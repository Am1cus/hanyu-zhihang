"""Capture deliberately separate failure/information-limit cases for the defence."""
import copy
import json
from pathlib import Path
import sys

from competition.core.curves import CurveLibrary
from competition.core.scenarios import get_scenario
from competition.core.simulator import MissionRun


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    library = CurveLibrary()
    config = {"scenario_id": "normal-s1", "strategy": "energy", "temperature_c": -10}
    cases = []

    missing = MissionRun(config, CurveLibrary(output / "intentionally-absent-reference.json"))
    assert missing.status == "UNAVAILABLE" and missing.initial_wh is None
    cases.append(("missing_reference", missing))

    outside = MissionRun({**config, "temperature_c": -30}, library)
    assert outside.status == "UNAVAILABLE"
    cases.append(("temperature_not_covered", outside))

    inaccessible = get_scenario("normal-s1")
    inaccessible["blocked"].append(inaccessible["targets"][0])
    unreachable = MissionRun({**config, "scenario": inaccessible}, library).run_all()
    assert unreachable.returned and not unreachable.visited_targets
    assert any(d["reason"] == "next_task_unreachable" for d in unreachable.decisions)
    cases.append(("blocked_first_target", unreachable))

    # A severe unforeseen wind change on an occupied edge causes a true failure.
    # It is a boundary test, not one of the 24 formal frozen scenarios.
    scenario = get_scenario("normal-s1")
    scenario["wind_regions"][0].update(x_min=0, x_max=21, y_min=0, y_max=13, vector=[0, 0])
    severe = MissionRun({**config, "scenario": scenario}, library)
    severe.advance(.5)
    a, b = severe.path[:2]
    dx, dy = b[0] - a[0], b[1] - a[1]
    severe.apply_event({"type": "wind", "wind": [-dy * 6, dx * 6]})
    severe.advance(1)
    assert severe.status == "FAILED" and not severe.returned
    assert severe.ended_reason == "wind_exceeds_track_hold_model"
    cases.append(("sudden_crosswind_failure", severe))

    rows = []
    for name, run in cases:
        filename = f"{name}.json"
        (output / filename).write_text(json.dumps(run.export(), ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append({"case": name, "file": filename, "status": run.status, "reason": run.ended_reason,
                     "returned": run.returned, "visited_count": len(run.visited_targets), "formal_case": False})
    report = {"purpose": "Separate boundary cases, excluded from the formal 24-case denominator", "cases": rows}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
