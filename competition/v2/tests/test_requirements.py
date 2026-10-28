"""Business-scope gates and request/decision accounting, without a task selector."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from competition.v2.contracts import (
    CONTRACT_VERSION, DecisionRecord, DecisionRequest, DeferredTask, GridMap,
    Task, fingerprint, validate_decision_for_request,
)
from competition.v2.planning_inputs import assess_order, build_leg_table
from competition.v2.scenarios import development_scenarios, initial_request
from competition.v2.tools.prepare_day11 import development_checks
from competition.v2.tools.prepare_day2 import route_probes


V2 = Path(__file__).resolve().parents[1]


class RequirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maps = development_scenarios()

    def request(self, *, mode="nominal", completed=(), position=None, temperature=-10.0):
        value = initial_request(self.maps[0], initial_soc=1.0, budget_mode=mode,
                                temperature_c=temperature).model_dump(mode="json")
        value["observation"]["completed_task_ids"] = list(completed)
        if position is not None:
            value["observation"]["position"] = list(position)
        return DecisionRequest.model_validate(value)

    def record(self, request, *, order=("A",), action="CONTINUE", reason="PLAN_SELECTED"):
        """Construct a complete example contract, not a computed selector output."""
        budget = assess_order(request, build_leg_table(request), order)
        done = set(request.observation.completed_task_ids)
        deferred_reason = ("DATA_UNAVAILABLE" if budget.status == "UNAVAILABLE" else
                           "BUDGET" if reason == "NO_FEASIBLE_TASK" else "LOWER_VALUE_PLAN")
        return DecisionRecord.model_validate({
            "contract_version": CONTRACT_VERSION,
            "request_sha256": fingerprint(request),
            "as_of_s": request.observation.as_of_s,
            "selector_id": request.selector_id,
            "budget_mode": request.budget.mode,
            "action": action,
            "reason_code": reason,
            "ordered_task_ids": list(order),
            "deferred_tasks": [
                {"id": task.id, "reason": deferred_reason,
                 "follow_up_state": "REQUIRES_OPERATOR_REVIEW"}
                for task in request.task_catalog if task.id not in done | set(order)
            ],
            "budget": budget.model_dump(mode="json"),
            "computation_ms": 0.0,
        })

    def return_only_request(self, *, position=None):
        """Set a current observation with enough energy only for return/reserve."""
        request = self.request(position=position)
        legs = build_leg_table(request)
        demand = assess_order(request, legs, ()).assessed_demand_wh
        value = request.model_dump(mode="json")
        value["observation"]["available_wh_estimate"] = demand + 0.001
        request = DecisionRequest.model_validate(value)
        self.assertEqual(assess_order(request, legs, ()).status, "SUFFICIENT")
        for task in request.task_catalog:
            self.assertEqual(assess_order(request, legs, (task.id,)).status, "INSUFFICIENT")
        return request

    def assert_field_error(self, model, value, field, error_type):
        with self.assertRaises(ValidationError) as caught:
            model.model_validate(value)
        self.assertEqual([(error["loc"], error["type"]) for error in caught.exception.errors()],
                         [((field,), error_type)])

    def assert_pair_rejected(self, request, value, error_code):
        # The record must pass its own structural validation first. This ensures
        # the target failure is cross-record consistency, not a missing field.
        record = DecisionRecord.model_validate(value)
        with self.assertRaisesRegex(ValueError, "^" + error_code + "$"):
            validate_decision_for_request(request, record)

    def test_business_gates_are_required_and_reject_unsupported_semantics(self):
        cases = (
            (Task, self.maps[0].tasks[0].model_dump(mode="json"), "service_level",
             ("mandatory_safety_inspection", "delivery")),
            (Task, self.maps[0].tasks[0].model_dump(mode="json"), "action_semantics",
             ("actual_image_capture", "automatic_hazard_detection", "delivered")),
            (GridMap, self.maps[0].grid.model_dump(mode="json"), "blocked_cell_meaning",
             ("ground_snow_blockage", "ground_road_closed")),
            (DeferredTask, {"id": "B", "reason": "BUDGET",
                            "follow_up_state": "REQUIRES_OPERATOR_REVIEW"}, "follow_up_state",
             ("HUMAN_ACCEPTED", "HANDOVER_COMPLETED")),
        )
        for model, value, field, invalid_values in cases:
            with self.subTest(model=model.__name__, field=field):
                model.model_validate(value)
                self.assertTrue(model.model_fields[field].is_required())
                missing = value.copy()
                del missing[field]
                self.assert_field_error(model, missing, field, "missing")
                for invalid in invalid_values:
                    self.assert_field_error(model, {**value, field: invalid}, field, "literal_error")

    def test_completed_is_not_a_deferred_reason(self):
        value = {"id": "B", "reason": "BUDGET", "follow_up_state": "REQUIRES_OPERATOR_REVIEW"}
        DeferredTask.model_validate(value)
        self.assert_field_error(DeferredTask, {**value, "reason": "COMPLETED"},
                                "reason", "literal_error")

    def test_business_names_match_mapping_and_original_geometry_is_preserved(self):
        mapping = json.loads((V2 / "data/heilongjiang_application.json").read_text(encoding="utf-8"))
        original_path = Path(__file__).parent / "fixtures/development_scenarios_0_2.json"
        original = {row["id"]: row for row in json.loads(original_path.read_text(encoding="utf-8"))}
        names = {row["scenario_id"]: {t["task_id"]: t["display_name"] for t in row["tasks"]}
                 for row in mapping["scenario_labels"]}
        self.assertEqual(set(names), {scenario.id for scenario in self.maps})
        self.assertEqual(CONTRACT_VERSION, "competition-v2-contract-0.3")
        self.assertEqual(mapping["linked_contract"], CONTRACT_VERSION)
        self.assertEqual(mapping["scenario_source_sha256"],
                         hashlib.sha256((V2 / "data/development_scenarios.json").read_bytes()).hexdigest())
        self.assertEqual(sum(len(s.tasks) for s in self.maps), 13)
        for scenario in self.maps:
            current = scenario.model_dump(mode="json")
            before = original[scenario.id]
            self.assertEqual(scenario.version, "v2-development-maps-0.3")
            self.assertEqual({t.id: t.label for t in scenario.tasks}, names[scenario.id])
            self.assertEqual(scenario.grid.blocked_cell_meaning, "fixed_altitude_2d_exclusion_area")
            self.assertEqual(scenario.grid.blocked_cell_meaning, mapping["blocked_cell_meaning"])
            for key in ("base", "airspeed_ms", "fixed_height_m", "scheduled_events"):
                self.assertEqual(current[key], before[key], (scenario.id, key))
            for key in before["grid"]:
                self.assertEqual(current["grid"][key], before["grid"][key], (scenario.id, key))
            self.assertEqual([task["id"] for task in current["tasks"]], [task["id"] for task in before["tasks"]])
            old_tasks = {task["id"]: task for task in before["tasks"]}
            for task in scenario.tasks:
                self.assertEqual(task.service_level, "optional_supplemental_observation")
                self.assertEqual(task.action_semantics, "simulated_dwell_only")
                self.assertEqual(task.action_semantics, mapping["action_semantics"])
                self.assertEqual(task.service_level, mapping["task_service_level"])
                for key in ("position", "value", "dwell_s", "value_source"):
                    self.assertEqual(task.model_dump(mode="json")[key], old_tasks[task.id][key],
                                     (scenario.id, task.id, key))

    def test_missing_duplicate_or_mistyped_wind_probe_cannot_pass_development_checks(self):
        probes = route_probes(self.maps)
        self.assertTrue(development_checks(self.maps, probes)[0]["passed"])
        missing = copy.deepcopy(probes)
        missing["variants"] = [r for r in missing["variants"] if r["event"]["id"] != "east-gust"]
        duplicate = copy.deepcopy(probes)
        duplicate["variants"].append(copy.deepcopy(duplicate["variants"][-1]))
        mistyped = copy.deepcopy(probes)
        next(r for r in mistyped["variants"] if r["event"]["id"] == "east-gust")["event"]["type"] = "obstacle"
        for broken, code in ((missing, "development_probe_set_mismatch"),
                             (duplicate, "development_probe_set_mismatch"),
                             (mistyped, "development_gust_probe_type_mismatch")):
            with self.subTest(code=code):
                with self.assertRaisesRegex(ValueError, "^" + code + "$"):
                    development_checks(self.maps, broken)

    def test_complete_nominal_and_bounded_records_are_valid(self):
        for mode in ("nominal", "bounded"):
            with self.subTest(mode=mode):
                request = self.request(mode=mode, completed=("B",))
                record = self.record(request)
                self.assertIs(validate_decision_for_request(request, record), record)

    def test_unavailable_record_is_valid_without_numeric_budget_claim(self):
        request = self.request(temperature=-30.0)
        record = self.record(request, order=(), action="STOP", reason="DATA_UNAVAILABLE")
        self.assertIsNone(record.budget.assessed_demand_wh)
        self.assertIs(validate_decision_for_request(request, record), record)

    def test_pair_identity_mismatches_are_rejected(self):
        request = self.request()
        base = self.record(request).model_dump(mode="json")
        for field, wrong, error in (
                ("request_sha256", "0" * 64, "decision_request_fingerprint_mismatch"),
                ("as_of_s", 1.0, "decision_observation_time_mismatch"),
                ("selector_id", "fixed_order", "decision_policy_mismatch"),
                ("budget_mode", "bounded", "decision_policy_mismatch")):
            with self.subTest(field=field):
                self.assert_pair_rejected(request, {**base, field: wrong}, error)

    def test_omitted_unfinished_task_is_rejected(self):
        request = self.request()
        value = self.record(request).model_dump(mode="json")
        value["deferred_tasks"] = [task for task in value["deferred_tasks"] if task["id"] != "B"]
        self.assert_pair_rejected(request, value, "decision_task_accounting_incomplete")

    def test_unknown_deferred_task_is_rejected(self):
        request = self.request()
        value = self.record(request).model_dump(mode="json")
        value["deferred_tasks"][0]["id"] = "Ghost"
        self.assert_pair_rejected(request, value, "decision_unknown_task")

    def test_completed_task_cannot_also_be_selected(self):
        initial = self.request()
        value = self.record(initial).model_dump(mode="json")
        completed = self.request(completed=("A",))
        value["request_sha256"] = fingerprint(completed)
        self.assert_pair_rejected(completed, value, "decision_completed_task_reused")

    def test_completed_task_cannot_also_be_deferred(self):
        request = self.request(completed=("B",))
        value = self.record(request).model_dump(mode="json")
        value["deferred_tasks"].append({"id": "B", "reason": "BUDGET",
                                        "follow_up_state": "REQUIRES_OPERATOR_REVIEW"})
        self.assert_pair_rejected(request, value, "decision_completed_task_reused")

    def test_refused_is_allowed_only_at_base(self):
        at_base = self.return_only_request()
        refused = self.record(at_base, order=(), action="REFUSED", reason="NO_FEASIBLE_TASK")
        self.assertIs(validate_decision_for_request(at_base, refused), refused)
        away = self.return_only_request(position=self.maps[0].tasks[0].position)
        returning = self.record(away, order=(), action="RETURN", reason="NO_FEASIBLE_TASK")
        self.assertIs(validate_decision_for_request(away, returning), returning)
        value = returning.model_dump(mode="json")
        value["action"] = "REFUSED"
        self.assert_pair_rejected(away, value, "refused_requires_position_at_base")

    def test_all_tasks_visited_requires_actual_completed_id_set(self):
        request = self.return_only_request()
        value = self.record(request, order=(), action="RETURN", reason="NO_FEASIBLE_TASK").model_dump(mode="json")
        value["reason_code"] = "ALL_TASKS_VISITED"
        self.assert_pair_rejected(request, value, "all_tasks_visited_has_unfinished_tasks")
        complete = self.request(completed=tuple(task.id for task in self.maps[0].tasks))
        record = self.record(complete, order=(), action="RETURN", reason="ALL_TASKS_VISITED")
        self.assertEqual(record.deferred_tasks, ())
        self.assertIs(validate_decision_for_request(complete, record), record)

    def test_reserve_cannot_be_changed_inside_otherwise_consistent_budget(self):
        request = self.request()
        value = self.record(request).model_dump(mode="json")
        budget = value["budget"]
        budget["reserve_wh"] += 1.0
        budget["assessed_demand_wh"] += 1.0
        budget["margin_wh"] -= 1.0
        self.assert_pair_rejected(request, value, "decision_reserve_mismatch")

    def test_available_energy_must_follow_current_request_and_budget_mode(self):
        for mode in ("nominal", "bounded"):
            with self.subTest(mode=mode):
                request = self.request(mode=mode)
                value = self.record(request).model_dump(mode="json")
                value["budget"]["assessed_available_wh"] += 1.0
                value["budget"]["margin_wh"] += 1.0
                self.assert_pair_rejected(request, value, "decision_budget_arithmetic_mismatch")

    def test_demand_must_match_components_with_declared_error_once(self):
        for mode in ("nominal", "bounded"):
            for field in ("transit_wh", "service_wh", "return_wh", "assessed_demand_wh"):
                with self.subTest(mode=mode, field=field):
                    request = self.request(mode=mode)
                    value = self.record(request).model_dump(mode="json")
                    value["budget"][field] += 1.0
                    if field == "assessed_demand_wh":
                        value["budget"]["margin_wh"] -= 1.0
                    self.assert_pair_rejected(request, value, "decision_budget_arithmetic_mismatch")


if __name__ == "__main__":
    unittest.main()
