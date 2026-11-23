"""Behavioral checks for direct endurance and the connected HTTP/route API."""
import json
import math
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from pydantic import ValidationError

from competition.endurance.contracts import PredictionInput, RouteInput
from competition.endurance.model import EnduranceModel
from competition.endurance.routes import make_edge_model, plan_round_trip
from competition.v2.api import create_app


class EnduranceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = EnduranceModel()

    def test_direct_three_input_prediction_has_minutes(self):
        result = self.model.predict(temperature_c=-20, battery_percent=80, wind_speed_ms=5)
        self.assertGreater(result["remaining_minutes"], 2)
        self.assertLess(result["remaining_minutes"], 4)
        self.assertAlmostEqual(result["usable_minutes"] / result["remaining_minutes"], .75)
        self.assertEqual(result["inputs"]["ground_speed_ms"], 2)

    def test_charge_conservation_and_capacity_scaling(self):
        result = self.model.predict()
        delivered_ah = result["estimated_current_a"] * result["remaining_minutes"] / 60
        self.assertAlmostEqual(delivered_ah, result["available_capacity_ah"])
        doubled = self.model.predict(nominal_capacity_ah=result["inputs"]["nominal_capacity_ah"] * 2)
        self.assertAlmostEqual(doubled["remaining_minutes"], result["remaining_minutes"] * 2)

    def test_temperature_wind_and_soc_trends(self):
        for temperature in (-35, -20, -10, 0, 25):
            results = [self.model.predict(temperature_c=temperature, wind_speed_ms=wind) for wind in (0, 5, 10)]
            self.assertTrue(all(a["remaining_minutes"] > b["remaining_minutes"] for a, b in zip(results, results[1:])))
        times = [self.model.predict(temperature_c=t)["remaining_minutes"] for t in (-35, -20, -10, 0, 25)]
        self.assertEqual(times, sorted(times))
        self.assertAlmostEqual(self.model.predict(temperature_c=40)["remaining_minutes"], times[-1])
        for soc in range(0, 101, 10):
            result = self.model.predict(battery_percent=soc)
            self.assertTrue(math.isfinite(result["remaining_minutes"]))
            self.assertGreaterEqual(result["remaining_minutes"], 0)
            self.assertLessEqual(result["usable_minutes"], result["remaining_minutes"])

    def test_zero_and_below_reserve_are_useful_results(self):
        result = self.model.predict(battery_percent=0)
        self.assertEqual(result["remaining_minutes"], 0)
        self.assertEqual(result["usable_minutes"], 0)
        result = self.model.predict(battery_percent=10)
        self.assertGreater(result["remaining_minutes"], 0)
        self.assertEqual(result["usable_minutes"], 0)

    def test_extrapolation_returns_estimate_with_scope(self):
        result = self.model.predict(temperature_c=20, battery_percent=30, wind_speed_ms=15)
        self.assertGreater(result["remaining_minutes"], 0)
        self.assertCountEqual(result["extrapolated_fields"], ["temperature_c", "battery_percent", "wind_speed_ms"])
        self.assertFalse(self.model.artifact["interpretation"]["observed_exhaustion_labels"])

    def test_artifact_train_holdout_are_disjoint(self):
        training = self.model.artifact["training"]
        self.assertFalse(set(training["training_flights"]) & set(training["holdout_flights"]))
        self.assertEqual(len(training["training_flights"]) + len(training["holdout_flights"]), 35)
        self.assertEqual(len(training["holdout_flights"]), 12)

    def test_round_trip_consumption_matches_elapsed_current(self):
        request = RouteInput(temperature_c=-20, battery_percent=90, wind_speed_ms=0,
                             grid={"width": 5, "height": 3, "cell_size_m": 10}, start=(0, 1), goal=(4, 1))
        result = plan_round_trip(request, self.model)
        route = result["energy_route"]
        self.assertEqual(route["outbound"]["path"][0], [0, 1])
        self.assertEqual(route["inbound"]["path"][-1], [0, 1])
        self.assertEqual(route["distance_m"], 80)
        self.assertEqual(route["duration_s"], 40)
        self.assertAlmostEqual(route["estimated_consumption_ah"], self.model.current_a(0, 2) * 40 / 3600)
        self.assertEqual(route["outbound"]["cost_source"], self.model.version)

    def test_sheltered_lane_can_reduce_charge(self):
        result = plan_round_trip(RouteInput(wind_speed_ms=10, battery_percent=90), self.model)
        self.assertGreater(result["saving_percent"], 0)
        self.assertLess(result["energy_route"]["estimated_consumption_ah"], result["distance_route"]["estimated_consumption_ah"])
        self.assertGreater(result["energy_route"]["distance_m"], result["distance_route"]["distance_m"])
        low = plan_round_trip(RouteInput(wind_speed_ms=10, battery_percent=5), self.model)
        self.assertFalse(low["energy_route"]["feasible_with_reserve"])
        self.assertEqual(low["return_limit"]["status"], "start_below_reserve")
        self.assertEqual(result["return_limit"]["status"], "goal_with_reserve")
        self.assertAlmostEqual(result["return_limit"]["last_feasible"]["remaining_battery_percent"],
                               result["energy_route"]["remaining_battery_percent"])

    def test_return_limit_finds_last_waypoint_with_reserve(self):
        limit = plan_round_trip(RouteInput(), self.model)["return_limit"]
        self.assertEqual(limit["status"], "turn_back")
        self.assertEqual(limit["last_feasible"]["position"], [13, 6])
        self.assertEqual(limit["last_feasible"]["duration_s"], 60)
        self.assertGreater(limit["last_feasible"]["remaining_battery_percent"], 20)
        self.assertEqual(limit["first_limited"]["distance_m"], 130)
        self.assertEqual(limit["reason"], "reserve_shortfall")

    def test_uniform_strong_wind_cannot_promise_return(self):
        request = RouteInput(wind_speed_ms=20, max_airspeed_ms=15,
                             grid={"width": 5, "height": 3}, start=(0, 1), goal=(4, 1))
        result = plan_round_trip(request, self.model)
        self.assertEqual(result["energy_route"]["outbound"]["status"], "planned")
        self.assertEqual(result["energy_route"]["inbound"]["status"], "unreachable")
        self.assertFalse(result["energy_route"]["feasible_with_reserve"])
        self.assertEqual(result["return_limit"]["reason"], "return_unreachable")
        self.assertEqual(result["return_limit"]["last_feasible"]["distance_m"], 0)
        self.assertEqual(result["return_limit"]["first_limited"]["distance_m"], 10)

    def test_zero_length_round_trip_does_not_restore_missing_reserve(self):
        request = RouteInput(battery_percent=10, grid={"width": 3, "height": 3}, start=(1, 1), goal=(1, 1))
        result = plan_round_trip(request, self.model)
        for key in ("energy_route", "distance_route"):
            route = result[key]
            self.assertEqual(route["estimated_consumption_ah"], 0)
            self.assertFalse(route["feasible_with_reserve"])
            self.assertAlmostEqual(route["capacity_deficit_ah"], result["prediction"]["available_capacity_ah"])

    def test_ground_speed_slows_at_aircraft_limit(self):
        edge = make_edge_model(self.model, ground_speed_ms=2, max_airspeed_ms=15)
        self.assertAlmostEqual(edge((1, 0), (-14, 0))[0], 1)
        self.assertIsNone(edge((1, 0), (-16, 0)))
        self.assertAlmostEqual(edge((1, 0), (20, 0))[0], 5)
        for wind in ((20, 0), (-14, 0), (8, 12), (-8, 12)):
            result = edge((1, 0), wind)
            if result is not None:
                self.assertLessEqual(math.hypot(result[0] - wind[0], wind[1]), 15 + 1e-9)

    def test_invalid_input_is_rejected(self):
        for field, value in (("battery_percent", 101), ("wind_speed_ms", -1),
                             ("temperature_c", float("nan")), ("nominal_capacity_ah", 0)):
            with self.assertRaises(ValidationError):
                PredictionInput(**{field: value})


class HttpTests(unittest.TestCase):
    def test_replan_uses_current_conditions_and_keeps_reserve_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(Path(directory) / "runs.sqlite", tick_enabled=False)) as client:
                request = dict(grid={"width": 7, "height": 3}, current=[2, 1], base=[0, 1],
                               goal=[6, 1], alternates=[[3, 1]], wind_speed_ms=0, battery_percent=90)

                def replan(**changes):
                    response = client.post("/api/v2/endurance/replan", json={**request, **changes})
                    self.assertEqual(response.status_code, 200, response.text)
                    return response.json()

                original = replan()
                self.assertEqual(original["action"], "continue_to_goal")
                self.assertEqual([leg["path"][-1] for leg in original["legs"]], [[6, 1], [0, 1]])

                blocked = replan(grid={**request["grid"], "blocked": [[4, 1]]})
                self.assertEqual(blocked["action"], "continue_to_goal")
                self.assertNotIn([4, 1], [point for leg in blocked["legs"] for point in leg["path"]])
                self.assertGreater(blocked["estimated_consumption_ah"], original["estimated_consumption_ah"])

                low = replan(battery_percent=30)
                self.assertEqual(low["action"], "return_to_base")
                self.assertEqual(low["reason"], "goal_reserve_shortfall")
                self.assertTrue(low["feasible_with_reserve"])

                below_reserve = replan(battery_percent=15)
                self.assertEqual(below_reserve["action"], "divert")
                self.assertFalse(below_reserve["feasible_with_reserve"])

                gust = replan(wind_speed_ms=20)
                self.assertEqual(gust["action"], "divert")
                self.assertEqual(gust["reason"], "goal_return_unreachable")
                self.assertEqual(gust["legs"][0]["path"], [[2, 1], [3, 1]])

                stranded = replan(wind_speed_ms=20, alternates=[])
                self.assertEqual(stranded["action"], "no_feasible_landing")
                self.assertEqual(stranded["legs"], [])
                self.assertIsNone(stranded["remaining_battery_percent"])
                self.assertEqual(client.get("/api/v2/runs").json(), [])

    def test_predictions_and_routes_do_not_create_missions(self):
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(Path(directory) / "runs.sqlite", tick_enabled=False)) as client:
                request = {"temperature_c": -20, "battery_percent": 80, "wind_speed_ms": 5}
                prediction = client.post("/api/v2/endurance/predict", json=request)
                self.assertEqual(prediction.status_code, 200, prediction.text)
                self.assertGreater(prediction.json()["remaining_minutes"], 0)
                route = client.post("/api/v2/endurance/route", json=request)
                self.assertEqual(route.status_code, 200, route.text)
                self.assertEqual(route.json()["prediction"], prediction.json())
                self.assertEqual(route.json()["return_limit"]["last_feasible"]["distance_m"], 120)
                self.assertEqual(client.get("/api/v2/runs").json(), [])
                self.assertEqual(client.get("/endurance").status_code, 200)
                self.assertIn("/endurance", client.get("/").text)
                self.assertEqual(client.get("/api/v2/health").json()["api_version"], "competition-v2-api-0.4")
                self.assertEqual(client.get("/api/v2/endurance/model").json()["training"]["total_flights"], 35)
                schema = client.get("/openapi.json").json()
                self.assertIn("/api/v2/endurance/predict", schema["paths"])
                self.assertIn("PredictionResult", schema["components"]["schemas"])
                self.assertEqual(client.post("/api/v2/endurance/predict", json={**request, "battery_percent": -5}).status_code, 422)
                self.assertEqual(client.post("/api/v2/endurance/route", json={**request, "ground_speed_ms": 0}).status_code, 422)
                self.assertEqual(client.post("/api/v2/endurance/route", json={**request, "grid": {"width": 3, "height": 3}}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
