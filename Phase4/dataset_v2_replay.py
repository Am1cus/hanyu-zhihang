"""Read-only manifest adapter for the delivered raw-10Hz AirSim batch.

Reuse the frozen experiment's binning implementation, not the supplied nearest
sample 1Hz export. Frame attrs carry provenance, never model features/labels.
"""
import hashlib
import io
import json
import re
from pathlib import PurePosixPath

import pandas as pd
from Phase4.capacity_v3 import aggregate_raw, GROUND
from Phase4.energy_v3_service import CONTRACT, DOMAIN, MODEL

KNOWN_BUNDLE = "071a43e240ea48c9c3395cfd2da48642d938b436e63770cbd7411dbf9b7971f4"


def load_manifest_flights(archive, bundle_hash):
    manifests = [n for n in archive.namelist() if PurePosixPath(n).name == "dataset_manifest_batch.json"]
    if not manifests:
        return None
    if len(manifests) != 1:
        raise ValueError("需要唯一的批次manifest")
    batch_bytes = archive.read(manifests[0])
    batch = json.loads(batch_bytes)
    root = PurePosixPath(manifests[0]).parent
    result, seen = [], set()
    for entry in batch["flights"]:
        flight = entry["flight_id"]
        if not isinstance(flight, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", flight) or flight in seen:
            raise ValueError("重复或不合法的manifest架次ID")
        seen.add(flight)
        prefix = root / ("flight_" + flight)
        meta_bytes = archive.read(str(prefix / "manifest.json"))
        meta = json.loads(meta_bytes)
        if meta["flight_id"] != flight or meta.get("sample_rate_hz") != 10:
            raise ValueError("架次manifest身份或采样率不匹配: " + flight)
        member = str(prefix / "flights" / (flight + "_raw_10Hz.csv"))
        raw_bytes = archive.read(member)
        raw = pd.read_csv(io.BytesIO(raw_bytes))
        if raw.empty or set(raw.flight_id) != {flight}:
            raise ValueError("原始CSV架次身份不匹配: " + flight)
        if entry.get("end_reason") != meta.get("end_reason"):
            raise ValueError("批次和架次终止原因不一致: " + flight)
        reason = ("suspected_ground_record_pending_source_verification" if bundle_hash == KNOWN_BUNDLE and flight in GROUND
                  else (meta.get("end_reason") or "missing_end_reason") if meta.get("end_reason") != "battery_threshold_reached" else None)
        split = batch.get("split", {}).get(flight, "unspecified")
        raw.attrs["v3_provenance"] = {
            "inference_method": MODEL, "execution_mode": "research_shadow",
            "sampling_contract": CONTRACT, "battery_data_domain": DOMAIN,
            "source_bundle_sha256": bundle_hash, "raw_member": member,
            "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "batch_manifest_sha256": hashlib.sha256(batch_bytes).hexdigest(),
            "flight_manifest_sha256": hashlib.sha256(meta_bytes).hexdigest(),
            "source_split": split,
            "evaluation_role": ("training" if split == "train" else "development_validation" if split in {"val", "validation"}
                                else "exploratory_" + split) if bundle_hash == KNOWN_BUNDLE else "unconfirmed_new_data",
            "end_reason": meta.get("end_reason"), "quarantine_reason": reason,
            "track": meta.get("track"), "ambient_temp_c": entry.get("ambient_temp_c"),
            "nominal_capacity_ah": meta.get("battery", {}).get("nominal_capacity_ah"),
            "coordinate_system": meta.get("coordinate_system"),
            "position_source": "airsim_home_plus_displacement_approximation",
            "independent_confirmation": False,
        }
        result.append((flight, raw))
    return result


def prepare_v3(frame, columns, max_samples=None):
    provenance = frame.attrs["v3_provenance"]
    if provenance["quarantine_reason"]:
        raise ValueError("架次已隔离，不能作为正常V3回放: " + provenance["quarantine_reason"])
    aggregated = aggregate_raw(frame)
    # Drop incomplete bins but retain their source-clock gap, never interpolate.
    numeric = pd.DataFrame({key: aggregated[source] for key, source in columns.items() if source})
    required = ["current", "wind_speed", "velocity_x", "velocity_y", "velocity_z", "wind_x", "wind_y", "wind_z", "remaining_capacity"]
    numeric.index = pd.to_timedelta(aggregated.available_at_s, unit="s")
    numeric = numeric.dropna(subset=required).drop(columns=["timestamp"])
    if max_samples is not None:
        numeric = numeric.iloc[:max_samples]
    if numeric.empty:
        raise ValueError("没有完整的一秒遥测桶")
    return numeric
