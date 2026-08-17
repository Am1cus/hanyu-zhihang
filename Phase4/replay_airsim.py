import argparse
import io
import json
import math
import time
import urllib.request
from datetime import datetime, timedelta
from zipfile import ZipFile

import pandas as pd


def load_member(zip_path, member):
    with ZipFile(zip_path) as archive:
        return pd.read_csv(io.BytesIO(archive.read(member)))


def post_json(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def replay(args):
    frame = load_member(args.source, args.member).sort_values("timestamp")
    frame["relative_s"] = frame["timestamp"] - frame["timestamp"].iloc[0]
    frame = frame.set_index(pd.to_timedelta(frame["relative_s"], unit="s")).resample("1s").mean(numeric_only=True).interpolate()
    battery_level = args.start_battery_pct
    previous_current = None
    started_at = datetime.now().replace(microsecond=0)

    for sequence, (_, row) in enumerate(frame.iterrows()):
        if previous_current is not None:
            consumed_ah = max(previous_current, 0) / 3600.0
            battery_level = max(0.0, battery_level - consumed_ah / args.nominal_capacity_ah * 100)
        previous_current = float(row.current)
        speed = math.sqrt(row.velocity_x ** 2 + row.velocity_y ** 2 + row.velocity_z ** 2)
        payload = {
            "droneId": args.drone_id,
            "droneCode": args.drone_code,
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
            "altitude": float(row.altitude),
            "speed": float(speed),
            "heading": 0.0,
            "voltage": float(row.voltage),
            "current": float(row.current),
            "batteryLevel": round(battery_level, 4),
            "batteryTemperature": float(row.ambient_temp),
            "envTemperature": float(row.ambient_temp),
            "windSpeed": float(row.wind_speed),
            "windDirection": float(row.wind_direction),
            "collectTime": (started_at + timedelta(seconds=sequence)).strftime("%Y-%m-%dT%H:%M:%S"),
        }
        result = post_json(args.backend_url.rstrip("/") + "/api/telemetry", payload)
        if result.get("code") != 200:
            raise RuntimeError(f"遥测上报失败：{result}")
        print(f"[{sequence + 1:03d}/{len(frame):03d}] battery={battery_level:.2f}% response={result.get('code')}")
        if args.speed > 0:
            time.sleep(1 / args.speed)


def main():
    parser = argparse.ArgumentParser(description="以1Hz向Spring Boot回放AirSim遥测")
    parser.add_argument("source")
    parser.add_argument("--member", default="airsim_data/raw_extreme.csv")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8080")
    parser.add_argument("--drone-id", type=int, default=2)
    parser.add_argument("--drone-code", default="UAV-002")
    parser.add_argument("--nominal-capacity-ah", type=float, default=5.2)
    parser.add_argument("--start-battery-pct", type=float, default=100.0)
    parser.add_argument("--speed", type=float, default=1.0, help="回放倍速；0表示无等待")
    replay(parser.parse_args())


if __name__ == "__main__":
    main()
