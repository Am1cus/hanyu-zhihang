"""Causal, versioned AirSim energy experiments. No changes to deployed V2.

The prediction target is the difference between two completed one-second mean
charge measurements, ten seconds apart, not SOH or measured cold-cell capacity.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import torch
from torch import nn

LOOKBACK = 30
HORIZON = 10
GROUND = {"F001", "F007", "F013", "F019"}
CORE = ["current", "wind_speed", "horizontal_speed", "velocity_z",
        "relative_air_speed", "wind_along_velocity"]
FULL = CORE + ["voltage", "soc_pct", "ambient_temp", "battery_temperature", "payload_kg"]
FEATURE_SETS = {
    "core": CORE,
    "full": FULL,
    "no_thermal": [x for x in FULL if x not in {"ambient_temp", "battery_temperature"}],
    "with_altitude": FULL + ["altitude"],
    "current_only": ["current"],
}
ALL_FEATURES = FULL + ["altitude"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False), encoding="utf-8")


def aggregate_raw(raw):
    """Only complete bins; stamp availability at the RIGHT boundary.

    A bucket [k,k+1) is not available at k. A missing/undersampled bucket stays
    NaN: it cannot silently be bridged by a training window. The terminal
    partial second is discarded even if it already contains nine samples.
    """
    needed = {"timestamp", "remaining_capacity_ah", "velocity_x", "velocity_y",
              "velocity_z", "wind_x", "wind_y", "wind_z", *FULL[:2],
              "voltage", "soc_pct", "ambient_temp", "battery_temperature",
              "payload_kg", "altitude"}
    if needed - set(raw.columns):
        raise ValueError(f"Missing raw columns: {sorted(needed-set(raw.columns))}")
    if not np.isfinite(raw[list(needed)].to_numpy(dtype=float)).all():
        raise ValueError("Non-finite telemetry")
    if len(raw) < 2 or (np.diff(raw.timestamp) <= 0).any():
        raise ValueError("Raw timestamps must be strictly increasing")
    elapsed = raw.timestamp.to_numpy() - raw.timestamp.iloc[0]
    f = raw.copy()
    f.index = pd.to_timedelta(elapsed, unit="s")
    values = f.resample("1s").mean(numeric_only=True)
    count = f.resample("1s").size()
    # Stop before the last uncompleted interval; no file-tail label fabrication.
    completed = values.index.total_seconds() + 1 <= elapsed[-1] + 1e-9
    values = values.loc[completed].copy()
    values.loc[count.loc[values.index] < 9, :] = np.nan
    values["horizontal_speed"] = np.hypot(values.velocity_x, values.velocity_y)
    values["relative_air_speed"] = np.sqrt(
        (values.velocity_x-values.wind_x)**2 + (values.velocity_y-values.wind_y)**2
        + (values.velocity_z-values.wind_z)**2)
    values["wind_along_velocity"] = (
        values.wind_x*values.velocity_x + values.wind_y*values.velocity_y
    ) / np.maximum(values.horizontal_speed, 0.1)
    values["available_at_s"] = values.index.total_seconds() + 1
    values["bin_start_s"] = values.index.total_seconds()
    return values.reset_index(drop=True)


def read_dataset(source):
    frames, metadata, exclusions = {}, {}, {}
    with ZipFile(source) as archive:
        batch = json.loads(archive.read("dataset_v2/dataset_manifest_batch.json"))
        for entry in batch["flights"]:
            flight = entry["flight_id"]
            prefix = f"dataset_v2/flight_{flight}/"
            manifest = json.loads(archive.read(prefix + "manifest.json"))
            if flight in GROUND:
                exclusions[flight] = "suspected_ground_record_pending_source_verification"
                continue
            if manifest["end_reason"] != "battery_threshold_reached":
                exclusions[flight] = manifest["end_reason"]
                continue
            member = prefix + f"flights/{flight}_raw_10Hz.csv"
            raw_bytes = archive.read(member)
            raw = pd.read_csv(io.BytesIO(raw_bytes))
            if set(raw.flight_id) != {flight}:
                raise ValueError(f"Flight ID mismatch: {flight}")
            frames[flight] = aggregate_raw(raw)
            metadata[flight] = {"split": batch["split"][flight],
                                "temperature_c": entry["ambient_temp_c"],
                                "track": entry["track"], "raw_member": member,
                                "raw_sha256": hashlib.sha256(raw_bytes).hexdigest()}
    return frames, metadata, exclusions


def build_windows(frames, ids):
    xs, ys, bases, currents, flights, times = [], [], [], [], [], []
    for flight in ids:
        frame = frames[flight]
        raw_x = frame[ALL_FEATURES].to_numpy(dtype=np.float32)
        charge = frame.remaining_capacity_ah.to_numpy(dtype=float)
        for t in range(LOOKBACK-1, len(frame)-HORIZON):
            x = raw_x[t-LOOKBACK+1:t+1]
            # All history AND future label intervals must be observed.
            if not np.isfinite(raw_x[t-LOOKBACK+1:t+HORIZON+1]).all():
                continue
            if not np.isfinite(charge[t-LOOKBACK+1:t+HORIZON+1]).all():
                continue
            y = charge[t] - charge[t+HORIZON]
            base = charge[t-HORIZON] - charge[t]
            if y <= 1e-9 or base <= 1e-9:
                raise ValueError(f"Nonpositive discharge label: {flight} at {t}")
            xs.append(x); ys.append(y); bases.append(base)
            currents.append(charge[t]); flights.append(flight)
            times.append(frame.available_at_s.iloc[t])
    if not xs:
        raise ValueError("No complete 30+10 second windows")
    return {"x": np.asarray(xs, dtype=np.float32), "y": np.asarray(ys),
            "base": np.asarray(bases), "capacity": np.asarray(currents),
            "flight": np.asarray(flights), "time": np.asarray(times)}


def subset(data, mask):
    return {k: v[mask] for k, v in data.items()}


def metrics(y, prediction):
    y, p = np.asarray(y, dtype=float), np.asarray(prediction, dtype=float)
    if len(y) != len(p) or not np.isfinite(p).all() or (y <= 0).any():
        raise ValueError("Invalid prediction/label; do not silently filter failures")
    e = p-y
    ape = np.abs(e/y)*100
    return {"n": len(y), "mae_mah": float(np.abs(e).mean()*1000),
            "rmse_mah": float(np.sqrt(np.mean(e**2))*1000),
            "mape_pct": float(ape.mean()), "ape_p90_pct": float(np.percentile(ape,90)),
            "bias_mah": float(e.mean()*1000), "nonpositive_predictions": int((p<=0).sum())}


def group_metrics(data, prediction):
    result = metrics(data["y"], prediction)
    per = {f: metrics(data["y"][data["flight"]==f], prediction[data["flight"]==f])
           for f in np.unique(data["flight"])}
    result["flight_macro_mape_pct"] = float(np.mean([v["mape_pct"] for v in per.values()]))
    result["per_flight"] = per
    mask = np.zeros(len(prediction), dtype=bool)
    for f in per:
        indices = np.flatnonzero(data["flight"]==f)
        # 40-second-separated anchors: historical+future source bins do not overlap.
        last = -np.inf
        for i in indices:
            if data["time"][i]-last >= LOOKBACK+HORIZON:
                mask[i] = True; last = data["time"][i]
    result["nonoverlap_40s"] = metrics(data["y"][mask], prediction[mask])
    return result


def causal_baselines(data):
    current = data["x"][:, :, ALL_FEATURES.index("current")]
    values = {"history_10s": data["base"], "current_10s": current[:, -1]*HORIZON/3600}
    for n in (3, 5, 10, 20, 30):
        values[f"mean_current_{n}s"] = current[:, -n:].mean(axis=1)*HORIZON/3600
    for decay in (0.1, 0.3, 0.6):
        weights = (1-decay)**np.arange(LOOKBACK-1, -1, -1)
        values[f"ema_current_{decay}"] = (current@weights/weights.sum())*HORIZON/3600
    return values


def tabular_features(data):
    """Identical causal sensor access for the non-neural competitors."""
    x = data["x"][:, :, :len(FULL)]
    cols = [np.log(data["base"])[:, None], x[:, -1]]
    for n in (3, 10, 30):
        cols.extend([x[:, -n:].mean(axis=1), x[:, -n:].std(axis=1),
                     (x[:, -1]-x[:, -n])/max(n-1,1)])
    return np.concatenate(cols, axis=1)


class EnergyLSTM(nn.Module):
    def __init__(self, input_size, hidden_size):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.head = nn.Sequential(nn.Linear(hidden_size, hidden_size), nn.Tanh(),
                                  nn.Linear(hidden_size, 1))
        # Residual candidate starts exactly at the baseline, not an arbitrary curve.
        nn.init.zeros_(self.head[-1].weight)
        nn.init.zeros_(self.head[-1].bias)

    def forward(self, x):
        return self.head(self.lstm(x)[0][:, -1]).squeeze(-1)


def selected_features(x, feature_set):
    return x[:, :, [ALL_FEATURES.index(f) for f in FEATURE_SETS[feature_set]]]


def predict_network(model, scaler, config, data, reference, batch_size=256):
    x = selected_features(data["x"], config["features"])
    x = scaler.transform(x.reshape(-1, x.shape[-1])).reshape(x.shape).astype(np.float32)
    output = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(x), batch_size):
            output.append(model(torch.from_numpy(x[start:start+batch_size])).numpy())
    # The residual is learned in log space; no calibration/smoothing/curve correction.
    anchor = data["base"] if config["residual"] else reference
    return np.asarray(anchor)*np.exp(np.concatenate(output).astype(float))
