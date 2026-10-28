"""Export D2 schemas, development inputs, source audit and route probe evidence."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import unittest

import pydantic

from competition.core.curves import CurveLibrary
from competition.core.planning import UPPER_POWER_W, ground_speed
from competition.v2.contracts import (CONTRACT_VERSION, BudgetAssessment, DecisionRecord,
                                      DecisionRequest, LegEstimate, fingerprint)
from competition.v2.planning_inputs import assess_order, build_leg_table, plan_leg
from competition.v2.scenarios import Scenario, development_scenarios, initial_request, observed_grid


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def route_probes(scenarios):
    config = json.loads((Path(__file__).resolve().parents[1] / "data/development_probes.json").read_text())
    scenario = next(s for s in scenarios if s.id == config["scenario_id"])
    goal = next(t.position for t in scenario.tasks if t.id == config["target_id"])
    before = plan_leg(scenario.grid, scenario.base, goal, "BASE", "C", scenario.airspeed_ms, UPPER_POWER_W)
    elapsed, position = 0.0, scenario.base
    # A diagnostic position derived from the pre-event planned path, not telemetry.
    for a, b in zip(before.path, before.path[1:]):
        duration = scenario.grid.cell_size_m / ground_speed(a, b, [w.model_dump() for w in scenario.grid.wind_regions], scenario.airspeed_ms)
        if elapsed + duration > config["observation_s"] + 1e-9:
            break
        elapsed += duration
        position = b
    if abs(elapsed - config["observation_s"]) > 1e-7:
        raise ValueError("probe_event_must_align_with_a_planned_grid_boundary")
    index = before.path.index(position)
    if (8, 3) not in before.path[index + 1:]:
        raise ValueError("north_gate_not_on_unexecuted_probe_suffix")
    baseline = plan_leg(scenario.grid, position, goal, "CURRENT", "C", 5.0, UPPER_POWER_W)
    variants = []
    for event in config["event_variants"]:
        data = scenario.model_dump(mode="json")
        data["scheduled_events"] = [event]
        changed = Scenario.model_validate(data)
        grid = observed_grid(changed, config["observation_s"])
        after = plan_leg(grid, position, goal, "CURRENT", "C", 5.0, UPPER_POWER_W)
        back = plan_leg(grid, goal, scenario.base, "C", "BASE", 5.0, UPPER_POWER_W)
        if event["id"] == "close-north-gate":
            valid = (after.status == "PLANNED" and (8, 9) in after.path
                     and (8, 3) not in after.path and after.distance_m > baseline.distance_m)
        elif event["id"] == "close-both-gates":
            valid = after.status == "UNREACHABLE" and after.energy_wh is None and back.status == "UNREACHABLE"
        else:
            valid = after.status == "PLANNED" and after.energy_wh > baseline.energy_wh
        variants.append({"event": event, "passed": valid, "after": after.model_dump(mode="json"),
                         "return_estimate": back.model_dump(mode="json"),
                         "distance_difference_m": None if after.distance_m is None else after.distance_m - baseline.distance_m})
    return {"scope": config["scope"], "observation_s": config["observation_s"],
            "derived_probe_position": list(position), "actual_flight_executed": False,
            "before": baseline.model_dump(mode="json"), "variants": variants,
            "passed": all(v["passed"] for v in variants)}


def source_audit(learn):
    root = learn.parent
    registry_path = learn / "competition/v2/data/parameter_sources.json"
    registry = json.loads(registry_path.read_text())
    library = CurveLibrary()
    if not library.available:
        raise ValueError(library.reason)
    pdf = root / registry["reference_pdf"]
    pdf_sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if pdf_sha != library.source["sha256"]:
        raise ValueError("reference_pdf_hash_mismatch")
    values = {p["id"]: p["value"] for p in registry["parameters"]}
    if (sorted(library.curves) != values["temperature_nodes"] or library.current_a != values["reference_current"]
            or library.series_cells != values["series_cells"] or abs(UPPER_POWER_W-values["planner_power"]) > 1e-9):
        raise ValueError("parameter_registry_disagrees_with_reference")
    scenarios = development_scenarios()
    for scenario in scenarios:
        if (scenario.grid.cell_size_m != values["grid_size"] or scenario.airspeed_ms != values["airspeed"]
                or scenario.fixed_height_m != values["fixed_height"]
                or any(t.dwell_s != values["task_dwell"] or t.value not in values["task_values"] for t in scenario.tasks)):
            raise ValueError("scenario_parameter_source_mismatch")
    request = initial_request(scenarios[0])
    if (abs(request.budget.reserve_wh - library.reference_wh * values["reserve_fraction"]) > 1e-9
            or request.budget.available_fraction_error != values["available_fraction_error"]
            or request.budget.cost_fraction_error != values["cost_fraction_error"]):
        raise ValueError("budget_parameter_source_mismatch")
    protocol = json.loads((learn / "competition/v2/protocol.json").read_text())
    for profile in protocol["error_profiles"]:
        biased = initial_request(scenarios[0], error_profile=profile["id"])
        if (abs(biased.observation.available_wh_estimate - request.observation.available_wh_estimate / profile["available_hat_divisor"]) > 1e-9
                or abs(biased.model.estimated_power_w - UPPER_POWER_W / profile["planner_power_divisor"]) > 1e-9):
            raise ValueError("error_profile_disagrees_with_protocol")
    source_hashes = {str(p.relative_to(learn)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in [registry_path, library.path]}
    return {"passed": True, "registry": registry, "source_hashes": source_hashes,
            "pdf_sha256": pdf_sha, "no_new_manufacturer_download": True,
            "source_reading_scope": "existing_source_file_and_vector_data_provenance_not_new_physical_calibration",
            "full_reference_wh": {str(t): library.curve(t).energy_between(0, library.curve(t).capacity_ah)
                                  for t in (-20, -10, 0, 23)}}


def verify_v1(root):
    path = root / "output/4C/v2/v1-baseline-lock.json"
    lock = json.loads(path.read_text())
    changed = [f["path"] for f in lock["files"]
               if hashlib.sha256((root / f["path"]).read_bytes()).hexdigest() != f["sha256"]]
    return {"passed": not changed, "checked_files": len(lock["files"]), "changed_files": changed,
            "formal_archives": lock["formal_runs_preserved"], "lock_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if CONTRACT_VERSION != "competition-v2-contract-0.2":
        parser.error("D2 is a historical 0.2 entry. Use competition.v2.tools.prepare_day11 for 0.3; D2 source is preserved under output/4C/v2/day11/before/source.")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    learn = Path(__file__).resolve().parents[3]
    scenarios = development_scenarios()
    schemas = {model.__name__: model.model_json_schema() for model in
               (DecisionRequest, DecisionRecord, BudgetAssessment, LegEstimate, Scenario)}
    for name, schema in schemas.items():
        write_json(out / "schemas" / (name + ".schema.json"), schema)
    examples = []
    for scenario in scenarios:
        request = initial_request(scenario)
        legs = build_leg_table(request)
        write_json(out / "examples" / (scenario.id + ".request.json"), request.model_dump(mode="json"))
        write_json(out / "examples" / (scenario.id + ".legs.json"), [x.model_dump(mode="json") for x in legs.values()])
        budgets = {task.id: assess_order(request, legs, (task.id,)).model_dump(mode="json") for task in scenario.tasks}
        write_json(out / "examples" / (scenario.id + ".single-task-budgets.json"), budgets)
        temperature_rows = []
        for temperature in (0.0, -10.0, -20.0):
            req = initial_request(scenario, temperature_c=temperature)
            temperature_rows.append({"temperature_c": temperature, "available_wh_estimate": req.observation.available_wh_estimate,
                                     "reserve_wh": req.budget.reserve_wh, "input_sha256": fingerprint(req)})
        examples.append({"scenario_id": scenario.id, "task_count": len(scenario.tasks), "directed_legs": len(legs),
                         "request_sha256": fingerprint(request), "temperature_rows": temperature_rows})
    write_json(out / "route-probes.json", probes := route_probes(scenarios))
    write_json(out / "parameter-audit.json", sources := source_audit(learn))
    write_json(out / "v1-preservation.json", old := verify_v1(learn.parent))
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName("competition.v2.tests.test_contracts")
    tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (out / "tests.txt").write_text(stream.getvalue(), encoding="utf-8")
    source_files = [p for p in (learn / "competition/v2").rglob("*")
                    if p.is_file() and p.suffix in {".py", ".json", ".md"}]
    report = {"date": "2026-10-10", "contract_version": CONTRACT_VERSION,
              "scope": "D2_development_contract_and_route_probes_not_full_v2_execution",
              "passed": tests.wasSuccessful() and probes["passed"] and sources["passed"] and old["passed"],
              "python_version": platform.python_version(), "pydantic_version": pydantic.__version__,
              "tests": {"run": tests.testsRun, "failures": len(tests.failures), "errors": len(tests.errors), "skipped": len(tests.skipped)},
              "schemas": list(schemas), "development_examples": examples,
              "source_sha256": {str(p.relative_to(learn)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source_files)},
              "formal_v2_executions": 0, "real_flights": 0,
              "need_intake_files": [str(p.relative_to(learn.parent)) for p in
                                    sorted((learn.parent / "output/4C/v2/needs").glob("*")) if p.is_file() and p.name != "README.md"],
              "remaining": ["real_need_feedback", "subset_dp_and_baselines", "runtime_executor_integration", "formal_holdout_runs", "web_v2_integration"]}
    write_json(out / "report.json", report)
    print(json.dumps({"passed": report["passed"], "tests": report["tests"], "maps": len(examples),
                      "route_probe_before_m": probes["before"]["distance_m"],
                      "route_probe_after_m": probes["variants"][0]["after"]["distance_m"],
                      "output": str(out)}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
