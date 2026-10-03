"""Independent raw-telemetry audit, without importing the numerical integrator.

Checks exported V/I/t, Ah, energy conservation, returned position and cardinal
movement against actual applied obstacles. Run from the directory above competition.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def audit(path):
    exported = json.loads(path.read_text(encoding="utf-8"))
    telemetry, summary = exported["telemetry"], exported["summary"]
    scenario = exported["configuration"]["scenario"]
    wh = sum((a["voltage_v"] * a["current_a"] + b["voltage_v"] * b["current_a"]) * .5
             * (b["t_s"] - a["t_s"]) / 3600 for a, b in zip(telemetry, telemetry[1:]))
    ah = sum((a["current_a"] + b["current_a"]) * .5 * (b["t_s"] - a["t_s"]) / 3600
             for a, b in zip(telemetry, telemetry[1:]))
    wh_error = abs(wh - summary["total_energy_wh"])
    ah_error = abs(ah - telemetry[-1]["discharged_ah"])
    balance_error = abs(summary["initial_usable_wh"] - summary["total_energy_wh"] - summary["remaining_usable_wh"])
    if wh_error > 1e-7 or ah_error > 1e-7 or balance_error > 1e-7:
        raise ValueError(f"Energy/charge identity failed: {path.name}")
    returned_distance = math.dist(telemetry[-1]["position"], scenario["start"])
    if summary["returned"] and returned_distance > 1e-7:
        raise ValueError(f"Returned before physically reaching base: {path.name}")
    blocked = {tuple(p) for p in scenario["blocked"]}
    obstacles = sorted((e for e in exported["events"] if e["applied"] and e["type"] == "obstacle"), key=lambda e: e["t_s"])
    wind_vectors = [r["vector"] for r in scenario["wind_regions"]] + [e["payload"]["wind"] for e in exported["events"] if e["applied"] and e["type"] == "wind"]
    speed_bound = scenario["airspeed_ms"] + max((math.hypot(*v) for v in wind_vectors), default=0)
    event_index = 0
    for sample in telemetry:
        while event_index < len(obstacles) and obstacles[event_index]["t_s"] <= sample["t_s"] + 1e-9:
            blocked.update(tuple(p) for p in obstacles[event_index]["payload"]["cells"])
            event_index += 1
        x, y = sample["position"]
        # Obstacles are blocked grid nodes; four-neighbour edges have free endpoints.
        endpoints = {(math.floor(x + 1e-8), math.floor(y + 1e-8)),
                     (math.ceil(x - 1e-8), math.ceil(y - 1e-8))}
        if blocked.intersection(endpoints):
            raise ValueError(f"Telemetry enters a blocked node or edge: {path.name}")
    for a, b in zip(telemetry, telemetry[1:]):
        dx, dy = abs(a["position"][0] - b["position"][0]), abs(a["position"][1] - b["position"][1])
        if dx > 1e-8 and dy > 1e-8:
            raise ValueError(f"Non-cardinal movement: {path.name}")
        if dx + dy > speed_bound * (b["t_s"] - a["t_s"]) / scenario["cell_size_m"] + 1e-7:
            raise ValueError(f"Physical position discontinuity: {path.name}")
    return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "samples": len(telemetry), "raw_integral_wh": wh, "raw_integral_ah": ah,
            "wh_error": wh_error, "ah_error": ah_error, "energy_balance_error_wh": balance_error,
            "returned_distance_grid": returned_distance, "trajectory_check": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    files = sorted(args.directory.glob("*.json"))
    if not files:
        raise ValueError("No raw run exports found")
    rows = [audit(p) for p in files]
    report = {"method": "Independent exported trapezoidal V*I*time, charge integral and obstacle endpoint check",
              "tolerance_wh_ah": 1e-7, "execution_count": len(rows), "passed": True,
              "maximum_wh_error": max(r["wh_error"] for r in rows),
              "maximum_ah_error": max(r["ah_error"] for r in rows), "runs": rows,
              "limitation": "Software numerical consistency only; not physical drone validation"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "runs"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
