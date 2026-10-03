import copy
import heapq
import math
from pathlib import Path
import random
import tempfile
import unittest

from competition.core.curves import CurveLibrary
from competition.core.planning import plan, UPPER_POWER_W
from competition.core.scenarios import formal_manifest, get_scenario
from competition.core.simulator import MissionRun, compare_runs
from competition.core.storage import RunStore


class CurvesTests(unittest.TestCase):
    def test_source_wh_and_interpolation_use_one_profile(self):
        library = CurveLibrary()
        self.assertTrue(library.available, library.reason)
        expected = {-20: 52.079758438, 0: 56.990492601, 23: 60.316595571}
        for temperature, wh in expected.items():
            curve = library.curve(temperature)
            self.assertAlmostEqual(curve.energy_between(0, curve.capacity_ah), wh, places=5)
        interpolated = library.curve(-10)
        self.assertAlmostEqual(interpolated.energy_between(0, interpolated.capacity_ah), 54.507484047, places=6)
        self.assertNotIn(-10, library.curves)
        with self.assertRaises(ValueError):
            library.curve(-20.01)
        with self.assertRaises(ValueError):
            library.curve(23.01)

    def test_missing_data_is_unavailable_never_faked(self):
        library = CurveLibrary(Path(tempfile.gettempdir()) / "nonexistent-competition-curves-test.json")
        run = MissionRun({}, library)
        self.assertEqual(run.status, "UNAVAILABLE")
        self.assertEqual(run.telemetry, [])
        self.assertIsNone(run.summary()["total_energy_wh"])
        self.assertEqual(compare_runs(run, run)["status"], "not_comparable")


class PlanningTests(unittest.TestCase):
    def test_directed_wind_cost_and_infeasible_track(self):
        region = [{"x_min": 0, "x_max": 3, "y_min": 0, "y_max": 3, "vector": [-2, 0]}]
        outbound = plan([0, 0], [3, 0], 4, 4, [], region)
        returning = plan([3, 0], [0, 0], 4, 4, [], region)
        self.assertGreater(outbound["estimated_energy_wh"], returning["estimated_energy_wh"])
        region[0]["vector"] = [0, 6]
        self.assertEqual(plan([0, 0], [1, 0], 4, 4, [], region)["status"], "unreachable")

    def test_energy_astar_matches_independent_dijkstra_on_40_maps(self):
        randomizer = random.Random(4200)
        wind = (-2, 0)
        region = [{"x_min": 0, "x_max": 4, "y_min": 0, "y_max": 4, "vector": list(wind)}]
        for _ in range(40):
            blocked = {(x, y) for x in range(5) for y in range(5) if randomizer.random() < .2} - {(0, 0), (4, 4)}
            frontier, visited, answer = [(0., (0, 0))], set(), None
            while frontier:
                cost, point = heapq.heappop(frontier)
                if point in visited:
                    continue
                visited.add(point)
                if point == (4, 4):
                    answer = cost
                    break
                for next_point in ((point[0] + 1, point[1]), (point[0] - 1, point[1]), (point[0], point[1] + 1), (point[0], point[1] - 1)):
                    x, y = next_point
                    if not (0 <= x < 5 and 0 <= y < 5) or next_point in blocked:
                        continue
                    dx, dy = next_point[0] - point[0], next_point[1] - point[1]
                    parallel, perpendicular = wind[0] * dx + wind[1] * dy, -wind[0] * dy + wind[1] * dx
                    speed = math.sqrt(25 - perpendicular * perpendicular) + parallel
                    heapq.heappush(frontier, (cost + UPPER_POWER_W * 80 / speed / 3600, next_point))
            actual = plan([0, 0], [4, 4], 5, 5, blocked, region)
            if answer is None:
                self.assertEqual(actual["status"], "unreachable")
            else:
                self.assertAlmostEqual(actual["estimated_energy_wh"], answer, places=9)


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.library = CurveLibrary()

    def test_energy_ah_conservation_from_independent_raw_vi_integral(self):
        run = MissionRun({"temperature_c": -10}, self.library).run_all()
        rows = run.telemetry
        wh = sum((a["voltage_v"] * a["current_a"] + b["voltage_v"] * b["current_a"]) * .5 * (b["t_s"] - a["t_s"]) / 3600
                 for a, b in zip(rows, rows[1:]))
        ah = sum((a["current_a"] + b["current_a"]) * .5 * (b["t_s"] - a["t_s"]) / 3600
                 for a, b in zip(rows, rows[1:]))
        self.assertAlmostEqual(wh, run.consumed_wh, places=8)
        self.assertAlmostEqual(ah, run.q - run.initial_q, places=9)
        self.assertAlmostEqual(run.initial_wh - wh, run.remaining_wh, places=8)
        self.assertTrue(run.returned)
        self.assertEqual(run.position, list(map(float, run.scenario["start"])))

    def test_execution_is_independent_of_wallclock_chunks_and_speedup(self):
        first = MissionRun({"scenario_id": "gust-s1", "speedup": 20}, self.library).run_all()
        second = MissionRun({"scenario_id": "gust-s1", "speedup": 100}, self.library)
        randomizer = random.Random(2026)
        while second.status == "RUNNING":
            second.advance(randomizer.uniform(.01, 6))
        self.assertEqual(first.export()["result_sha256"], second.export()["result_sha256"])

    def test_future_event_not_in_initial_plan_and_applies_online(self):
        normal = MissionRun({"scenario_id": "normal-s1"}, self.library)
        gust = MissionRun({"scenario_id": "gust-s1"}, self.library)
        self.assertEqual(normal.path, gust.path)
        self.assertEqual(normal.currentbudget, gust.currentbudget)
        self.assertEqual(gust.events, [])
        gust.advance(121)
        self.assertEqual(gust.events[0]["t_s"], 120)
        self.assertEqual(gust.events[0]["source"], "scheduled")
        self.assertTrue(gust.events[0]["applied"])
        gust.advance(30)
        self.assertTrue(any(d["reason"] == "event_applied" and d["t_s"] >= 120 for d in gust.decisions))

    def test_manual_event_export_replays_without_rewriting_original(self):
        original = MissionRun({}, self.library)
        original.advance(66.3)
        original.apply_event({"type": "wind", "wind": [-3, 0]})
        original.run_all()
        snapshot = copy.deepcopy(original.export())
        replay = MissionRun(snapshot["configuration"], self.library).run_all()
        self.assertEqual(snapshot["result_sha256"], replay.export()["result_sha256"])
        self.assertEqual(snapshot, original.export())
        self.assertNotEqual(original.id, replay.id)

    def test_emitted_configuration_hash_is_consistent_after_manual_events(self):
        run = MissionRun({}, self.library)
        run.advance(33)
        run.apply_event({"type": "wind", "wind": [-3, 0]})
        exported = run.export()
        self.assertEqual(exported["state"]["configuration_sha256"], exported["metadata"]["configuration_sha256"])
        self.assertEqual(run.state()["configuration_sha256"], exported["metadata"]["configuration_sha256"])

    def test_dynamic_obstacle_trajectory_respects_applied_map(self):
        run = MissionRun({"scenario_id": "dynamic_obstacle-s1"}, self.library).run_all()
        obstacle_event = next(e for e in run.events if e["type"] == "obstacle")
        self.assertTrue(obstacle_event["applied"])
        for row in run.telemetry:
            x, y = row["position"]
            self.assertTrue(0 <= x < run.scenario["width"] and 0 <= y < run.scenario["height"])
            if x.is_integer() and y.is_integer() and row["t_s"] >= obstacle_event["t_s"]:
                self.assertNotIn((int(x), int(y)), run.blocked)

    def test_whole_mission_budget_is_separate_from_next_point(self):
        run = MissionRun({"scenario_id": "low_budget-s1", "temperature_c": -20}, self.library)
        whole, next_point = run.initial_whole_mission_budget, run.currentbudget
        self.assertGreater(whole["mission_task_wh"], next_point["next_task_wh"])
        self.assertLessEqual(whole["feasible_prefix_count"], 3)
        self.assertEqual(whole["target_count"], 3)

    def test_failure_and_abstention_preserved_not_savings(self):
        run = MissionRun({}, self.library)
        run.apply_event({"type": "wind", "wind": [0, 15]})
        run.run_all()
        self.assertIn(run.status, ("FAILED", "COMPLETED"))
        self.assertIsNone(compare_runs(run, MissionRun({}, self.library).run_all())["energy_saving_pct"])

    def test_unflyable_wind_on_occupied_edge_is_failed_without_teleport(self):
        scenario = get_scenario("normal-s1")
        scenario["wind_regions"][0].update(x_min=0, x_max=22, y_min=0, y_max=14)
        run = MissionRun({"scenario": scenario}, self.library)
        run.advance(1)
        before = list(run.position)
        run.apply_event({"type": "wind", "wind": [0, 15]})
        run.advance(2)
        self.assertEqual(run.status, "FAILED")
        self.assertEqual(run.ended_reason, "wind_exceeds_track_hold_model")
        self.assertFalse(run.returned)
        self.assertEqual(run.position, before)
        self.assertIsNotNone(run.response_metrics[0]["decision_compute_ms"])

    def test_cancelled_export_replays_at_original_simulation_time(self):
        run = MissionRun({}, self.library)
        run.advance(62.2)
        run.cancel()
        archive = run.export()
        replay = MissionRun(archive["configuration"], self.library).run_all()
        self.assertEqual(replay.status, "CANCELLED")
        self.assertEqual(replay.export()["result_sha256"], archive["result_sha256"])

    def test_same_predictor_and_reserve_for_both_route_objectives(self):
        a = MissionRun({"strategy": "distance"}, self.library)
        b = MissionRun({"strategy": "energy"}, self.library)
        self.assertEqual(a.library.sha256, b.library.sha256)
        self.assertEqual(a.reserve_wh, b.reserve_wh)
        self.assertEqual(a.initial_wh, b.initial_wh)
        self.assertEqual(a.configuration["estimator_version"], b.configuration["estimator_version"])

    def test_response_cpu_and_simulation_delay_have_separate_boundaries(self):
        run = MissionRun({"scenario_id": "gust-s1"}, self.library).run_all()
        metric = run.response_metrics[0]
        self.assertGreaterEqual(metric["event_compute_ms"], 0)
        self.assertGreaterEqual(metric["decision_compute_ms"], 0)
        self.assertAlmostEqual(metric["simulated_reaction_s"], metric["decision_t_s"] - metric["event_t_s"])
        self.assertLessEqual(metric["simulated_reaction_s"], 50)

    def test_load_and_wind_sensitivity_change_estimator_not_execution_reference(self):
        run = MissionRun({"load_mismatch_fraction": .1, "wind_observation_bias_ms": .5}, self.library)
        self.assertAlmostEqual(run.library.current_a, 4.2)
        self.assertAlmostEqual(run.estimated_power_w, UPPER_POWER_W / 1.1)
        true = run.wind_regions[0]["vector"][0]
        observed = run.observed_wind_regions()[-1]["vector"][0]
        self.assertAlmostEqual(observed - true, .5)
        run.run_all()
        self.assertTrue(all(row["current_a"] == 4.2 for row in run.telemetry))

    def test_frozen_manifest_has_24_cases_and_48_executions(self):
        manifest = formal_manifest()
        self.assertEqual(manifest["software_scenarios"], 24)
        self.assertEqual(manifest["paired_executions"], 48)
        self.assertEqual(manifest["independent_real_flights"], 0)
        self.assertEqual(manifest, formal_manifest())


class StorageTests(unittest.TestCase):
    def test_isolated_store_survives_reopen_and_preserves_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            run = MissionRun({}, CurveLibrary())
            run.apply_event({"type": "wind", "wind": [-3, 0]})
            store = RunStore(path)
            store.save(run)
            store.save(run)
            store.close()
            reopened = RunStore(path)
            self.assertEqual(reopened.get(run.id), run.export())
            self.assertEqual(len(reopened.list()), 1)
            reopened.close()


if __name__ == "__main__":
    unittest.main()
