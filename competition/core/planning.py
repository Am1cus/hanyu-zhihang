"""Directed four-neighbour A*: known current wind, never future events."""
import heapq
import math

ESTIMATOR_VERSION = "constant_current_4.2v_per_cell_upper_v1"
UPPER_POWER_W = 4.2 * 4 * 4.2


def wind_at(position, regions):
    x, y = position
    for region in reversed(regions):
        if region["x_min"] <= x <= region["x_max"] and region["y_min"] <= y <= region["y_max"]:
            return tuple(region["vector"])
    return (0.0, 0.0)


def ground_speed(a, b, regions, airspeed_ms=5.0):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0
    ux, uy = dx / length, dy / length
    wx, wy = wind_at(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), regions)
    along, cross = wx * ux + wy * uy, -wx * uy + wy * ux
    if abs(cross) >= airspeed_ms:
        return None
    speed = math.sqrt(airspeed_ms ** 2 - cross ** 2) + along
    return speed if speed > .25 else None


def plan(start, goal, width, height, blocked, wind_regions, cell_size_m=80.0, objective="energy", airspeed_ms=5.0, power_w=UPPER_POWER_W):
    if objective not in ("distance", "energy"):
        raise ValueError("unsupported objective")
    start, goal = tuple(start), tuple(goal)
    blocked = {tuple(p) for p in blocked}
    if not all(0 <= p[0] < width and 0 <= p[1] < height for p in (start, goal)):
        return {"status": "unreachable", "reason": "endpoint_outside_map", "path": []}
    if start in blocked or goal in blocked:
        return {"status": "unreachable", "reason": "blocked_endpoint", "path": []}
    max_wind = max((math.hypot(*r["vector"]) for r in wind_regions), default=0)
    minimum_cost = cell_size_m if objective == "distance" else power_w * cell_size_m / (airspeed_ms + max_wind) / 3600

    def heuristic(p):
        return (abs(p[0] - goal[0]) + abs(p[1] - goal[1])) * minimum_cost

    queue = [(heuristic(start), 0.0, start)]
    best, parents, expanded = {start: 0.0}, {}, 0
    while queue:
        _, cost, point = heapq.heappop(queue)
        if cost != best[point]:
            continue
        expanded += 1
        if point == goal:
            path = [point]
            while path[-1] != start:
                path.append(parents[path[-1]])
            path.reverse()
            duration = sum(cell_size_m / ground_speed(a, b, wind_regions, airspeed_ms) for a, b in zip(path, path[1:]))
            return {"status": "planned", "path": [list(p) for p in path], "distance_m": (len(path) - 1) * cell_size_m,
                    "duration_s": duration, "estimated_energy_wh": duration * power_w / 3600,
                    "objective": objective, "cost": cost, "expanded_nodes": expanded,
                    "cost_source": ESTIMATOR_VERSION}
        x, y = point
        for next_point in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            nx, ny = next_point
            if not (0 <= nx < width and 0 <= ny < height) or next_point in blocked:
                continue
            speed = ground_speed(point, next_point, wind_regions, airspeed_ms)
            if speed is None:
                continue
            edge_cost = cell_size_m if objective == "distance" else power_w * cell_size_m / speed / 3600
            candidate = cost + edge_cost
            if candidate < best.get(next_point, math.inf):
                best[next_point], parents[next_point] = candidate, point
                heapq.heappush(queue, (candidate + heuristic(next_point), candidate, next_point))
    return {"status": "unreachable", "reason": "no_feasible_path", "path": [], "expanded_nodes": expanded}
