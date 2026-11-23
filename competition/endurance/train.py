"""Fit the scalar endurance model from the existing 35-flight AirSim dataset.

Run: python -m competition.endurance.train
No flight-ending labels are manufactured. Holdout is by complete flight, with
one deterministic flight per temperature/wind condition. Serving uses only
the training split coefficients; it is not refitted after inspecting holdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from . import MODEL_VERSION

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "Phase4/processed/airsim_capacity_dataset.csv"
DEFAULT_OUTPUT = Path(__file__).parent / "artifacts"
DEFAULT_EVIDENCE = Path(__file__).parent / "evidence"


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def metrics(actual, predicted):
    a, p = np.asarray(actual), np.asarray(predicted)
    return {"mae_a": float(np.mean(abs(a - p))),
            "mape_percent": float(np.mean(abs((a - p) / a)) * 100),
            "rmse_a": float(np.sqrt(np.mean((a - p) ** 2)))}


def train(source=DEFAULT_SOURCE, output=DEFAULT_OUTPUT, evidence=DEFAULT_EVIDENCE):
    source, output, evidence = Path(source), Path(output), Path(evidence)
    frame = pd.read_csv(source)
    columns = ["env_temperature_C", "wind_speed_ms", "current_A", "speed_ms",
               "battery_level_pct", "current_capacity_ah"]
    if not np.isfinite(frame[columns].to_numpy()).all() or (frame.battery_level_pct <= 0).any():
        raise ValueError("训练数据含无效数值或非正 SOC")
    frame["full_ah"] = frame.current_capacity_ah / (frame.battery_level_pct / 100)
    flights = frame.groupby("flight_id", sort=True).agg(
        temperature=("env_temperature_C", "median"), wind=("wind_speed_ms", "median"),
        full_ah=("full_ah", "median"), current_a=("current_A", "mean"), rows=("current_A", "size"))
    holdout = sorted(flights.groupby(["temperature", "wind"]).apply(
        lambda group: sorted(group.index)[-1], include_groups=False).tolist())
    train_ids = sorted(set(flights.index) - set(holdout))
    train_rows = frame[frame.flight_id.isin(train_ids)].copy()
    test_rows = frame[frame.flight_id.isin(holdout)].copy()
    capacity_rows = flights.loc[train_ids]
    matrix = np.column_stack([np.ones(len(capacity_rows)), capacity_rows.temperature.to_numpy() - 25])
    capacity_at_25, slope = np.linalg.lstsq(matrix, capacity_rows.full_ah.to_numpy(), rcond=None)[0]
    if capacity_at_25 <= 0 or slope < 0:
        raise ValueError("本数据不支持所声明的温度容量结构，请检查数据")

    def features(rows):
        return np.column_stack([np.ones(len(rows)), rows.wind_speed_ms, rows.speed_ms ** 2])

    # Give every complete flight the same weight, regardless of its log length.
    weights = 1 / np.sqrt(train_rows.groupby("flight_id").current_A.transform("size").to_numpy())
    coefficients, _ = nnls(features(train_rows) * weights[:, None], train_rows.current_A.to_numpy() * weights)
    if coefficients[0] <= 0:
        raise ValueError("拟合得到非正基础电流")
    train_prediction = features(train_rows) @ coefficients
    test_prediction = features(test_rows) @ coefficients
    test_rows["predicted_current_a"] = test_prediction
    flight_results = []
    for flight_id, group in test_rows.groupby("flight_id", sort=True):
        actual, predicted = float(group.current_A.mean()), float(group.predicted_current_a.mean())
        temp = float(group.env_temperature_C.median())
        predicted_full = float(capacity_at_25 + slope * (temp - 25))
        flight_results.append({"flight_id": flight_id, "temperature_c": temp,
                               "wind_speed_ms": float(group.wind_speed_ms.median()),
                               "rows": len(group), "actual_mean_current_a": actual,
                               "predicted_mean_current_a": predicted,
                               "observed_full_capacity_ah": float(group.full_ah.median()),
                               "predicted_full_capacity_ah": predicted_full,
                               "point_metrics": metrics(group.current_A, group.predicted_current_a)})
    baseline = float(capacity_rows.current_a.mean())
    current_flight_metrics = metrics([r["actual_mean_current_a"] for r in flight_results],
                                    [r["predicted_mean_current_a"] for r in flight_results])
    artifact = {
        "schema_version": 1, "model_version": MODEL_VERSION,
        "profile": {"name": "AirSim 参考机型 · 约 1.8 Ah 电池", "nominal_voltage_v": 11.1,
                    "default_ground_speed_ms": 2., "default_reserve_percent": 20.,
                    "max_airspeed_ms": 15.,
                    "voltage_and_airspeed_source": "route-conversion and tracking assumptions, not learned specifications"},
        "capacity_model": {"reference_temperature_c": 25., "capacity_at_reference_ah": float(capacity_at_25),
                           "slope_ah_per_c": float(slope), "temperature_above_reference": "hold_capacity_constant",
                           "fit_target": "per-flight median(current_capacity_ah / SOC_fraction)"},
        "current_model": {"features": ["1", "wind_speed_ms", "ground_speed_ms_squared"],
                          "coefficients": dict(zip(["intercept_a", "wind_a_per_ms", "speed_a_per_ms2"],
                                                   map(float, coefficients))),
                          "fit_method": "nonnegative_least_squares_equal_flight_weight"},
        "observed_ranges": {key: [float(frame[column].min()), float(frame[column].max())]
                            for key, column in {"temperature_c": "env_temperature_C", "wind_speed_ms": "wind_speed_ms",
                                                "ground_speed_ms": "speed_ms", "battery_percent": "battery_level_pct"}.items()},
        "training": {"source": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else source.name,
                     "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                     "total_rows": len(frame), "total_flights": len(flights),
                     "training_flights": train_ids, "holdout_flights": holdout,
                     "split": "lexically last flight per temperature/wind stratum held out; no post-holdout refit",
                     "holdout_current_flight_mean_metrics": current_flight_metrics},
        "interpretation": {"time_target": "capacity_Ah * SOC_fraction / predicted_current_A * 60 minutes",
                           "observed_exhaustion_labels": False, "real_aircraft_data": False,
                           "scope": "constant-condition endurance extrapolation from short AirSim segments",
                           "capacity_reference_at_25c_is_extrapolated": True,
                           "training_speed": "source speed_ms includes vertical velocity; at serving, level-flight speed is used",
                           "no_soc_load_fit": "data span high SOC only; current held independent of SOC"},
    }
    report = {"model_version": MODEL_VERSION, "source_sha256": artifact["training"]["source_sha256"],
              "training_rows": len(train_rows), "holdout_rows": len(test_rows),
              "training_current_point_metrics": metrics(train_rows.current_A, train_prediction),
              "holdout_current_point_metrics": metrics(test_rows.current_A, test_prediction),
              "holdout_current_flight_mean_metrics": current_flight_metrics,
              "baseline_constant_current_a": baseline,
              "baseline_holdout_flight_mean_metrics": metrics([r["actual_mean_current_a"] for r in flight_results],
                                                               [baseline] * len(flight_results)),
              "flights": flight_results,
              "not_measured": "Full-flight remaining-time error; these logs do not contain exhaustion endpoints."}
    dump(output / "endurance-v1.json", artifact)
    dump(evidence / "training-report.json", report)
    test_rows[["flight_id", "timestamp_s", "env_temperature_C", "wind_speed_ms", "speed_ms",
               "current_A", "predicted_current_a"]].to_csv(evidence / "holdout-current-predictions.csv", index=False)
    print(json.dumps({"model": str(output / "endurance-v1.json"), "train_flights": len(train_ids),
                      "holdout_flights": len(holdout), "holdout_current_flight_mean_metrics": current_flight_metrics,
                      "baseline": report["baseline_holdout_flight_mean_metrics"]}, ensure_ascii=False, indent=2))
    return artifact, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()
    train(args.source, args.output, args.evidence)
