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

from flight_time_model import FEATURE_COLUMNS, LOOKBACK, FlightTimeLSTM


SEED = 42


def split_flights(flight_ids):
    ids = sorted(set(flight_ids))
    if len(ids) < 20:
        raise RuntimeError(f"独立架次仅{len(ids)}个，至少需要20个才能训练V2")
    random.Random(SEED).shuffle(ids)
    train_end = max(1, int(len(ids) * 0.7))
    validation_end = max(train_end + 1, int(len(ids) * 0.85))
    return ids[:train_end], ids[train_end:validation_end], ids[validation_end:]


def build_samples(frame, flight_ids):
    x_values, y_values = [], []
    for flight_id in flight_ids:
        flight = frame[frame.flight_id == flight_id].sort_values("timestamp_s")
        features = flight[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        targets = flight["remaining_time_s"].to_numpy(dtype=np.float32)
        for index in range(LOOKBACK - 1, len(flight)):
            x_values.append(features[index - LOOKBACK + 1:index + 1])
            y_values.append(targets[index])
    if not x_values:
        raise RuntimeError("没有足够的30秒连续窗口")
    return np.asarray(x_values, dtype=np.float32), np.asarray(y_values, dtype=np.float32).reshape(-1, 1)


def metrics(true, predicted):
    true = np.asarray(true).reshape(-1)
    predicted = np.asarray(predicted).reshape(-1)
    mae = float(np.mean(np.abs(true - predicted)))
    valid = true >= 5.0
    mape = float(np.mean(np.abs((true[valid] - predicted[valid]) / true[valid])) * 100) if valid.any() else None
    return {"mae_s": mae, "mape_pct_remaining_ge_5s": mape}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(Path(__file__).parent / "processed" / "flight_time_dataset.csv"))
    parser.add_argument("--output-dir", default=str(Path(__file__).parent / "models"))
    parser.add_argument("--epochs", type=int, default=300)
    args = parser.parse_args()

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    frame = pd.read_csv(args.dataset)
    required = {"flight_id", "timestamp_s", "remaining_time_s", *FEATURE_COLUMNS}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError("训练集缺少字段：" + ", ".join(missing))

    train_ids, validation_ids, test_ids = split_flights(frame.flight_id.unique())
    scaler = StandardScaler().fit(frame[frame.flight_id.isin(train_ids)][FEATURE_COLUMNS])
    frame.loc[:, FEATURE_COLUMNS] = scaler.transform(frame[FEATURE_COLUMNS])
    train_x, train_y = build_samples(frame, train_ids)
    validation_x, validation_y = build_samples(frame, validation_ids)
    test_x, test_y = build_samples(frame, test_ids)

    model = FlightTimeLSTM()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    loss_function = nn.MSELoss()
    loader = DataLoader(
        TensorDataset(torch.tensor(train_x), torch.tensor(train_y)),
        batch_size=32,
        shuffle=True,
    )
    best_state, best_loss = None, float("inf")
    for epoch in range(args.epochs):
        model.train()
        for batch_x, batch_y in loader:
            optimizer.zero_grad()
            loss = loss_function(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            validation_loss = loss_function(model(torch.tensor(validation_x)), torch.tensor(validation_y)).item()
        if validation_loss < best_loss:
            best_loss = validation_loss
            best_state = {name: value.detach().clone() for name, value in model.state_dict().items()}

    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        predictions = model(torch.tensor(test_x)).numpy()
    evaluation = metrics(test_y, predictions)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), output_dir / "flight_time_lstm_v2.pth")
    quantized = torch.quantization.quantize_dynamic(model, {nn.LSTM}, dtype=torch.qint8)
    torch.save(quantized.state_dict(), output_dir / "flight_time_lstm_v2_quantized.pth")
    joblib.dump(scaler, output_dir / "flight_time_scaler_v2.pkl")
    report = {
        "model_version": "flight_time_lstm_v2",
        "lookback_seconds": LOOKBACK,
        "features": FEATURE_COLUMNS,
        "train_flights": train_ids,
        "validation_flights": validation_ids,
        "test_flights": test_ids,
        "test_metrics": evaluation,
        "validated_on_real_data": False,
    }
    (output_dir / "flight_time_validation_v2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
