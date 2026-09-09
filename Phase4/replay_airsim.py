import argparse
import hashlib
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

# Keep direct-script invocation supported by demo/replay.sh.
import sys
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


ALIASES = {
    "timestamp": ["timestamp", "time", "timestamp_s"],
    "voltage": ["voltage", "voltage_V"],
    "current": ["current", "current_A"],
    "battery_level": ["battery_level", "soc_pct", "battery_level_pct"],
    "remaining_capacity": ["remaining_capacity_ah", "remaining_capacity_Ah", "capacity_Ah"],
    "temperature": ["ambient_temp", "env_temperature", "env_temperature_C", "temperature_C"],
    "battery_temperature": ["battery_temp", "battery_temperature", "battery_temperature_C"],
    "wind_x": ["wind_x"],
    "wind_y": ["wind_y"],
    "wind_z": ["wind_z"],
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
            if any(Path(n).name == "dataset_manifest_batch.json" for n in archive.namelist()):
                if member:
                    raise ValueError("新版批次必须按manifest选择架次，不接受--member绕过审计")
                from Phase4.dataset_v2_replay import load_manifest_flights
                return load_manifest_flights(archive, hashlib.sha256(source_path.read_bytes()).hexdigest())
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
    if "v3_provenance" in frame.attrs:
        from Phase4.dataset_v2_replay import prepare_v3
        return prepare_v3(frame, columns, max_samples)
    numeric = pd.DataFrame()
    for canonical, source_column in columns.items():
        if source_column:
            numeric[canonical] = pd.to_numeric(frame[source_column], errors="coerce")

    invalid = [name for name in REQUIRED_COLUMNS if not numeric[name].map(lambda x: pd.notna(x) and math.isfinite(x)).all()]
    if invalid:
        raise ValueError("所选架次存在无法转换为数值的必要字段：" + ", ".join(invalid))

    duplicates = numeric[numeric["timestamp"].duplicated(keep=False)]
    if not duplicates.empty and (duplicates.groupby("timestamp").nunique(dropna=False) > 1).any().any():
        raise ValueError("同一原始时间戳存在内容冲突，不能自动选择一条覆盖")
    numeric = numeric.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    if numeric.empty:
        raise ValueError("所选架次没有可回放记录")
    numeric["relative_s"] = numeric["timestamp"] - numeric["timestamp"].iloc[0]
    numeric = numeric.set_index(pd.to_timedelta(numeric["relative_s"], unit="s"))
    numeric = numeric.drop(columns=["timestamp", "relative_s"])
    # Preserve missing seconds as gaps. Never fabricate future/past telemetry by interpolation.
    numeric = numeric.resample("1s").mean().dropna(subset=[name for name in REQUIRED_COLUMNS if name != "timestamp"])

    if "battery_level" in numeric and numeric["battery_level"].max() <= 1.5:
        numeric["battery_level"] = numeric["battery_level"] * 100.0
    if max_samples is not None:
        numeric = numeric.iloc[:max_samples]
    return numeric


def post_json(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, allow_nan=False).encode("utf-8"),
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


PREPROCESSING_VERSION = "airsim_1hz_mean_no_interpolation_v3"


def get_json(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            result = json.load(response)
        if result.get("code") != 200:
            raise RuntimeError(str(result))
        return result["data"]
    except urllib.error.URLError as error:
        raise RuntimeError(f"无法读取后台实验记录: {error}") from error


def run_metadata(args, flight_id, frame, prepared, columns):
    # Fingerprint the complete selected, parsed flight table, not its path or replay clock.
    source_hash = hashlib.sha256(frame.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()
    source_path = Path(args.source).expanduser()
    bundle_hash = hashlib.sha256(source_path.read_bytes()).hexdigest() if source_path.is_file() else None
    result = {
        "flightId": flight_id, "droneId": args.drone_id, "droneCode": args.drone_code,
        "dataSource": "AIRSIM", "sourceLabel": source_path.name + " / " + flight_id,
        "sourceSha256": source_hash, "preprocessingVersion": PREPROCESSING_VERSION,
        "expectedSamples": len(prepared),
        "configuration": {
            "sample_period_s": 1, "interpolation": False, "max_samples": args.max_samples,
            "source_timestamp_origin_s": float(pd.to_numeric(frame[columns["timestamp"]]).min()),
            "source_bundle_sha256": bundle_hash, "source_hash_definition": "sha256(parsed_flight_csv_utf8)",
            "soc_source": columns.get("battery_level") or "current_integration_fallback",
            "capacity_source": columns.get("remaining_capacity"), "latitude_origin": args.latitude,
            "longitude_origin": args.longitude, "heading_fallback": args.heading,
            "wind_direction_fallback": args.wind_direction, "nominal_capacity_ah": args.nominal_capacity_ah,
            "start_battery_pct": args.start_battery_pct,
            "position_source": "recorded" if columns.get("latitude") and columns.get("longitude") else "integrated_NED_relative",
        },
    }
    if "v3_provenance" in frame.attrs:
        provenance = frame.attrs["v3_provenance"]
        result["preprocessingVersion"] = provenance["sampling_contract"]
        result["sourceSha256"] = provenance["raw_sha256"]
        result["configuration"].update(provenance)
        result["configuration"]["source_hash_definition"] = "sha256(raw_10hz_csv_bytes)"
        result["configuration"]["timestamp_semantics"] = "completed bin [k,k+1), available at k+1"
    return result


def replay(args, flight_id, frame, columns):
    prepared = prepare_flight(frame, columns, args.max_samples)
    metadata = run_metadata(args, flight_id, frame, prepared, columns)
    base = args.backend_url.rstrip("/")
    if args.run_id:
        run = get_json(base + "/api/runs/" + args.run_id)
        for key in ["flightId", "droneId", "droneCode", "dataSource", "sourceSha256", "preprocessingVersion", "expectedSamples", "configuration"]:
            if run.get(key) != metadata[key]:
                raise ValueError(f"不能续传：已存档的 {key} 与本次输入不一致")
    else:
        response = post_json(base + "/api/runs", metadata)
        if response.get("code") != 200:
            raise RuntimeError(str(response))
        run = response["data"]
    run_id = run["runId"]
    print(f"实验编号 run_id={run_id}", flush=True)
    print(f"架次 {flight_id} | {len(frame)} 条原始数据 | {len(prepared)} 条1Hz记录 | 旧记录全部保留", flush=True)
    started_at = datetime.fromisoformat(run["collectStartTime"])
    battery_level = args.start_battery_pct
    previous_current, previous_source_time = None, None
    synthetic_latitude, synthetic_longitude = args.latitude, args.longitude
    try:
        for sequence, (source_delta, row) in enumerate(prepared.iterrows()):
            source_time = source_delta.total_seconds()
            dt = 0 if previous_source_time is None else source_time - previous_source_time
            current = row_value(row, "current", 0.0)
            if "battery_level" in prepared.columns:
                raw_soc = row.get("battery_level")
                battery_level = None if pd.isna(raw_soc) else float(raw_soc)
            elif previous_current is not None:
                battery_level = max(0.0, battery_level - max(previous_current, 0.0) * dt / 3600.0 / args.nominal_capacity_ah * 100.0)
            previous_current, previous_source_time = current, source_time
            vx, vy, vz = (row_value(row, name, 0.0) for name in ["velocity_x", "velocity_y", "velocity_z"])
            temperature = row_value(row, "temperature", 0.0)
            if columns.get("latitude") and columns.get("longitude"):
                latitude, longitude = row_value(row, "latitude", args.latitude), row_value(row, "longitude", args.longitude)
            else:
                if sequence:
                    synthetic_latitude, synthetic_longitude = advance_gps_from_ned(synthetic_latitude, synthetic_longitude, vx, vy, dt)
                latitude, longitude = synthetic_latitude, synthetic_longitude
            heading = row_value(row, "heading", args.heading) if columns.get("heading") else (
                (math.degrees(math.atan2(vy, vx)) + 360) % 360 if abs(vx) + abs(vy) > .05 else args.heading)
            capacity = row.get("remaining_capacity")
            payload = {
                "runId": run_id, "flightId": flight_id, "sampleSeq": sequence, "sourceTimeS": source_time,
                "droneId": args.drone_id, "droneCode": args.drone_code,
                "latitude": latitude, "longitude": longitude, "altitude": row_value(row, "altitude", 0.0),
                "speed": math.sqrt(vx*vx + vy*vy + vz*vz), "heading": heading,
                "voltage": row_value(row, "voltage", 0.0), "current": current,
                "batteryLevel": None if battery_level is None else round(battery_level, 4),
                "remainingCapacityAh": None if pd.isna(capacity) else float(capacity),
                "batteryTemperature": row_value(row, "battery_temperature", temperature),
                "envTemperature": temperature, "windSpeed": row_value(row, "wind_speed", 0.0),
                "windDirection": row_value(row, "wind_direction", args.wind_direction),
                "collectTime": (started_at + timedelta(seconds=source_time)).strftime("%Y-%m-%dT%H:%M:%S"),
            }
            if "v3_provenance" in frame.attrs:
                for column, name in {"velocity_x": "velocityX", "velocity_y": "velocityY", "velocity_z": "velocityZ",
                                     "wind_x": "windX", "wind_y": "windY", "wind_z": "windZ"}.items():
                    payload[name] = float(row[column])
            result = post_json(base + "/api/telemetry", payload)
            if result.get("code") != 200 or result.get("data") is not True:
                raise RuntimeError(f"遥测上报失败：{result}")
            soc_text = "missing" if battery_level is None else f"{battery_level:.2f}%"
            print(f"[{sequence+1:03d}/{len(prepared):03d}] t={source_time:.0f}s SOC={soc_text} temp={temperature:.1f}°C response=200", flush=True)
            if args.speed > 0 and sequence >= run.get("sampleCount", 0):
                time.sleep(1.0 / args.speed)
        finished = post_json(base + "/api/runs/" + run_id + "/finish", {"status": "COMPLETED"})
        if finished.get("code") != 200:
            raise RuntimeError(str(finished))
        print(f"实验已归档：{run_id}\n指标：{json.dumps(finished['data']['metrics'], ensure_ascii=False)}", flush=True)
        return finished["data"]
    except BaseException as error:
        try:
            post_json(base + "/api/runs/" + run_id + "/finish", {"status": "INTERRUPTED", "error": str(error)[:500]})
        except Exception:
            pass
        print(f"回放中断；已保存记录不会删除。可用 --run-id {run_id} 重新发送同一份数据。", flush=True)
        raise


def build_parser():
    parser = argparse.ArgumentParser(description="选择AirSim架次，重采样至1Hz并向Spring Boot回放")
    parser.add_argument("source", help="新版/旧版AirSim ZIP、CSV或数据目录")
    parser.add_argument("--flight-id", help="架次ID，也可只写数字；省略时选择数据源中的第一个架次")
    parser.add_argument("--run-id", help="续传已有实验；会核对数据指纹和预处理配置，同序号同内容重试不会重复推理")
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
                meta = frame.attrs.get("v3_provenance", {})
                status = meta.get("quarantine_reason") or meta.get("evaluation_role", "legacy_V2")
                print(f"- {flight_id}: {len(frame)} 条原始记录 | {status}")
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
