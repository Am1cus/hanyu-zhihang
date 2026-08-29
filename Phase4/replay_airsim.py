import argparse
import io
import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


ALIASES = {
    "timestamp": ["timestamp", "time", "timestamp_s"],
    "voltage": ["voltage", "voltage_V"],
    "current": ["current", "current_A"],
    "battery_level": ["battery_level", "soc_pct", "battery_level_pct"],
    "remaining_capacity": ["remaining_capacity_ah", "remaining_capacity_Ah", "capacity_Ah"],
    "temperature": ["ambient_temp", "env_temperature", "env_temperature_C", "temperature_C"],
    "battery_temperature": ["battery_temp", "battery_temperature", "battery_temperature_C"],
    "wind_speed": ["wind_speed", "wind_speed_ms"],
    "wind_direction": ["wind_direction", "wind_direction_deg"],
    "velocity_x": ["velocity_x", "vx"],
    "velocity_y": ["velocity_y", "vy"],
    "velocity_z": ["velocity_z", "vz"],
    "altitude": ["altitude", "altitude_m"],
    "latitude": ["latitude", "lat"],
    "longitude": ["longitude", "lon", "lng"],
    "heading": ["heading", "heading_deg", "yaw"],
}

REQUIRED_COLUMNS = [
    "timestamp",
    "voltage",
    "current",
    "temperature",
    "wind_speed",
    "velocity_x",
    "velocity_y",
    "velocity_z",
    "altitude",
]


def split_frame(frame, fallback_flight_id):
    if "flight_id" in frame.columns and not frame.empty:
        return [(str(flight_id), group.copy()) for flight_id, group in frame.groupby("flight_id", sort=True)]
    return [(fallback_flight_id, frame)]


def load_flights(source, member=None):
    source_path = Path(source).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"AirSim数据源不存在：{source_path}")

    flights = []
    if source_path.suffix.lower() == ".zip":
        with ZipFile(source_path) as archive:
            if member:
                members = [member]
            else:
                members = sorted(
                    name for name in archive.namelist()
                    if name.lower().endswith(".csv")
                    and Path(name).name.lower().startswith(("raw", "flight_"))
                )
            if not members:
                raise ValueError("ZIP中未找到以 raw 或 flight_ 开头的CSV文件")
            for name in members:
                try:
                    frame = pd.read_csv(io.BytesIO(archive.read(name)))
                except KeyError as error:
                    raise ValueError(f"ZIP中不存在成员：{name}") from error
                flights.extend(split_frame(frame, Path(name).stem))
        return flights

    if source_path.is_dir():
        paths = sorted(
            path for path in source_path.rglob("*.csv")
            if path.name.lower().startswith(("raw", "flight_"))
        )
        if not paths:
            raise ValueError("目录中未找到以 raw 或 flight_ 开头的CSV文件")
        for path in paths:
            flights.extend(split_frame(pd.read_csv(path), path.stem))
        return flights

    if source_path.suffix.lower() == ".csv":
        return split_frame(pd.read_csv(source_path), source_path.stem)

    raise ValueError(f"不支持的数据源：{source_path}")


def select_flight(flights, requested_flight_id):
    exact_matches = [(flight_id, frame) for flight_id, frame in flights if flight_id == requested_flight_id]
    if len(exact_matches) == 1:
        return exact_matches[0]

    if requested_flight_id.isdigit():
        requested_number = int(requested_flight_id)
        numeric_matches = []
        for flight_id, frame in flights:
            suffix = re.search(r"(\d+)$", flight_id)
            if suffix and int(suffix.group(1)) == requested_number:
                numeric_matches.append((flight_id, frame))
        if len(numeric_matches) == 1:
            return numeric_matches[0]

    available = ", ".join(flight_id for flight_id, _ in flights)
    raise ValueError(f"找不到架次 {requested_flight_id}。可用架次：{available}")


def resolve_columns(frame):
    available = set(frame.columns)
    columns = {
        canonical: next((candidate for candidate in candidates if candidate in available), None)
        for canonical, candidates in ALIASES.items()
    }
    missing = [canonical for canonical in REQUIRED_COLUMNS if not columns[canonical]]
    if missing:
        raise ValueError("所选架次缺少回放必要字段：" + ", ".join(missing))
    return columns


def prepare_flight(frame, columns, max_samples=None):
    numeric = pd.DataFrame()
    for canonical, source_column in columns.items():
        if source_column:
            numeric[canonical] = pd.to_numeric(frame[source_column], errors="coerce")

    invalid = [name for name in REQUIRED_COLUMNS if numeric[name].isna().any()]
    if invalid:
        raise ValueError("所选架次存在无法转换为数值的必要字段：" + ", ".join(invalid))

    numeric = numeric.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    if numeric.empty:
        raise ValueError("所选架次没有可回放记录")
    numeric["relative_s"] = numeric["timestamp"] - numeric["timestamp"].iloc[0]
    numeric = numeric.set_index(pd.to_timedelta(numeric["relative_s"], unit="s"))
    numeric = numeric.drop(columns=["timestamp", "relative_s"])
    numeric = numeric.resample("1s").mean().interpolate(limit_direction="both")

    if "battery_level" in numeric and numeric["battery_level"].max() <= 1.5:
        numeric["battery_level"] = numeric["battery_level"] * 100.0
    if max_samples is not None:
        numeric = numeric.iloc[:max_samples]
    return numeric


def post_json(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"后台返回HTTP {error.code}：{detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"无法连接后台 {url}：{error.reason}") from error


def row_value(row, name, default):
    value = row.get(name, default)
    return float(default if pd.isna(value) else value)


def advance_gps_from_ned(latitude, longitude, north_speed_ms, east_speed_ms, seconds=1.0):
    """AirSim缺少GPS时，根据NED水平速度积分得到演示航迹坐标。"""
    meters_per_degree = 111_320.0
    next_latitude = latitude + north_speed_ms * seconds / meters_per_degree
    longitude_scale = meters_per_degree * max(math.cos(math.radians(latitude)), 0.01)
    next_longitude = longitude + east_speed_ms * seconds / longitude_scale
    return next_latitude, next_longitude


def replay(args, flight_id, frame, columns):
    prepared = prepare_flight(frame, columns, args.max_samples)
    battery_level = args.start_battery_pct
    previous_current = None
    synthetic_latitude = args.latitude
    synthetic_longitude = args.longitude
    started_at = datetime.now().replace(microsecond=0)
    total = len(prepared)

    print(f"回放架次：{flight_id} | 原始记录：{len(frame)} | 1Hz记录：{total} | 倍速：{args.speed}x")
    for sequence, (_, row) in enumerate(prepared.iterrows()):
        current = row_value(row, "current", 0.0)
        if "battery_level" in prepared.columns:
            battery_level = min(100.0, max(0.0, row_value(row, "battery_level", battery_level)))
        elif previous_current is not None:
            consumed_ah = max(previous_current, 0.0) / 3600.0
            battery_level = max(0.0, battery_level - consumed_ah / args.nominal_capacity_ah * 100.0)
        previous_current = current

        velocity_x = row_value(row, "velocity_x", 0.0)
        velocity_y = row_value(row, "velocity_y", 0.0)
        velocity_z = row_value(row, "velocity_z", 0.0)
        speed = math.sqrt(velocity_x ** 2 + velocity_y ** 2 + velocity_z ** 2)
        temperature = row_value(row, "temperature", 0.0)
        if columns.get("latitude") and columns.get("longitude"):
            latitude = row_value(row, "latitude", args.latitude)
            longitude = row_value(row, "longitude", args.longitude)
        else:
            if sequence > 0:
                synthetic_latitude, synthetic_longitude = advance_gps_from_ned(
                    synthetic_latitude,
                    synthetic_longitude,
                    velocity_x,
                    velocity_y,
                )
            latitude = synthetic_latitude
            longitude = synthetic_longitude

        if columns.get("heading"):
            heading = row_value(row, "heading", args.heading)
        elif abs(velocity_x) + abs(velocity_y) > 0.05:
            heading = (math.degrees(math.atan2(velocity_y, velocity_x)) + 360.0) % 360.0
        else:
            heading = args.heading

        payload = {
            "droneId": args.drone_id,
            "droneCode": args.drone_code,
            "latitude": latitude,
            "longitude": longitude,
            "altitude": row_value(row, "altitude", 0.0),
            "speed": speed,
            "heading": heading,
            "voltage": row_value(row, "voltage", 0.0),
            "current": current,
            "batteryLevel": round(battery_level, 4),
            "batteryTemperature": row_value(row, "battery_temperature", temperature),
            "envTemperature": temperature,
            "windSpeed": row_value(row, "wind_speed", 0.0),
            "windDirection": row_value(row, "wind_direction", args.wind_direction),
            "collectTime": (started_at + timedelta(seconds=sequence)).strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if "remaining_capacity" in prepared.columns:
            payload["remainingCapacityAh"] = row_value(row, "remaining_capacity", 0.0)
        result = post_json(args.backend_url.rstrip("/") + "/api/telemetry", payload)
        if result.get("code") != 200:
            raise RuntimeError(f"遥测上报失败：{result}")
        print(
            f"[{sequence + 1:03d}/{total:03d}] "
            f"SOC={battery_level:6.2f}% temp={temperature:6.1f}°C "
            f"wind={payload['windSpeed']:4.1f}m/s response=200"
        )
        if args.speed > 0:
            time.sleep(1.0 / args.speed)

    print(f"架次 {flight_id} 回放完成，共上报 {total} 条遥测。")


def build_parser():
    parser = argparse.ArgumentParser(description="选择AirSim架次，重采样至1Hz并向Spring Boot回放")
    parser.add_argument("source", help="新版/旧版AirSim ZIP、CSV或数据目录")
    parser.add_argument("--flight-id", help="架次ID，也可只写数字；省略时选择数据源中的第一个架次")
    parser.add_argument("--member", help="兼容旧数据包：直接指定ZIP内CSV成员")
    parser.add_argument("--list", action="store_true", help="列出数据源中的全部架次后退出")
    parser.add_argument("--validate-only", action="store_true", help="只校验所选架次，不连接后台")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8080")
    parser.add_argument("--drone-id", type=int, default=2)
    parser.add_argument("--drone-code", default="AIRSIM-001")
    parser.add_argument("--nominal-capacity-ah", type=float, default=5.2)
    parser.add_argument("--start-battery-pct", type=float, default=100.0)
    parser.add_argument("--latitude", type=float, default=45.7600, help="数据缺少纬度时的演示值")
    parser.add_argument("--longitude", type=float, default=126.6600, help="数据缺少经度时的演示值")
    parser.add_argument("--heading", type=float, default=90.0, help="数据缺少航向时的演示值")
    parser.add_argument("--wind-direction", type=float, default=270.0, help="数据缺少风向时的演示值")
    parser.add_argument("--max-samples", type=int, help="最多回放多少条1Hz记录")
    parser.add_argument("--speed", type=float, default=2.0, help="回放倍速；0表示无等待")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.speed < 0:
        parser.error("--speed 不能小于0")
    if args.max_samples is not None and args.max_samples <= 0:
        parser.error("--max-samples 必须大于0")

    try:
        flights = load_flights(args.source, args.member)
        if args.list:
            print(f"共发现 {len(flights)} 个架次：")
            for flight_id, frame in flights:
                print(f"- {flight_id}: {len(frame)} 条原始记录")
            return

        requested_flight_id = args.flight_id or flights[0][0]
        flight_id, frame = select_flight(flights, requested_flight_id)
        columns = resolve_columns(frame)
        prepared = prepare_flight(frame, columns, args.max_samples)
        if args.validate_only:
            battery_source = columns["battery_level"] or "电流积分回退"
            print(
                f"校验通过：{flight_id} | 原始 {len(frame)} 条 | 1Hz {len(prepared)} 条 | "
                f"SOC来源 {battery_source}"
            )
            return
        replay(args, flight_id, frame, columns)
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
