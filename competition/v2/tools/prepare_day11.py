"""Export the 2026-10-11 requirement revision and development checks, not flights."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import platform
import time
import unittest

import pydantic

from competition.v2.contracts import (
    CONTRACT_VERSION, BudgetAssessment, DecisionRecord, DecisionRequest,
    LegEstimate, fingerprint, validate_decision_for_request,
)
from competition.v2.planning_inputs import assess_order, build_leg_table
from competition.v2.scenarios import Scenario, development_scenarios, initial_request
from competition.v2.tools.prepare_day2 import route_probes, source_audit, verify_v1, write_json


def history_check(root):
    """Historical artifacts are immutable; current source may legitimately change."""
    before = root / "output/4C/v2/day11/before/manifest.json"
    saved = json.loads(before.read_text())
    bad = [row["snapshot"] for row in saved["files"]
           if hashlib.sha256((root / row["snapshot"]).read_bytes()).hexdigest() != row["sha256"]]
    day2 = root / "output/4C/v2/day2"
    audit = json.loads((day2 / "delivery-audit.json").read_text())
    bad.extend(str(day2 / rel) for rel, digest in audit["artifact_sha256"].items()
               if hashlib.sha256((day2 / rel).read_bytes()).hexdigest() != digest)
    return {"passed": not bad, "changed_historical_files": bad,
            "source_snapshots": len(saved["files"]), "day2_artifacts": len(audit["artifact_sha256"])}


def need_records(root):
    directory = root / "output/4C/v2/needs"
    rows = []
    for name, prefix, count in (("need-01.md", "R1", 7), ("need-02.md", "R2", 6)):
        path = directory / name
        content = path.read_text()
        ids = [f"{prefix}-{i:02d}" for i in range(1, count + 1)]
        if "PUBLIC_SOURCE_REVIEW" not in content or "非访谈" not in content or any(i not in content for i in ids):
            raise ValueError("requirement_record_missing_identity_or_ids")
        rows.append({"path": str(path.relative_to(root)), "record_type": "PUBLIC_SOURCE_REVIEW",
                     "requirement_ids": ids, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    # This is the declared scope of these two records, not automatic classification of other files.
    return {"public_source_records": rows, "interviews_represented_by_these_records": 0,
            "external_operator_validation": "PENDING"}


def development_checks(scenarios, probes):
    variants = {row["event"]["id"]: row for row in probes["variants"]}
    expected_ids = {"close-north-gate", "close-both-gates", "east-gust"}
    if set(variants) != expected_ids or len(probes["variants"]) != len(expected_ids):
        raise ValueError("development_probe_set_mismatch")
    if variants["east-gust"]["event"]["type"] != "wind":
        raise ValueError("development_gust_probe_type_mismatch")
    warm = initial_request(scenarios[0], temperature_c=0.0)
    cold = initial_request(scenarios[0], temperature_c=-20.0)
    start = time.perf_counter()
    low = initial_request(scenarios[0], initial_soc=0.1, selector="fixed_order")
    legs = build_leg_table(low)
    single = {task.id: assess_order(low, legs, [task.id]) for task in low.task_catalog}
    empty = assess_order(low, legs, [])
    if any(b.status != "INSUFFICIENT" for b in single.values()) or empty.status != "INSUFFICIENT":
        raise ValueError("low_budget_fixture_not_uniformly_insufficient")
    record = DecisionRecord(
        contract_version=CONTRACT_VERSION, request_sha256=fingerprint(low), as_of_s=0.0,
        selector_id=low.selector_id, budget_mode=low.budget.mode,
        action="REFUSED", reason_code="NO_FEASIBLE_TASK", ordered_task_ids=(),
        deferred_tasks=tuple({"id": task.id, "reason": "BUDGET", "follow_up_state": "REQUIRES_OPERATOR_REVIEW"}
                             for task in low.task_catalog),
        budget=empty, computation_ms=(time.perf_counter() - start) * 1000,
    )
    validate_decision_for_request(low, record)
    unavailable = initial_request(scenarios[0], temperature_c=-30.0)
    unknown_budget = assess_order(unavailable, build_leg_table(unavailable), ["C"])
    checks = [
        {"id": "SC-01", "kind": "temperature_pair", "passed": cold.observation.available_wh_estimate < warm.observation.available_wh_estimate
         and cold.budget.reserve_wh == warm.budget.reserve_wh,
         "warm_available_wh": warm.observation.available_wh_estimate,
         "cold_available_wh": cold.observation.available_wh_estimate, "reserve_wh": cold.budget.reserve_wh},
        {"id": "SC-02", "kind": "low_budget_given_order", "passed": single["C"].status == "INSUFFICIENT",
         "assessment": single["C"].model_dump(mode="json")},
        {"id": "SC-03", "kind": "north_exclusion", "passed": variants["close-north-gate"]["passed"],
         "before_m": probes["before"]["distance_m"], "after_m": variants["close-north-gate"]["after"]["distance_m"]},
        {"id": "SC-04", "kind": "both_exclusions", "passed": variants["close-both-gates"]["passed"]},
        {"id": "SC-05", "kind": "observed_gust", "passed": variants["east-gust"]["passed"]},
        {"id": "SC-06", "kind": "outside_reference_temperature", "passed": unavailable.observation.data_status == "UNAVAILABLE"
         and unknown_budget.status == "UNAVAILABLE" and unknown_budget.margin_wh is None,
         "reason": unavailable.observation.unavailable_reason},
    ]
    return ({"scope": "development_inputs_and_planning_only", "passed": all(c["passed"] for c in checks), "checks": checks},
            {"scope": "low_budget_contract_fixture_not_a_selector_or_execution_result",
             "request": low.model_dump(mode="json"), "record": record.model_dump(mode="json"),
             "actually_flown": False, "operator_acceptance_recorded": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verified-on", type=date.fromisoformat, required=True,
                        help="Actual verification date, YYYY-MM-DD; separate from the October 11 work item")
    args = parser.parse_args()
    learn = Path(__file__).resolve().parents[3]
    root = learn.parent
    out = args.output.resolve()
    for protected in (root / "output/4C/v2/day2", root / "output/4C/v2/day11/before",
                      root / "output/4C/v2/day11/checkpoint-20261011"):
        if out == protected or protected in out.parents:
            parser.error("output must not overwrite historical evidence")
    out.mkdir(parents=True, exist_ok=True)
    scenarios = development_scenarios()
    schemas = (DecisionRequest, DecisionRecord, BudgetAssessment, LegEstimate, Scenario)
    for model in schemas:
        write_json(out / "schemas" / f"{model.__name__}.schema.json", model.model_json_schema())
    examples = []
    for scenario in scenarios:
        request = initial_request(scenario)
        legs = build_leg_table(request)
        write_json(out / "examples" / f"{scenario.id}.request.json", request.model_dump(mode="json"))
        write_json(out / "examples" / f"{scenario.id}.legs.json", [leg.model_dump(mode="json") for leg in legs.values()])
        write_json(out / "examples" / f"{scenario.id}.single-task-budgets.json",
                   {t.id: assess_order(request, legs, [t.id]).model_dump(mode="json") for t in scenario.tasks})
        examples.append({"scenario_id": scenario.id, "label": scenario.label, "task_count": len(scenario.tasks),
                         "tasks": [{"id": t.id, "label": t.label} for t in scenario.tasks],
                         "request_sha256": fingerprint(request), "directed_legs": len(legs)})
    probes = route_probes(scenarios)
    checks, fixture = development_checks(scenarios, probes)
    write_json(out / "route-probes.json", probes)
    write_json(out / "development-checks.json", checks)
    write_json(out / "examples/low-budget-record-fixture.json", fixture)
    write_json(out / "parameter-audit.json", sources := source_audit(learn))
    write_json(out / "history-preservation.json", history := history_check(root))
    write_json(out / "v1-preservation.json", v1 := verify_v1(root))
    needs = need_records(root)
    write_json(out / "requirements-index.json", needs)
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(learn / "competition/v2/tests"), pattern="test_*.py", top_level_dir=str(learn))
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (out / "tests.txt").write_text(stream.getvalue(), encoding="utf-8")
    files = sorted(p for p in (learn / "competition/v2").rglob("*") if p.is_file() and p.suffix in {".py", ".md", ".json"})
    report = {
        "date": args.verified_on.isoformat(), "work_item_date": "2026-10-11",
        "contract_version": CONTRACT_VERSION,
        "scope": "public_needs_and_development_contract_revision_not_full_v2_execution",
        "passed": result.wasSuccessful() and all(x["passed"] for x in (checks, probes, sources, history, v1)),
        "python_version": platform.python_version(), "pydantic_version": pydantic.__version__,
        "tests": {"run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped)},
        "development_cases": len(checks["checks"]), "schemas": [m.__name__ for m in schemas],
        "development_examples": examples, "needs": needs,
        "source_sha256": {str(p.relative_to(learn)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "formal_v2_executions": 0, "real_flights": 0, "website_version": "v1",
    }
    write_json(out / "report.json", report)
    print(json.dumps({"passed": report["passed"], "tests": report["tests"], "development_cases": report["development_cases"],
                      "public_need_records": len(needs["public_source_records"]), "output": str(out)}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
