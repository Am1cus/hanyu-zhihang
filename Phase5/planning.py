"""Four-neighbour A* baseline with explicit scenario costs, in metres or Wh."""
import argparse
import heapq
import json
import math
from pathlib import Path


def positive(value, name, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: finite number required")
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name}: invalid sign")
    return value


def plan(scenario, objective="distance"):
    """Cost of an energy edge = entered cell's Wh/m * cell size. No diagonals."""
    if objective not in ("distance", "energy"):
        raise ValueError("objective must be distance or energy")
    w, h = scenario["width"], scenario["height"]
    if any(type(n) is not int or n < 1 for n in (w, h)) or w * h > 1_000_000:
        raise ValueError("invalid grid dimensions")
    cell = positive(scenario["cell_size_m"], "cell_size_m")

    def point(p):
        if not isinstance(p, (tuple, list)) or len(p) != 2 or any(type(v) is not int for v in p):
            raise ValueError("coordinates must be integer [x, y]")
        if not (0 <= p[0] < w and 0 <= p[1] < h):
            raise ValueError("coordinate outside grid")
        return tuple(p)

    start, goal = point(scenario["start"]), point(scenario["goal"])
    blocked = {point(p) for p in scenario.get("blocked", [])}
    costs = scenario.get("energy_wh_per_m")
    if costs is not None:
        if len(costs) != h or any(len(row) != w for row in costs):
            raise ValueError("energy cost grid must cover all cells")
        for y in range(h):
            for x in range(w):
                if (x, y) not in blocked:
                    positive(costs[y][x], "energy_wh_per_m")
    if objective == "energy" and costs is None:
        return {"status": "unavailable", "reason": "missing_segment_energy_costs"}
    if start in blocked or goal in blocked:
        return {"status": "unreachable", "reason": "blocked_endpoint"}
    minimum = min(costs[y][x] for y in range(h) for x in range(w) if (x, y) not in blocked) if objective == "energy" else 1

    def heuristic(p):
        return (abs(p[0] - goal[0]) + abs(p[1] - goal[1])) * cell * minimum

    queue = [(heuristic(start), 0.0, start)]
    best, parent, expanded = {start: 0.0}, {}, 0
    while queue:
        _, total, current = heapq.heappop(queue)
        if total != best[current]:
            continue
        expanded += 1
        if current == goal:
            path = [goal]
            while path[-1] != start:
                path.append(parent[path[-1]])
            path.reverse()
            return {"status": "planned", "objective": objective,
                    "path": [list(p) for p in path], "distance_m": (len(path) - 1) * cell,
                    "estimated_energy_wh": sum(costs[y][x] * cell for x, y in path[1:]) if costs is not None else None,
                    "cost": total, "cost_unit": "Wh" if objective == "energy" else "m",
                    "expanded_nodes": expanded, "execution": "offline_only",
                    "cost_source": scenario.get("cost_source", "unspecified_not_validated")}
        x, y = current
        for nx, ny in ((x+1,y), (x-1,y), (x,y+1), (x,y-1)):
            nxt = (nx, ny)
            if not (0 <= nx < w and 0 <= ny < h) or nxt in blocked:
                continue
            candidate = total + cell * (costs[ny][nx] if objective == "energy" else 1)
            if candidate < best.get(nxt, math.inf):
                best[nxt], parent[nxt] = candidate, current
                heapq.heappush(queue, (candidate + heuristic(nxt), candidate, nxt))
    return {"status": "unreachable", "reason": "no_path", "expanded_nodes": expanded}


def mission_budget(outbound, return_route, available_wh, reserve_wh):
    """Compare explicit usable Wh against BOTH routes and reserve; never infer Wh from Ah."""
    if available_wh is None or reserve_wh is None:
        return {"status": "unavailable", "reason": "missing_usable_energy_or_reserve"}
    positive(available_wh, "available_wh", True)
    positive(reserve_wh, "reserve_wh", True)
    energies = []
    for route in (outbound, return_route):
        if route.get("status") != "planned" or route.get("estimated_energy_wh") is None:
            return {"status": "unavailable", "reason": "missing_outbound_or_return_energy"}
        energies.append(positive(route["estimated_energy_wh"], "route_energy", True))
    needed = sum(energies) + reserve_wh
    return {"status": "budget_sufficient" if available_wh >= needed else "budget_exceeded",
            "required_wh": needed, "available_wh": available_wh, "reserve_wh": reserve_wh,
            "margin_wh": available_wh - needed, "execution": "offline_only",
            "limitation": "Conditional on supplied costs and usable energy; not a flight safety decision."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--objective", choices=["distance", "energy"], default="distance")
    args = parser.parse_args()
    scenario = json.loads(args.scenario.read_text())
    outbound = plan(scenario, args.objective)
    returning = plan({**scenario, "start": scenario["goal"], "goal": scenario["start"]}, args.objective)
    print(json.dumps({"outbound": outbound, "return": returning,
                      "budget": mission_budget(outbound, returning, scenario.get("available_wh"), scenario.get("reserve_wh"))}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
