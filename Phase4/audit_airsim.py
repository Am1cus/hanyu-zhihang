import argparse
import io
import json
import statistics
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


ALIASES = {
    "timestamp": ["timestamp", "time", "timestamp_s"],
    "voltage": ["voltage", "voltage_V"],
    "current": ["current", "current_A"],
    "temperature": ["ambient_temp", "env_temperature", "temperature_C"],
    "wind_speed": ["wind_speed", "wind_speed_ms"],
    "velocity_x": ["velocity_x", "vx"],
    "velocity_y": ["velocity_y", "vy"],
    "velocity_z": ["velocity_z", "vz"],
    "altitude": ["altitude", "altitude_m"],
    "battery_level": ["battery_level", "soc_pct", "battery_level_pct"],
    "end_reason": ["flight_end_reason", "end_reason", "termination_reason"],
}
MIN_FLIGHTS = 20


def canonical_columns(columns):
    available = set(columns)
    return {
        canonical: next((name for name in candidates if name in available), None)
        for canonical, candidates in ALIASES.items()
    }


def load_flights(source):
    source = Path(source).expanduser().resolve()
    if source.suffix.lower() == ".zip":
        with ZipFile(source) as archive:
            members = sorted(
                name for name in archive.namelist()
                if Path(name).name.lower().startswith(("raw", "flight_"))
                and name.lower().endswith(".csv")
            )
            flights = []
            for name in members:
                frame = pd.read_csv(io.BytesIO(archive.read(name)))
                flight_id = (
                    str(frame["flight_id"].iloc[0])
                    if "flight_id" in frame.columns and not frame.empty
                    else Path(name).stem
                )
                flights.append((flight_id, frame))
            return flights
    if source.is_dir():
        paths = sorted(set(source.glob("raw*.csv")) | set(source.glob("flight_*.csv")))
        flights = []
        for path in paths:
            frame = pd.read_csv(path)
            flight_id = (
                str(frame["flight_id"].iloc[0])
                if "flight_id" in frame.columns and not frame.empty
                else path.stem
            )
            flights.append((flight_id, frame))
        return flights
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source)
        flight_column = "flight_id" if "flight_id" in frame.columns else None
        if flight_column:
            return [(str(key), group.copy()) for key, group in frame.groupby(flight_column)]
        return [(source.stem, frame)]
    raise ValueError(f"不支持的数据源：{source}")


def audit(source):
    flights = load_flights(source)
    source_name = Path(source).expanduser().name
    details = []
    all_columns = set()
    for flight_id, frame in flights:
        all_columns.update(frame.columns)
        columns = canonical_columns(frame.columns)
        timestamp_name = columns["timestamp"]
        timestamps = frame[timestamp_name].astype(float) if timestamp_name else pd.Series(dtype=float)
        intervals = timestamps.diff().dropna()
        details.append({
            "flight_id": flight_id,
            "rows": int(len(frame)),
            "duration_s": round(float(timestamps.iloc[-1] - timestamps.iloc[0]), 3) if len(timestamps) > 1 else None,
            "median_hz": round(float(1 / intervals.median()), 3) if len(intervals) and intervals.median() > 0 else None,
            "missing_cells": int(frame.isna().sum().sum()),
            "duplicate_timestamps": int(timestamps.duplicated().sum()) if timestamp_name else None,
            "constant_columns": [column for column in frame.columns if frame[column].nunique(dropna=False) <= 1],
            "columns": list(frame.columns),
        })

    mapped = canonical_columns(all_columns)
    required_signals = [
        "timestamp", "voltage", "current", "temperature", "wind_speed",
        "velocity_x", "velocity_y", "velocity_z", "altitude", "battery_level",
    ]
    missing_signals = [name for name in required_signals if not mapped[name]]
    end_label_available = bool(mapped["end_reason"])
    blockers = []
    if len(flights) < MIN_FLIGHTS:
        blockers.append(f"独立架次仅{len(flights)}个，少于训练门槛{MIN_FLIGHTS}个")
    if missing_signals:
        blockers.append("缺少必要字段：" + ", ".join(missing_signals))
    if not end_label_available:
        blockers.append("缺少真实耗尽、返航或任务结束原因，文件末尾不能直接视为可飞时间终点")

    voltage_columns = [mapped["voltage"]] if mapped["voltage"] else []
    voltage_ranges = []
    for _, frame in flights:
        if voltage_columns and voltage_columns[0] in frame:
            series = frame[voltage_columns[0]].astype(float)
            voltage_ranges.append(float(series.max() - series.min()))
    if voltage_ranges and max(voltage_ranges) < 0.05:
        blockers.append("所有架次电压几乎恒定，无法学习电池衰减过程")

    return {
        "source": source_name,
        "flight_count": len(flights),
        "total_rows": sum(item["rows"] for item in details),
        "median_sample_hz": round(statistics.median(
            item["median_hz"] for item in details if item["median_hz"] is not None
        ), 3) if details else None,
        "canonical_columns": mapped,
        "training_ready": not blockers,
        "blockers": blockers,
        "flights": details,
    }


def write_report(result, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "airsim_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    status = "通过" if result["training_ready"] else "未通过"
    blockers = "\n".join(f"- {item}" for item in result["blockers"]) or "- 无"
    rows = "\n".join(
        f"| {item['flight_id']} | {item['rows']} | {item['duration_s']} | {item['median_hz']} | {item['missing_cells']} |"
        for item in result["flights"]
    )
    report = f"""# AirSim 数据审计报告

- 数据源：`{result['source']}`
- 独立架次：{result['flight_count']}
- 总记录数：{result['total_rows']}
- 中位采样率：{result['median_sample_hz']} Hz
- 飞行时间模型训练门禁：**{status}**

## 阻塞项

{blockers}

## 架次明细

| 架次 | 记录数 | 时长(s) | 采样率(Hz) | 缺失单元格 |
| --- | ---: | ---: | ---: | ---: |
{rows}

## 结论

只有在门禁通过后，才允许生成“剩余可飞时间”训练集和V2模型。当前容量模型V1继续保留，不能将本数据的文件末尾当作真实电池耗尽标签。
"""
    (output_dir / "airsim_audit_report.md").write_text(report, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="审计AirSim飞行遥测是否满足V2训练要求")
    parser.add_argument("source", help="AirSim zip、CSV或包含raw*.csv的目录")
    parser.add_argument("--output-dir", default=str(Path(__file__).parent / "reports"))
    args = parser.parse_args()
    result = audit(args.source)
    write_report(result, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["training_ready"] else 2)


if __name__ == "__main__":
    main()
