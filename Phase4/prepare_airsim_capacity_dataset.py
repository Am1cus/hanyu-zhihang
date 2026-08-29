"""将35架次AirSim原始数据整理为1Hz未来容量预测数据集。"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from airsim_capacity_model import FORECAST_HORIZON_SECONDS
from audit_airsim import canonical_columns, load_flights


CAPACITY_COLUMNS = ["remaining_capacity_ah", "remaining_capacity_Ah", "capacity_Ah"]


def prepare(source, output):
    prepared = []
    for flight_id, raw in load_flights(source):
        names = canonical_columns(raw.columns)
        capacity_column = next((name for name in CAPACITY_COLUMNS if name in raw.columns), None)
        if capacity_column is None:
            raise RuntimeError(f"{flight_id}缺少剩余容量Ah字段")

        frame = raw.sort_values(names["timestamp"]).copy()
        start = float(frame[names["timestamp"]].iloc[0])
        frame["elapsed_s"] = frame[names["timestamp"]].astype(float) - start
        frame = (
            frame.set_index(pd.to_timedelta(frame["elapsed_s"], unit="s"))
            .resample("1s")
            .mean(numeric_only=True)
            .interpolate(limit_direction="both")
        )
        speed = np.sqrt(
            frame[names["velocity_x"]] ** 2
            + frame[names["velocity_y"]] ** 2
            + frame[names["velocity_z"]] ** 2
        )
        flight = pd.DataFrame({
            "flight_id": flight_id,
            "timestamp_s": frame.index.total_seconds(),
            "env_temperature_C": frame[names["temperature"]].to_numpy(),
            "wind_speed_ms": frame[names["wind_speed"]].to_numpy(),
            "voltage_V": frame[names["voltage"]].to_numpy(),
            "current_A": frame[names["current"]].to_numpy(),
            "battery_level_pct": frame[names["battery_level"]].to_numpy(),
            "speed_ms": speed.to_numpy(),
            "altitude_m": frame[names["altitude"]].to_numpy(),
            "current_capacity_ah": frame[capacity_column].to_numpy(),
        })
        flight["future_capacity_ah"] = flight["current_capacity_ah"].shift(
            -FORECAST_HORIZON_SECONDS
        )
        flight["capacity_consumption_ah"] = (
            flight["current_capacity_ah"] - flight["future_capacity_ah"]
        )
        prepared.append(flight.dropna(subset=["future_capacity_ah"]))

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = pd.concat(prepared, ignore_index=True)
    dataset.to_csv(output, index=False)
    print(f"AirSim容量训练集已生成：{output}")
    print(f"架次：{dataset.flight_id.nunique()} | 1Hz记录：{len(dataset)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "processed" / "airsim_capacity_dataset.csv"),
    )
    args = parser.parse_args()
    prepare(args.source, args.output)


if __name__ == "__main__":
    main()
