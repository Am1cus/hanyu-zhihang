"""Two-phase, non-destructive restart acceptance against an isolated demo DB.

Run prepare, stop/restart the same database, then run verify. This tool never
stops services itself. Original predictions and model files are not modified.
"""
import argparse
import copy
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Phase4.replay_airsim import get_json, post_json
from Phase4.accept_energy_v3 import read_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "verify"])
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    base = args.backend_url.rstrip("/")
    batch = json.loads((args.batch / "report.json").read_text())
    if args.mode == "prepare":
        if args.state.exists(): parser.error("State already exists")
        reference = next(f for f in batch["flights"] if f["flight_id"] == "F022")
        source = get_json(f"{base}/api/runs/{reference['run_id']}")
        request = copy.deepcopy({k: source[k] for k in (
            "flightId", "droneId", "droneCode", "dataSource", "sourceLabel",
            "sourceSha256", "preprocessingVersion", "configuration")})
        request["expectedSamples"] = 40
        request["sourceLabel"] += " / restart engineering test"
        request["configuration"]["engineering_test"] = "restart_after_29_samples"
        run = post_json(base + "/api/runs", request)["data"]
        events = read_events(base, reference["run_id"])
        samples = []
        for event in events[:40]:
            row = copy.deepcopy(event["telemetry"])
            for key in ("id", "createTime", "payloadSha256"): row.pop(key, None)
            row["runId"] = run["runId"]
            row["collectTime"] = (datetime.fromisoformat(run["collectStartTime"])
                                  + timedelta(seconds=row["sourceTimeS"])).isoformat()
            samples.append(row)
        for row in samples[:29]: post_json(base + "/api/telemetry", row)
        before = read_events(base, run["runId"])
        assert len(before) == 29 and all(not e["prediction"]["valid"] for e in before)
        state = {"run_id": run["runId"], "samples": samples, "events_before": before}
        args.state.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        print("Prepared 29 persisted rows. Restart the same isolated DB, then verify.")
    else:
        output = args.state.with_name(args.state.stem + "-result.json")
        if output.exists(): parser.error("Result already exists")
        state = json.loads(args.state.read_text())
        report = {"scope": "real_three_service_restart_same_H2_database", "checks": {}, "run_id": state["run_id"]}
        try:
            for flight in batch["flights"]:
                saved = json.loads((args.batch / f"{flight['flight_id']}-events.json").read_text())
                assert read_events(base, flight["run_id"]) == saved
                restored = get_json(f"{base}/api/runs/{flight['run_id']}")
                assert restored["baselineMetrics"] == flight["baseline_metrics"]
            report["checks"]["all_20_archives_and_metrics_unchanged"] = True
            rid = state["run_id"]
            assert read_events(base, rid) == state["events_before"]
            for row in state["samples"][29:]: post_json(base + "/api/telemetry", row)
            events = read_events(base, rid)
            assert len(events) == 40 and events[29]["prediction"]["valid"]
            assert events[29]["prediction"]["window_samples"] == 30
            assert events[29]["verification"]["status"] == "verified"
            report["checks"]["window_restored_29_plus_1_and_future_label"] = True
            original_predictions = [e["prediction"] for e in events]
            check = post_json(f"{base}/api/runs/{rid}/recheck?sampleSeq=29", {})["data"]
            assert check["consistent"]
            assert [e["prediction"] for e in read_events(base, rid)] == original_predictions
            report["checks"]["recheck_after_restart_preserves_prediction"] = True
            post_json(f"{base}/api/runs/{rid}/finish", {"status": "COMPLETED"})
            report["all_passed"] = True
        except BaseException as error:
            report.update(all_passed=False, error=str(error))
            raise
        finally:
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
