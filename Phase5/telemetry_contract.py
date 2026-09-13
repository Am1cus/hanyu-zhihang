"""Offline MQTT envelope validation. No broker subscription or drone commands."""
import argparse
import json
import math
from pathlib import Path

SAMPLING = "completed_1hz_bin_means_right_boundary_v1"


def decode(topic, payload, registered_run):
    """Bind a message to previously registered run/drone identities.

    Missing sensor values are preserved so the backend can archive them and mark
    prediction unavailable. This gate does NOT declare model inputs valid.
    """
    if not isinstance(payload, (str, bytes)) or len(payload.encode() if isinstance(payload, str) else payload) > 65536:
        raise ValueError("payload must be JSON <=64KiB")
    parts = topic.split("/")
    if len(parts) != 6 or parts[:2] != ["cold-aviation", "v1"] or parts[3] != "runs" or parts[5] != "telemetry":
        raise ValueError("invalid topic")
    if not all(parts[i] and all(c.isascii() and (c.isalnum() or c in "-_") for c in parts[i]) for i in (2,4)):
        raise ValueError("invalid topic identifier")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("nonfinite JSON number")
    envelope = json.loads(payload, object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(envelope, dict) or set(envelope) != {"schema_version", "sampling_contract", "telemetry"}:
        raise ValueError("invalid envelope fields")
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1 or envelope["sampling_contract"] != SAMPLING:
        raise ValueError("unsupported schema or sampling contract")
    row = envelope["telemetry"]
    if not isinstance(row, dict):
        raise ValueError("telemetry object required")
    if set(row) & {"id", "createTime", "payloadSha256", "prediction", "verification"}:
        raise ValueError("server-owned fields are not accepted from devices")
    if registered_run.get("sampling_contract") != SAMPLING or registered_run.get("status") != "RUNNING":
        raise ValueError("run not open for this sampling contract")
    for key in ("droneCode", "runId", "flightId", "droneId"):
        if row.get(key) is None or row[key] != registered_run.get(key):
            raise ValueError("message and registered run identity mismatch: " + key)
    if parts[2] != row["droneCode"] or parts[4] != row["runId"]:
        raise ValueError("topic and payload identity mismatch")
    if type(row["droneId"]) is not int or row["droneId"] < 1:
        raise ValueError("invalid droneId")
    if type(row.get("sampleSeq")) is not int or row["sampleSeq"] < 0:
        raise ValueError("sampleSeq must be nonnegative integer")
    t = row.get("sourceTimeS")
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 1 or not float(t).is_integer():
        raise ValueError("sourceTimeS must be a completed second right boundary")
    # Strict serialization also catches overflowing exponents (1e999).
    json.dumps(row, allow_nan=False)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic")
    parser.add_argument("payload", type=Path)
    parser.add_argument("registered_run", type=Path)
    args = parser.parse_args()
    row = decode(args.topic, args.payload.read_bytes(), json.loads(args.registered_run.read_text()))
    print(json.dumps({"status": "envelope_valid", "telemetry": row,
                      "forwarded": False, "sensor_quality": "backend_must_check"}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
