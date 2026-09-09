"""Read-only benchmark on the existing V2 held-out flights. No fitting or calibration.

Run from learn: .venv/bin/python Phase4/evaluate_capacity_baselines.py
The JSON on stdout can be archived beside the original validation report.
"""
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from torch import nn
from airsim_capacity_model import AirSimCapacityLSTM, FEATURE_COLUMNS
from train_airsim_capacity_lstm import build_samples, metrics, select_quantization_engine

ROOT = Path(__file__).resolve().parent


def main():
    torch.set_num_threads(1)
    dataset_path = ROOT / "processed/airsim_capacity_dataset.csv"
    model_path = ROOT / "models/airsim_capacity_lstm_v2_quantized.pth"
    report = json.loads((ROOT / "models/airsim_capacity_validation_v2.json").read_text())
    frame = pd.read_csv(dataset_path)
    test_ids = report["test_flights"]
    instantaneous, persistence = [], []
    for flight_id in test_ids:
        flight = frame[frame.flight_id == flight_id].sort_values("timestamp_s").reset_index(drop=True)
        for index in range(29, len(flight)):
            assert flight.loc[index, "timestamp_s"] - flight.loc[index - 10, "timestamp_s"] == 10
            instantaneous.append(flight.loc[index, "current_A"] * 10 / 3600)
            persistence.append(flight.loc[index - 10, "current_capacity_ah"] - flight.loc[index, "current_capacity_ah"])
    scaler = joblib.load(ROOT / "models/airsim_capacity_scaler_v2.pkl")
    normalized = frame.copy()
    normalized.loc[:, FEATURE_COLUMNS] = scaler.transform(frame[FEATURE_COLUMNS])
    x_values, y_values, _ = build_samples(normalized, test_ids)
    engine = select_quantization_engine()
    model = torch.quantization.quantize_dynamic(AirSimCapacityLSTM(), {nn.LSTM}, dtype=torch.qint8)
    model.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=False))
    model.eval()
    with torch.no_grad():
        lstm = model(torch.tensor(x_values)).numpy().reshape(-1)
    methods = [
        ("lstm_int8", "LSTM V2 · INT8", lstm),
        ("current_times_horizon", "当前电流 × 10秒", instantaneous),
        ("last_10s_consumption", "延续过去10秒耗电", persistence),
    ]
    result = {
        "scope": "same five held-out flights and 105 overlapping windows; no fitting",
        "test_flights": test_ids,
        "sample_count": len(y_values),
        "target": "next_10s_consumption_ah",
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "quantization_engine": engine,
        "methods": [{"id": key, "name": name, **metrics(y_values, values)} for key, name, values in methods],
        "conclusion": "LSTM has not beaten last-10s persistence on this split. Simulation accuracy is not real-flight validation.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
