"""Directed optimality and actual edge-power integration, without A* as oracle."""
import heapq
import math
import random
import unittest

from competition.core.planning import plan as legacy_plan
from competition.endurance.pathfinding import GridPlanner


def dijkstra(width, height, blocked, regions, start, goal, objective, model=None, cell=10.0):
    """Independent graph discovery, wind selection and default edge arithmetic."""
    blocked = set(blocked)
    if start in blocked or goal in blocked:
        return math.inf
    best = {start: 0.0}
    queue = [(0.0, start)]
    while queue:
        score, point = heapq.heappop(queue)
        if score != best[point]:
            continue
        if point == goal:
            return score
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = point[0] + dx, point[1] + dy
            if not (0 <= neighbor[0] < width and 0 <= neighbor[1] < height) or neighbor in blocked:
                continue
            midpoint = point[0] + dx / 2, point[1] + dy / 2
            wind = (0.0, 0.0)
            for region in regions:
                if (region["x_min"] <= midpoint[0] <= region["x_max"]
                        and region["y_min"] <= midpoint[1] <= region["y_max"]):
                    wind = tuple(region["vector"])
            if model:
                estimate = model((dx, dy), wind)
                if estimate is None:
                    continue
                speed, power = estimate
            else:
                cross = wind[1] * dx - wind[0] * dy
                along = wind[0] * dx + wind[1] * dy
                if abs(cross) >= 5:
                    continue
                speed, power = math.sqrt(25 - cross * cross) + along, 70.56
                if speed <= .25:
                    continue
            candidate = score + (cell if objective == "distance" else power * cell / speed / 3600)
            if candidate < best.get(neighbor, math.inf):
                best[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return math.inf


class GridPlannerTests(unittest.TestCase):
    def test_default_matches_legacy_in_both_objectives(self):
        regions = [dict(x_min=2, x_max=5, y_min=0, y_max=5, vector=[-2.0, 1.0])]
        blocked = [(3, 2), (3, 3), (3, 4)]
        planner = GridPlanner(6, 6, blocked, regions)
        for objective in ("energy", "distance"):
            for start, goal in (((0, 0), (5, 5)), ((5, 5), (0, 0))):
                old = legacy_plan(start, goal, 6, 6, blocked, regions, 10., objective)
                new = planner.plan(start, goal, objective)
                self.assertEqual(old["status"], new["status"])
                self.assertAlmostEqual(old["cost"], new["cost"], delta=1e-7)
                self.assertEqual(new["cost_source"], old["cost_source"])

    def test_direction_and_return_are_not_symmetric(self):
        regions = [dict(x_min=0, x_max=4, y_min=0, y_max=2, vector=[2.0, 0.0])]
        planner = GridPlanner(5, 3, [], regions)
        outward = planner.plan((0, 1), (4, 1))
        returning = planner.plan((4, 1), (0, 1))
        self.assertAlmostEqual(outward["duration_s"], 40 / 7)
        self.assertAlmostEqual(returning["duration_s"], 40 / 3)
        self.assertLess(outward["estimated_energy_wh"], returning["estimated_energy_wh"])

    def test_custom_power_changes_optimal_route(self):
        regions = [dict(x_min=1, x_max=3, y_min=1, y_max=1, vector=[4.0, 0.0])]

        def model(direction, wind):
            return (2.0, 1000.0 if wind[0] else 50.0)

        planner = GridPlanner(5, 3, [], regions, edge_model=model)
        shortest = planner.plan((0, 1), (4, 1), "distance")
        energy = planner.plan((0, 1), (4, 1))
        self.assertEqual(shortest["distance_m"], 40)
        self.assertEqual(energy["distance_m"], 60)
        self.assertLess(energy["estimated_energy_wh"], shortest["estimated_energy_wh"])
        self.assertAlmostEqual(energy["estimated_energy_wh"], 50 * 30 / 3600)

    def test_obstacles_endpoints_and_zero_length(self):
        planner = GridPlanner(5, 3, [(2, y) for y in range(3)], [])
        self.assertEqual(planner.plan((0, 0), (4, 0))["reason"], "no_feasible_path")
        self.assertEqual(planner.plan((0, 0), (2, 0))["reason"], "blocked_endpoint")
        self.assertEqual(planner.plan((0, 0), (6, 0))["reason"], "endpoint_outside_map")
        same = planner.plan((0, 0), (0, 0))
        self.assertEqual(same["path"], [[0, 0]])
        self.assertEqual((same["cost"], same["duration_s"], same["estimated_energy_wh"]), (0, 0, 0))

    def test_unflyable_direction_and_crosswind_do_not_create_edges(self):
        regions = [dict(x_min=0, x_max=3, y_min=0, y_max=3, vector=[6.0, 0.0])]
        planner = GridPlanner(4, 4, [], regions)
        self.assertEqual(planner.plan((0, 1), (3, 1))["status"], "planned")
        self.assertEqual(planner.plan((3, 1), (0, 1))["status"], "unreachable")
        self.assertEqual(planner.plan((0, 0), (0, 1))["status"], "unreachable")
        rejected = GridPlanner(3, 3, [], [], edge_model=lambda direction, wind: None)
        self.assertEqual(rejected.plan((0, 0), (1, 1))["status"], "unreachable")

    def test_dijkstra_oracle_60_grids_both_objectives(self):
        rng = random.Random(20261116)
        for case in range(60):
            size = 5 + case % 4
            start, goal = (0, 0), (size - 1, size - 1)
            blocked = {(x, y) for x in range(size) for y in range(size) if rng.random() < .2} - {start, goal}
            regions = [dict(x_min=1, x_max=size - 1, y_min=0, y_max=size - 1,
                            vector=[rng.uniform(-5.5, 5.5), rng.uniform(-2., 2.)]),
                       dict(x_min=1, x_max=size - 2, y_min=1, y_max=size - 2,
                            vector=[rng.uniform(-3., 3.), rng.uniform(-3., 3.)])]
            # Alternate reference physics with variable power and rejected edges.
            model = None if case % 2 == 0 else lambda direction, wind: (
                None if wind[0] * direction[0] < -4 else
                (2 + .1 * (wind[0] * direction[0] + wind[1] * direction[1]),
                 60 + 3 * (wind[0] - direction[0]) ** 2 + 2 * (wind[1] - direction[1]) ** 2))
            planner = GridPlanner(size, size, blocked, regions, edge_model=model)
            for objective in ("energy", "distance"):
                for a, b in ((start, goal), (goal, start)):
                    with self.subTest(case=case, objective=objective, start=a):
                        expected = dijkstra(size, size, blocked, regions, a, b, objective, model)
                        actual = planner.plan(a, b, objective)
                        if math.isinf(expected):
                            self.assertEqual(actual["status"], "unreachable")
                            continue
                        self.assertEqual(actual["status"], "planned")
                        self.assertAlmostEqual(actual["cost"], expected, delta=1e-7)
                        path = [tuple(p) for p in actual["path"]]
                        self.assertEqual((path[0], path[-1]), (a, b))
                        self.assertFalse(set(path) & blocked)
                        for p, q in zip(path, path[1:]):
                            self.assertEqual(abs(p[0] - q[0]) + abs(p[1] - q[1]), 1)

    def test_cache_and_map_snapshot_are_independent_of_caller_mutations(self):
        regions = [dict(x_min=0, x_max=4, y_min=0, y_max=4, vector=[0., 0.])]
        calls = []

        def model(direction, wind):
            calls.append((direction, wind))
            return 2., 60.

        planner = GridPlanner(5, 5, [], regions, edge_model=model)
        self.assertEqual(len(calls), 4)
        first = planner.plan((0, 0), (4, 4))
        first["path"][0][0] = 999
        regions[0]["vector"][0] = 100
        second = planner.plan((0, 0), (4, 4))
        self.assertEqual(second["path"][0], [0, 0])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["expanded_nodes"], 0)
        self.assertGreater(second["uncached_expanded_nodes"], 0)
        self.assertEqual(len(calls), 4)
        self.assertFalse(planner.plan((4, 4), (0, 0))["cache_hit"])

    def test_open_grid_tie_break_does_not_expand_entire_rectangle(self):
        planner = GridPlanner(32, 32, [], [])
        result = planner.plan((0, 0), (31, 31), "distance")
        self.assertEqual(result["expanded_nodes"], 63)
        old = legacy_plan((0, 0), (31, 31), 32, 32, [], [], 10., "distance")
        self.assertGreater(old["expanded_nodes"], result["expanded_nodes"])

    def test_invalid_nonpositive_edge_values_are_rejected(self):
        for speed, power in ((0, 60), (2, -1), (math.nan, 60), (2, math.inf)):
            with self.subTest(speed=speed, power=power), self.assertRaises(ValueError):
                GridPlanner(2, 2, [], [], edge_model=lambda d, w: (speed, power))


if __name__ == "__main__":
    unittest.main()
