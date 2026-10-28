"""Meaningful boundaries for future information, costs and development geometry."""
import unittest

from pydantic import ValidationError

from competition.core.planning import UPPER_POWER_W
from competition.v2.contracts import (CONTRACT_VERSION, BudgetAssessment, DecisionRecord, DecisionRequest, LegEstimate,
                                      fingerprint)
from competition.v2.planning_inputs import assess_order, build_leg_table, plan_leg
from competition.v2.scenarios import Scenario, development_scenarios, initial_request, observed_grid


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maps = development_scenarios()
        cls.request = initial_request(cls.maps[0])
        cls.legs = build_leg_table(cls.request)

    def test_json_roundtrip_and_stable_fingerprint(self):
        recovered = DecisionRequest.model_validate_json(self.request.model_dump_json())
        self.assertEqual(recovered, self.request)
        self.assertEqual(fingerprint(recovered), fingerprint(self.request))

    def test_future_events_rejected_at_every_request_layer(self):
        for path in ((), ("observation",), ("observation", "known_map"), ("model",),
                     ("budget",), ("task_catalog", 0), ("observation", "known_map", "wind_regions", 0)):
            with self.subTest(path=path):
                value = self.request.model_dump(mode="json")
                target = value
                for key in path:
                    target = target[key]
                target["scheduled_events"] = [{"at_s": 100, "type": "wind"}]
                with self.assertRaises(ValidationError):
                    DecisionRequest.model_validate(value)

    def test_bool_nonfinite_and_unknown_policy_rejected(self):
        for path, invalid in ((["observation", "available_wh_estimate"], True),
                              (["observation", "temperature_c"], float("nan")),
                              (["model", "estimated_power_w"], float("inf")),
                              (["selector_id"], "made_up_algorithm"),
                              (["task_catalog", 0, "value"], True)):
            with self.subTest(path=path):
                value = self.request.model_dump(mode="json")
                target = value
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = invalid
                with self.assertRaises(ValidationError):
                    DecisionRequest.model_validate(value)

    def test_completed_id_and_duplicate_task_rejected(self):
        value = self.request.model_dump(mode="json")
        value["observation"]["completed_task_ids"] = ["does-not-exist"]
        with self.assertRaises(ValidationError):
            DecisionRequest.model_validate(value)
        value = self.request.model_dump(mode="json")
        value["task_catalog"][1]["id"] = value["task_catalog"][0]["id"]
        with self.assertRaises(ValidationError):
            DecisionRequest.model_validate(value)

    def test_changed_map_requires_changed_fingerprint(self):
        value = self.request.model_dump(mode="json")
        value["observation"]["known_map"]["blocked"].append([0, 0])
        with self.assertRaises(ValidationError):
            DecisionRequest.model_validate(value)

    def test_future_changes_do_not_change_initial_request(self):
        scenario = self.maps[1]
        value = scenario.model_dump(mode="json")
        value["scheduled_events"][0]["cells"] = [[8, 9]]
        value["scheduled_events"][0]["at_s"] = 100.0
        variant = Scenario.model_validate(value)
        self.assertNotEqual(fingerprint(scenario), fingerprint(variant))
        self.assertEqual(fingerprint(initial_request(scenario)), fingerprint(initial_request(variant)))

    def test_event_not_visible_before_declared_time(self):
        scenario = self.maps[1]
        self.assertNotIn((8, 3), observed_grid(scenario, 31.999).blocked)
        self.assertIn((8, 3), observed_grid(scenario, 32.0).blocked)

    def test_development_maps_have_distinct_topologies_and_all_tasks_reachable(self):
        self.assertEqual([len(s.tasks) for s in self.maps], [5, 8])
        self.assertNotEqual(self.maps[0].grid.width, self.maps[1].grid.width)
        for scenario in self.maps:
            legs = build_leg_table(initial_request(scenario))
            for task in scenario.tasks:
                self.assertEqual(legs["BASE", task.id].status, "PLANNED")
                self.assertEqual(legs[task.id, "BASE"].status, "PLANNED")
            for leg in legs.values():
                self.assertTrue(set(leg.path).isdisjoint(scenario.grid.blocked))
                for a, b in zip(leg.path, leg.path[1:]):
                    self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1)

    def test_gate_closure_changes_probe_route_and_closing_both_is_unreachable(self):
        scenario = self.maps[1]
        goal = next(t.position for t in scenario.tasks if t.id == "C")
        before = plan_leg(scenario.grid, scenario.base, goal, "BASE", "C", 5.0, UPPER_POWER_W)
        after = plan_leg(observed_grid(scenario, 32.0), scenario.base, goal, "BASE", "C", 5.0, UPPER_POWER_W)
        self.assertIn((8, 3), before.path)
        self.assertNotIn((8, 3), after.path)
        self.assertIn((8, 9), after.path)
        self.assertGreater(after.distance_m, before.distance_m)
        data = scenario.model_dump(mode="json")
        data["scheduled_events"][0]["cells"] = [[8, 3], [8, 9]]
        closed = Scenario.model_validate(data)
        leg = plan_leg(observed_grid(closed, 32.0), scenario.base, goal, "BASE", "C", 5.0, UPPER_POWER_W)
        self.assertEqual(leg.status, "UNREACHABLE")
        self.assertIsNone(leg.energy_wh)

    def test_wind_probe_changes_directed_energy(self):
        scenario = self.maps[1]
        data = scenario.model_dump(mode="json")
        data["scheduled_events"] = [{"id": "east-gust", "at_s": 32.0, "type": "wind", "region_id": "east", "vector": [-3.0, 0.0]}]
        gust = Scenario.model_validate(data)
        grid = observed_grid(gust, 32.0)
        goal = next(t.position for t in scenario.tasks if t.id == "C")
        before = plan_leg(scenario.grid, scenario.base, goal, "BASE", "C", 5.0, UPPER_POWER_W)
        after = plan_leg(grid, scenario.base, goal, "BASE", "C", 5.0, UPPER_POWER_W)
        back = plan_leg(grid, goal, scenario.base, "C", "BASE", 5.0, UPPER_POWER_W)
        self.assertGreater(after.energy_wh, before.energy_wh)
        self.assertNotAlmostEqual(after.energy_wh, back.energy_wh)

    def test_budget_uses_directed_return_and_dwell(self):
        request = initial_request(self.maps[0], budget_mode="nominal")
        legs = build_leg_table(request)
        actual = assess_order(request, legs, ["C"])
        expected = legs["CURRENT", "C"].energy_wh + 10 * UPPER_POWER_W / 3600 + legs["C", "BASE"].energy_wh + request.budget.reserve_wh
        self.assertAlmostEqual(actual.assessed_demand_wh, expected)
        self.assertNotAlmostEqual(legs["C", "BASE"].energy_wh, legs["BASE", "C"].energy_wh)
        self.assertFalse(actual.execution_verified)

    def test_bounded_budget_applies_uncertainty_once_and_not_to_reserve(self):
        nominal = initial_request(self.maps[0], budget_mode="nominal")
        a = assess_order(nominal, self.legs, ["C", "D"])
        b = assess_order(self.request, self.legs, ["C", "D"])
        self.assertAlmostEqual(b.assessed_demand_wh, (a.assessed_demand_wh-a.reserve_wh)*1.1+a.reserve_wh)
        self.assertAlmostEqual(b.assessed_available_wh, a.assessed_available_wh * 0.9)

    def test_completed_tasks_not_reselected(self):
        data = self.request.model_dump(mode="json")
        data["observation"]["completed_task_ids"] = ["A"]
        request = DecisionRequest.model_validate(data)
        legs = build_leg_table(request)
        self.assertNotIn(("CURRENT", "A"), legs)
        with self.assertRaisesRegex(ValueError, "completed_task"):
            assess_order(request, legs, ["A"])

    def test_missing_or_unreachable_return_does_not_become_zero(self):
        legs = self.legs.copy()
        del legs["C", "BASE"]
        missing = assess_order(self.request, legs, ["C"])
        self.assertEqual(missing.status, "UNAVAILABLE")
        self.assertIsNone(missing.margin_wh)
        legs["C", "BASE"] = LegEstimate(from_id="C", to_id="BASE", status="UNREACHABLE", path=(), distance_m=None, duration_s=None, energy_wh=None, reason="no_feasible_path")
        unavailable = assess_order(self.request, legs, ["C"])
        self.assertEqual(unavailable.reason, "return_unreachable")

    def test_unsupported_temperature_is_explicitly_unavailable(self):
        request = initial_request(self.maps[0], temperature_c=-30.0)
        self.assertEqual(request.observation.data_status, "UNAVAILABLE")
        self.assertIsNone(request.observation.available_wh_estimate)
        self.assertEqual(build_leg_table(request), {})
        self.assertEqual(assess_order(request, {}, ["C"]).status, "UNAVAILABLE")

    def test_cold_reference_reduces_available_energy_with_fixed_reserve(self):
        warm = initial_request(self.maps[0], temperature_c=0.0)
        cold = initial_request(self.maps[0], temperature_c=-20.0)
        self.assertLess(cold.observation.available_wh_estimate, warm.observation.available_wh_estimate)
        self.assertEqual(cold.budget.reserve_wh, warm.budget.reserve_wh)

    def test_estimation_bias_does_not_change_curve_or_map(self):
        biased = initial_request(self.maps[0], error_profile="joint_within_declared")
        self.assertAlmostEqual(biased.observation.available_wh_estimate, self.request.observation.available_wh_estimate / 0.9)
        self.assertAlmostEqual(biased.model.estimated_power_w, UPPER_POWER_W / 1.1)
        self.assertEqual(biased.model.curve_sha256, self.request.model.curve_sha256)
        self.assertEqual(biased.observation.known_map_sha256, self.request.observation.known_map_sha256)

    def test_budget_cannot_claim_execution_or_inconsistent_success(self):
        result = assess_order(self.request, self.legs, ["C"]).model_dump(mode="json")
        result["execution_verified"] = True
        with self.assertRaises(ValidationError):
            BudgetAssessment.model_validate(result)
        result["execution_verified"] = False
        result["margin_wh"] = -100.0
        result["status"] = "SUFFICIENT"
        with self.assertRaises(ValidationError):
            BudgetAssessment.model_validate(result)

    def test_decision_action_reason_and_deferred_tasks_cannot_conflict(self):
        request = initial_request(self.maps[0], initial_soc=1.0, budget_mode="nominal")
        budget = assess_order(request, build_leg_table(request), ["A"])
        value = {"contract_version": CONTRACT_VERSION, "request_sha256": fingerprint(request),
                 "as_of_s": 0.0, "selector_id": request.selector_id, "budget_mode": "nominal",
                 "action": "CONTINUE", "reason_code": "PLAN_SELECTED", "ordered_task_ids": ["A"],
                 "deferred_tasks": [], "budget": budget.model_dump(mode="json"), "computation_ms": 0.0}
        DecisionRecord.model_validate(value)
        for change in ({"reason_code": "RETURN_UNREACHABLE"},
                       {"deferred_tasks": [{"id": "A", "reason": "BUDGET", "follow_up_state": "REQUIRES_OPERATOR_REVIEW"}]},
                       {"returned": True}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                DecisionRecord.model_validate({**value, **change})


if __name__ == "__main__":
    unittest.main()
