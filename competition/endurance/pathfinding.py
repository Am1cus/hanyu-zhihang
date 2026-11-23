"""Reusable directed A* graph with current wind and pluggable edge power.

The old competition/core/planning.py remains the frozen v2 implementation.
An edge model takes (unit_direction, wind_vector) and returns
(ground_speed_ms, power_w), or None when that direction cannot be flown.
Models must be pure for a planner's lifetime: construct another planner when
the observed wind, obstacles, or aircraft parameters change.
"""
from __future__ import annotations

from collections import OrderedDict
import copy
import heapq
from itertools import accumulate
import math
import time

from competition.core.planning import ESTIMATOR_VERSION, UPPER_POWER_W, wind_at

PLANNER_VERSION = "directed-astar-context-1.1"
DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def default_edge_model(direction, wind):
    """The legacy 5 m/s airspeed and 70.56 W reference model."""
    dx, dy = direction
    wx, wy = wind
    along, cross = wx * dx + wy * dy, -wx * dy + wy * dx
    if abs(cross) >= 5.0:
        return None
    speed = math.sqrt(25.0 - cross * cross) + along
    return (speed, UPPER_POWER_W) if speed > 0.25 else None


class GridPlanner:
    """One immutable observed map, reusable for many endpoint queries.

    The energy heuristic sums the cheapest directed crossings of the grid
    boundaries between the current point and goal.
    Equal f-scores prefer larger g, avoiding broad equal-cost plateaus.
    """

    def __init__(self, width, height, blocked, wind_regions, cell_size_m=10.0,
                 edge_model=None):
        started = time.perf_counter()
        if (type(width) is not int or type(height) is not int
                or width < 1 or height < 1):
            raise ValueError("grid dimensions must be positive integers")
        if not math.isfinite(cell_size_m) or cell_size_m <= 0:
            raise ValueError("cell_size_m must be positive and finite")
        self.width, self.height = width, height
        self.cell_size_m = float(cell_size_m)
        self.blocked = frozenset(self._point(p) for p in blocked)
        if any(not self._contains(p) for p in self.blocked):
            raise ValueError("blocked cell outside map")
        # Keep a snapshot; caller edits must not make cached routes stale.
        self.wind_regions = copy.deepcopy(list(wind_regions))
        for region in self.wind_regions:
            if (region["x_min"] > region["x_max"]
                    or region["y_min"] > region["y_max"]
                    or len(region["vector"]) != 2
                    or not all(math.isfinite(v) for v in region["vector"])):
                raise ValueError("invalid wind region")
        model = edge_model or default_edge_model
        self.cost_source = (ESTIMATOR_VERSION if edge_model is None else
                            getattr(model, "cost_source", "edge_power_times_travel_time_v1"))
        self._cache = OrderedDict()
        self._graph = [[] for _ in range(width * height)]
        crossing_minima = [[math.inf] * (length - 1)
                           for length in (width, width, height, height)]
        edge_values = {}
        edge_count = 0
        for y in range(height):
            for x in range(width):
                if (x, y) in self.blocked:
                    continue
                adjacency = self._graph[y * width + x]
                for direction_index, (dx, dy) in enumerate(DIRECTIONS):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < width and 0 <= ny < height) or (nx, ny) in self.blocked:
                        continue
                    wind = wind_at((x + dx * .5, y + dy * .5), self.wind_regions)
                    key = (direction_index, wind)
                    if key not in edge_values:
                        estimate = model((dx, dy), wind)
                        if estimate is None:
                            edge_values[key] = None
                        else:
                            speed, power = estimate
                            if not all(math.isfinite(v) and v > 0 for v in (speed, power)):
                                raise ValueError("edge model must return positive finite speed and power")
                            duration = self.cell_size_m / speed
                            edge_values[key] = (duration, duration * power / 3600.0)
                    estimate = edge_values[key]
                    if estimate is None:
                        continue
                    duration, energy = estimate
                    adjacency.append((ny * width + nx, duration, energy))
                    boundary = min(x, nx) if dx else min(y, ny)
                    minima = crossing_minima[direction_index]
                    if energy < minima[boundary]:
                        minima[boundary] = energy
                    edge_count += 1
        self._direction_minima = tuple(
            min((cost for cost in row if math.isfinite(cost)), default=0.0)
            for row in crossing_minima
        )
        self._crossing_costs = None
        if any(math.isfinite(cost) and cost != minimum
               for row, minimum in zip(crossing_minima, self._direction_minima) for cost in row):
            self._crossing_costs = tuple(
                tuple(accumulate((minimum if math.isinf(cost) else cost for cost in row), initial=0.0))
                for row, minimum in zip(crossing_minima, self._direction_minima)
            )
        self._graph = tuple(tuple(edges) for edges in self._graph)
        self.edge_count = edge_count
        self.edge_model_calls = len(edge_values)
        self.build_time_ms = (time.perf_counter() - started) * 1000.0

    @staticmethod
    def _point(value):
        if len(value) != 2 or any(type(v) is not int for v in value):
            raise ValueError("grid endpoints must contain two integers")
        return tuple(value)

    def _contains(self, point):
        return 0 <= point[0] < self.width and 0 <= point[1] < self.height

    def return_costs_along(self, path):
        """Yield elapsed seconds, spent Wh and minimum Wh back to the start."""
        nodes = [y * self.width + x for x, y in path]
        home = nodes[0]

        # Search incoming edges from home, retaining each edge's flight direction and cost.
        incoming = [[] for _ in self._graph]
        for source, edges in enumerate(self._graph):
            for target, _, energy in edges:
                incoming[target].append((source, energy))
        remaining = set(nodes)
        return_costs = {}
        best = {home: 0.0}
        queue = [(0.0, home)]
        while queue and remaining:
            cost, node = heapq.heappop(queue)
            if cost != best[node]:
                continue
            if node in remaining:
                return_costs[node] = cost
                remaining.remove(node)
            for previous, energy in incoming[node]:
                candidate = cost + energy
                if candidate < best.get(previous, math.inf):
                    best[previous] = candidate
                    heapq.heappush(queue, (candidate, previous))

        elapsed = spent = 0.0
        for index, node in enumerate(nodes):
            if index:
                _, seconds, energy = next(edge for edge in self._graph[nodes[index - 1]] if edge[0] == node)
                elapsed += seconds
                spent += energy
            yield elapsed, spent, return_costs.get(node)

    def plan(self, start, goal, objective="energy"):
        """Return legacy-compatible route fields plus actual search timings.

        ``build_time_ms`` is reported separately from ``query_time_ms``.
        A cached query expands zero nodes; ``uncached_expanded_nodes`` retains
        the count from its original search. At most 256 routes are retained.
        """
        started = time.perf_counter()
        if objective not in ("distance", "energy"):
            raise ValueError("unsupported objective")
        start, goal = self._point(start), self._point(goal)
        key = (start, goal, objective)
        if key in self._cache:
            self._cache.move_to_end(key)
            result = copy.deepcopy(self._cache[key])
            result.update(cache_hit=True, expanded_nodes=0,
                          query_time_ms=(time.perf_counter() - started) * 1000.0)
            return result

        def finish(result):
            result.update(objective=objective, cost_source=self.cost_source,
                          planner_version=PLANNER_VERSION, cache_hit=False,
                          build_time_ms=self.build_time_ms,
                          query_time_ms=(time.perf_counter() - started) * 1000.0)
            result.setdefault("expanded_nodes", 0)
            result["uncached_expanded_nodes"] = result["expanded_nodes"]
            self._cache[key] = copy.deepcopy(result)
            if len(self._cache) > 256:
                self._cache.popitem(last=False)
            return result

        if not self._contains(start) or not self._contains(goal):
            return finish({"status": "unreachable", "reason": "endpoint_outside_map", "path": []})
        if start in self.blocked or goal in self.blocked:
            return finish({"status": "unreachable", "reason": "blocked_endpoint", "path": []})

        goal_x, goal_y = goal
        width = self.width
        cell_size = self.cell_size_m
        if objective == "distance":
            def heuristic(index):
                y, x = divmod(index, width)
                return abs(goal_x - x) * cell_size + abs(goal_y - y) * cell_size
        elif self._crossing_costs is None:
            east, west, positive_y, negative_y = self._direction_minima

            def heuristic(index):
                y, x = divmod(index, width)
                dx, dy = goal_x - x, goal_y - y
                return (dx * east if dx >= 0 else -dx * west) + (
                    dy * positive_y if dy >= 0 else -dy * negative_y)
        else:
            east, west, positive_y, negative_y = self._crossing_costs

            def heuristic(index):
                y, x = divmod(index, width)
                across = east[goal_x] - east[x] if x <= goal_x else west[x] - west[goal_x]
                along = positive_y[goal_y] - positive_y[y] if y <= goal_y else negative_y[y] - negative_y[goal_y]
                return across + along

        start_id, goal_id = start[1] * width + start[0], goal[1] * width + goal[0]
        scores = {start_id: 0.0}
        parents = {}
        queue = [(heuristic(start_id), 0.0, start_id)]
        expanded = 0
        while queue:
            _, negative_cost, point = heapq.heappop(queue)
            cost = -negative_cost
            if cost != scores[point]:
                continue
            expanded += 1
            if point == goal_id:
                path = [point]
                duration = energy = 0.0
                while path[-1] != start_id:
                    previous, edge_seconds, edge_wh = parents[path[-1]]
                    path.append(previous)
                    duration += edge_seconds
                    energy += edge_wh
                path.reverse()
                return finish({"status": "planned",
                               "path": [[node % width, node // width] for node in path],
                               "distance_m": (len(path) - 1) * self.cell_size_m,
                               "duration_s": duration, "estimated_energy_wh": energy,
                               "cost": cost, "expanded_nodes": expanded})
            for neighbor, duration, energy in self._graph[point]:
                edge_cost = self.cell_size_m if objective == "distance" else energy
                candidate = cost + edge_cost
                if candidate < scores.get(neighbor, math.inf):
                    scores[neighbor] = candidate
                    parents[neighbor] = (point, duration, energy)
                    heapq.heappush(queue, (candidate + heuristic(neighbor), -candidate, neighbor))
        return finish({"status": "unreachable", "reason": "no_feasible_path",
                       "path": [], "expanded_nodes": expanded})
