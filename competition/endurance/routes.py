"""Use the fitted discharge model for both endurance and A* edge costs."""
from __future__ import annotations

import math

from .contracts import PredictionInput, ReplanInput, RouteGrid, RouteInput, RoutingConditions
from .model import EnduranceModel
from .pathfinding import GridPlanner, PLANNER_VERSION

CHARGE_TOLERANCE_AH = 1e-10


def example_grid(wind_speed_ms, wind_direction_deg=0):
    """A short inspection round trip with a sheltered lane one row north.

    The sheltered lane is a scenario assumption. Its lower observed wind is
    supplied to the planner as current information, not as a future event.
    """
    angle = math.radians(wind_direction_deg)
    wind = [wind_speed_ms * math.cos(angle), wind_speed_ms * math.sin(angle)]
    return RouteGrid(width=16, height=12, cell_size_m=10,
                     blocked=[(7, 2), (7, 3), (7, 8), (7, 9), (10, 9), (11, 9)],
                     wind_regions=[
                         {"x_min": 0, "x_max": 15, "y_min": 0, "y_max": 11, "vector": wind},
                         {"x_min": 0, "x_max": 15, "y_min": 4.5, "y_max": 5.5, "vector": [0, 0]},
                     ])


def make_edge_model(model: EnduranceModel, ground_speed_ms, max_airspeed_ms):
    def edge(direction, wind):
        along = wind[0] * direction[0] + wind[1] * direction[1]
        cross = -wind[0] * direction[1] + wind[1] * direction[0]
        if abs(cross) > max_airspeed_ms:
            return None
        along_air_limit = math.sqrt(max_airspeed_ms ** 2 - cross ** 2)
        minimum_ground_speed = max(.25, along - along_air_limit)
        maximum_ground_speed = along + along_air_limit
        if maximum_ground_speed < minimum_ground_speed:
            return None
        # In a strong tailwind the aircraft may also be unable to slow down
        # to its requested ground speed. Choose the nearest feasible speed.
        speed = max(minimum_ground_speed, min(ground_speed_ms, maximum_ground_speed))
        current = model.current_a(math.hypot(*wind), speed)
        return speed, current * model.nominal_voltage_v
    return edge


def return_limit(planner, outward, prediction, reserve_budget):
    """Find the furthest outbound waypoint that still allows a return."""
    if outward["status"] != "planned":
        return {"status": "outbound_unreachable"}
    inputs = prediction["inputs"]
    if inputs["battery_percent"] < inputs["reserve_percent"]:
        return {"status": "start_below_reserve"}

    path = outward["path"]
    voltage = prediction["nominal_voltage_v"]
    full = prediction["full_capacity_ah"]
    last = None
    for index, (position, costs) in enumerate(zip(path, planner.return_costs_along(path))):
        elapsed, spent, back = costs
        point = {"position": position, "distance_m": index * planner.cell_size_m, "duration_s": elapsed}
        charge = (spent + back) / voltage if back is not None else math.inf
        if charge > reserve_budget + CHARGE_TOLERANCE_AH:
            return {"status": "turn_back", "last_feasible": last, "first_limited": point,
                    "reason": "return_unreachable" if back is None else "reserve_shortfall"}

        # Spent energy plus minimum return cost is nondecreasing: returning
        # via the next waypoint is one of the choices at the current point.
        percent = max(0., inputs["battery_percent"] - charge / full * 100) if full else 0.
        last = {**point, "remaining_battery_percent": percent}
    return {"status": "goal_with_reserve", "last_feasible": last}


def planning_context(request: RoutingConditions, grid: RouteGrid, model: EnduranceModel):
    winds = [region.model_dump() for region in grid.wind_regions]
    # A custom map may override local wind. With no regions the three-input
    # forecast wind applies everywhere, rather than silently becoming calm.
    if not winds:
        angle = math.radians(request.wind_direction_deg)
        winds = [{"x_min": 0, "x_max": grid.width - 1, "y_min": 0, "y_max": grid.height - 1,
                  "vector": [request.wind_speed_ms * math.cos(angle), request.wind_speed_ms * math.sin(angle)]}]
    planner = GridPlanner(grid.width, grid.height, grid.blocked, winds, grid.cell_size_m,
                          edge_model=make_edge_model(model, request.ground_speed_ms, request.max_airspeed_ms))
    conditions = PredictionInput.model_validate(request.model_dump(include=set(PredictionInput.model_fields)))
    return model.predict_input(conditions), planner, winds


def plan_leg(planner, model, start, goal, objective="energy"):
    leg = planner.plan(start, goal, objective)
    leg["cost_source"] = model.version
    if leg["status"] == "planned":
        leg["estimated_consumption_ah"] = leg["estimated_energy_wh"] / model.nominal_voltage_v
    return leg


def plan_round_trip(request: RouteInput, model: EnduranceModel | None = None):
    model = model or EnduranceModel()
    grid = request.grid or example_grid(request.wind_speed_ms, request.wind_direction_deg)
    start, goal = request.start or (1, 6), request.goal or (14, 6)
    prediction, planner, winds = planning_context(request, grid, model)
    full = prediction["full_capacity_ah"]
    reserve_budget = prediction["available_capacity_ah"] - full * request.reserve_percent / 100

    def route(objective):
        outward = plan_leg(planner, model, start, goal, objective)
        inward = plan_leg(planner, model, goal, start, objective)
        if outward["status"] != "planned" or inward["status"] != "planned":
            return {"status": "unreachable", "outbound": outward, "inbound": inward,
                    "feasible_with_reserve": False,
                    "expanded_nodes": outward.get("expanded_nodes", 0) + inward.get("expanded_nodes", 0),
                    "reason": "去程或返程在当前障碍、风场及最大空速下不可达"}
        energy = outward["estimated_energy_wh"] + inward["estimated_energy_wh"]
        charge = energy / model.nominal_voltage_v
        return {"status": "planned", "outbound": outward, "inbound": inward,
                "distance_m": outward["distance_m"] + inward["distance_m"],
                "duration_s": outward["duration_s"] + inward["duration_s"],
                "estimated_energy_wh": energy, "estimated_consumption_ah": charge,
                "remaining_battery_percent": max(0., request.battery_percent - charge / full * 100) if full else 0.,
                "feasible_with_reserve": request.battery_percent >= request.reserve_percent
                and charge <= reserve_budget + CHARGE_TOLERANCE_AH,
                "capacity_deficit_ah": max(0., charge - reserve_budget),
                "expanded_nodes": outward["expanded_nodes"] + inward["expanded_nodes"]}

    energy, distance = route("energy"), route("distance")
    saving = None
    if energy["status"] == distance["status"] == "planned":
        baseline = distance["estimated_energy_wh"]
        saving = max(0., (baseline - energy["estimated_energy_wh"]) / baseline * 100) if baseline else 0.
    return {"model_version": model.version, "planner_version": PLANNER_VERSION,
            "prediction": prediction, "grid": {**grid.model_dump(), "wind_regions": winds},
            "start": list(start), "goal": list(goal), "energy_route": energy, "distance_route": distance,
            "return_limit": return_limit(planner, energy["outbound"], prediction, reserve_budget),
            "saving_percent": saving, "build_time_ms": planner.build_time_ms,
            "edge_model_calls": planner.edge_model_calls,
            "route_assumptions": {"max_airspeed_ms": request.max_airspeed_ms,
                                  "wind_direction_convention": "degrees counterclockwise from +x; vector points downwind",
                                  "current_model_direction": "wind magnitude and ground speed; no fitted heading effect",
                                  "round_trip": True, "takeoff_landing_included": False}}


def replan_from_current(request: ReplanInput, model: EnduranceModel | None = None):
    """Choose remaining mission legs from the latest observed map and charge."""
    model = model or EnduranceModel()
    prediction, planner, _ = planning_context(request, request.grid, model)
    full = prediction["full_capacity_ah"]
    available = prediction["available_capacity_ah"]
    reserve = full * request.reserve_percent / 100
    result = {"model_version": model.version, "planner_version": PLANNER_VERSION,
              "available_capacity_ah": available, "reserve_capacity_ah": reserve}

    def leg(start, goal):
        return plan_leg(planner, model, start, goal)

    def fits_reserve(charge):
        return request.battery_percent >= request.reserve_percent and charge <= available - reserve + CHARGE_TOLERANCE_AH

    def decision(action, legs, charge, reason):
        return {**result, "action": action, "reason": reason, "legs": legs,
                "estimated_consumption_ah": charge,
                "remaining_battery_percent": max(0., (available - charge) / full * 100) if full else 0.,
                "feasible_with_reserve": fits_reserve(charge)}

    reason = "return_requested"
    if request.goal is not None:
        outbound = leg(request.current, request.goal)
        if outbound["status"] != "planned":
            reason = "goal_unreachable"
        else:
            inbound = leg(request.goal, request.base)
            if inbound["status"] != "planned":
                reason = "goal_return_unreachable"
            else:
                charge = outbound["estimated_consumption_ah"] + inbound["estimated_consumption_ah"]
                if fits_reserve(charge):
                    return decision("continue_to_goal", [outbound, inbound], charge, "goal_with_reserve")
                reason = "goal_reserve_shortfall"

    candidates = []
    for target in dict.fromkeys([request.base, *request.alternates]):
        route = leg(request.current, target)
        if route["status"] == "planned":
            charge = route["estimated_consumption_ah"]
            action = "return_to_base" if target == request.base else "divert"
            if action == "return_to_base" and fits_reserve(charge):
                return decision(action, [route], charge, reason)
            if charge <= available:
                candidates.append((charge, action, route))
    if candidates:
        # Minimizing charge maximizes arrival reserve; exact ties keep input order.
        charge, action, route = min(candidates, key=lambda candidate: candidate[0])
        return decision(action, [route], charge, reason)
    return {**result, "action": "no_feasible_landing", "reason": reason,
            "legs": [], "feasible_with_reserve": False}
