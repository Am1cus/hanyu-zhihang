import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from audit_airsim import audit, canonical_columns, load_flights


def prepare(source, output):
    result = audit(source)
    if not result["training_ready"]:
        raise RuntimeError("数据未通过训练门禁：" + "；".join(result["blockers"]))

    prepared = []
    for flight_id, frame in load_flights(source):
        names = canonical_columns(frame.columns)
        frame = frame.sort_values(names["timestamp"]).copy()
        start = float(frame[names["timestamp"]].iloc[0])
        frame["elapsed_s"] = frame[names["timestamp"]].astype(float) - start
        frame = frame.set_index(pd.to_timedelta(frame["elapsed_s"], unit="s")).resample("1s").mean(numeric_only=True).interpolate()
        end_s = float(frame["elapsed_s"].max())
        speed = np.sqrt(
            frame[names["velocity_x"]] ** 2
            + frame[names["velocity_y"]] ** 2
            + frame[names["velocity_z"]] ** 2
        )
        prepared.append(pd.DataFrame({
            "flight_id": flight_id,
            "timestamp_s": frame["elapsed_s"].to_numpy(),
            "env_temperature_C": frame[names["temperature"]].to_numpy(),
            "wind_speed_ms": frame[names["wind_speed"]].to_numpy(),
            "voltage_V": frame[names["voltage"]].to_numpy(),
            "current_A": frame[names["current"]].to_numpy(),
            "battery_level_pct": frame[names["battery_level"]].to_numpy(),
            "speed_ms": speed.to_numpy(),
            "altitude_m": frame[names["altitude"]].to_numpy(),
            "remaining_time_s": end_s - frame["elapsed_s"].to_numpy(),
        }))

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(prepared, ignore_index=True).to_csv(output, index=False)
    print(f"训练集已生成：{output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--output", default=str(Path(__file__).parent / "processed" / "flight_time_dataset.csv"))
    args = parser.parse_args()
    prepare(args.source, args.output)


if __name__ == "__main__":
    main()
