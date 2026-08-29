"""按完整架次训练AirSim 10秒未来剩余容量LSTM。"""

import argparse
import json
import random
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from airsim_capacity_model import (
    FEATURE_COLUMNS,
    FORECAST_HORIZON_SECONDS,
    LOOKBACK,
    AirSimCapacityLSTM,
)


SEED = 42


def select_quantization_engine():
    for engine_name in ["qnnpack", "x86", "fbgemm"]:
        if engine_name in torch.backends.quantized.supported_engines:
            torch.backends.quantized.engine = engine_name
            return engine_name
    raise RuntimeError("当前PyTorch环境没有可用的动态量化后端")


def split_flights(frame):
    counts = frame.groupby("flight_id").size()
    eligible = sorted(counts[counts >= LOOKBACK].index.tolist())
    excluded = sorted(counts[counts < LOOKBACK].index.tolist())
    if len(eligible) < 20:
        raise RuntimeError(f"可构造窗口的独立架次仅{len(eligible)}个，至少需要20个")
    random.Random(SEED).shuffle(eligible)
    train_end = int(len(eligible) * 0.7)
    validation_end = int(len(eligible) * 0.85)
    return (
        eligible[:train_end],
        eligible[train_end:validation_end],
        eligible[validation_end:],
        excluded,
    )


def build_samples(frame, flight_ids):
    x_values, y_values, current_capacities = [], [], []
    for flight_id in flight_ids:
        flight = frame[frame.flight_id == flight_id].sort_values("timestamp_s")
        features = flight[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        targets = flight["capacity_consumption_ah"].to_numpy(dtype=np.float32)
        capacity = flight["current_capacity_ah"].to_numpy(dtype=np.float32)
        for index in range(LOOKBACK - 1, len(flight)):
            x_values.append(features[index - LOOKBACK + 1:index + 1])
            y_values.append(targets[index])
            current_capacities.append(capacity[index])
    if not x_values:
        raise RuntimeError("没有足够的连续30秒窗口")
    return (
        np.asarray(x_values, dtype=np.float32),
        np.asarray(y_values, dtype=np.float32).reshape(-1, 1),
        np.asarray(current_capacities, dtype=np.float32).reshape(-1, 1),
    )


def metrics(true, predicted):
    true = np.asarray(true).reshape(-1)
    predicted = np.asarray(predicted).reshape(-1)
    errors = predicted - true
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    mape = float(np.mean(np.abs(errors / true)) * 100)
    ss_res = float(np.sum(errors ** 2))
    ss_total = float(np.sum((true - np.mean(true)) ** 2))
    r2 = 1.0 - ss_res / ss_total if ss_total > 0 else None
    return {"mae_ah": mae, "rmse_ah": rmse, "mape_pct": mape, "r2": r2}


def predict(model, x_values):
    model.eval()
    with torch.no_grad():
        return model(torch.tensor(x_values)).numpy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        default=str(Path(__file__).parent / "processed" / "airsim_capacity_dataset.csv"),
    )
    parser.add_argument("--output-dir", default=str(Path(__file__).parent / "models"))
    parser.add_argument("--epochs", type=int, default=300)
    args = parser.parse_args()

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.set_num_threads(1)
    frame = pd.read_csv(args.dataset)
    required = {
        "flight_id",
        "current_capacity_ah",
        "future_capacity_ah",
        "capacity_consumption_ah",
        *FEATURE_COLUMNS,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError("训练集缺少字段：" + ", ".join(missing))

    train_ids, validation_ids, test_ids, excluded_ids = split_flights(frame)
    scaler = StandardScaler().fit(frame[frame.flight_id.isin(train_ids)][FEATURE_COLUMNS])
    frame.loc[:, FEATURE_COLUMNS] = scaler.transform(frame[FEATURE_COLUMNS])
    train_x, train_y, _ = build_samples(frame, train_ids)
    validation_x, validation_y, _ = build_samples(frame, validation_ids)
    test_x, test_y, test_current_capacity = build_samples(frame, test_ids)

    model = AirSimCapacityLSTM()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    loss_function = nn.MSELoss()
    loader = DataLoader(
        TensorDataset(torch.tensor(train_x), torch.tensor(train_y)),
        batch_size=32,
        shuffle=True,
    )
    best_state, best_loss, stale_epochs = None, float("inf"), 0
    for _ in range(args.epochs):
        model.train()
        for batch_x, batch_y in loader:
            optimizer.zero_grad()
            loss = loss_function(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            validation_loss = loss_function(
                model(torch.tensor(validation_x)), torch.tensor(validation_y)
            ).item()
        if validation_loss < best_loss - 1e-8:
            best_loss = validation_loss
            best_state = {name: value.detach().clone() for name, value in model.state_dict().items()}
            stale_epochs = 0
        else:
            stale_epochs += 1
        if stale_epochs >= 50:
            break

    model.load_state_dict(best_state)
    float_predictions = predict(model, test_x)
    quantization_engine = select_quantization_engine()
    quantized = torch.quantization.quantize_dynamic(model, {nn.LSTM}, dtype=torch.qint8)
    quantized_predictions = predict(quantized, test_x)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), output_dir / "airsim_capacity_lstm_v2.pth")
    torch.save(quantized.state_dict(), output_dir / "airsim_capacity_lstm_v2_quantized.pth")
    joblib.dump(scaler, output_dir / "airsim_capacity_scaler_v2.pkl")
    true_future_capacity = test_current_capacity - test_y
    float_future_capacity = test_current_capacity - float_predictions
    quantized_future_capacity = test_current_capacity - quantized_predictions
    report = {
        "model_version": "airsim_capacity_lstm_v2",
        "target": f"capacity_consumption_ah_next_{FORECAST_HORIZON_SECONDS}s",
        "output_transform": "future_capacity = current_measured_capacity - raw_lstm_consumption",
        "linear_calibration": False,
        "curve_smoothing": False,
        "lookback_seconds": LOOKBACK,
        "forecast_horizon_seconds": FORECAST_HORIZON_SECONDS,
        "features": FEATURE_COLUMNS,
        "train_flights": train_ids,
        "validation_flights": validation_ids,
        "test_flights": test_ids,
        "excluded_short_flights": excluded_ids,
        "sample_counts": {
            "train": len(train_x),
            "validation": len(validation_x),
            "test": len(test_x),
        },
        "float_test_metrics": metrics(true_future_capacity, float_future_capacity),
        "quantized_test_metrics": metrics(true_future_capacity, quantized_future_capacity),
        "float_consumption_metrics": metrics(test_y, float_predictions),
        "quantized_consumption_metrics": metrics(test_y, quantized_predictions),
        "data_source": "AirSim simulation",
        "quantization_engine": quantization_engine,
        "validated_on_real_data": False,
    }
    (output_dir / "airsim_capacity_validation_v2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
