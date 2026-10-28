"""Build directed route estimates and budgets; task selection arrives in D3."""
from __future__ import annotations

from competition.core.planning import plan
from .contracts import BudgetAssessment, DecisionRequest, GridMap, LegEstimate


def plan_leg(grid: GridMap, start, goal, from_id, to_id, airspeed_ms, power_w):
    raw = plan(start, goal, grid.width, grid.height, grid.blocked,
               [w.model_dump(mode="json") for w in grid.wind_regions], grid.cell_size_m,
               objective="energy", airspeed_ms=airspeed_ms, power_w=power_w)
    if raw["status"] != "planned":
        return LegEstimate(from_id=from_id, to_id=to_id, status="UNREACHABLE", path=(),
                           distance_m=None, duration_s=None, energy_wh=None, reason=raw["reason"])
    return LegEstimate(from_id=from_id, to_id=to_id, status="PLANNED", path=raw["path"],
                       distance_m=raw["distance_m"], duration_s=raw["duration_s"],
                       energy_wh=raw["estimated_energy_wh"], reason=None)


def build_leg_table(request: DecisionRequest):
    if request.observation.data_status != "AVAILABLE":
        return {}
    nodes = {"BASE": request.observation.base, "CURRENT": request.observation.position}
    nodes.update({t.id: t.position for t in request.task_catalog
                  if t.id not in request.observation.completed_task_ids})
    return {(a, b): plan_leg(request.observation.known_map, pa, pb, a, b,
                             request.model.airspeed_ms, request.model.estimated_power_w)
            for a, pa in nodes.items() for b, pb in nodes.items()}


def assess_order(request: DecisionRequest, legs, order):
    order = tuple(order)
    tasks = {t.id: t for t in request.task_catalog}
    if len(set(order)) != len(order) or not set(order).issubset(tasks):
        raise ValueError("duplicate_or_unknown_selected_task")
    if set(order) & set(request.observation.completed_task_ids):
        raise ValueError("completed_task_cannot_be_selected_again")

    def unavailable(reason):
        return BudgetAssessment(status="UNAVAILABLE", ordered_task_ids=order, transit_wh=None, service_wh=None,
                                return_wh=None, reserve_wh=request.budget.reserve_wh,
                                assessed_available_wh=None, assessed_demand_wh=None, margin_wh=None, reason=reason)
    if request.observation.data_status != "AVAILABLE":
        return unavailable(request.observation.unavailable_reason)
    transit = service = 0.0
    previous = "CURRENT"
    for target in (*order, "BASE"):
        leg = legs.get((previous, target))
        if leg is None:
            return unavailable("missing_directed_leg")
        if leg.from_id != previous or leg.to_id != target:
            return unavailable("leg_identity_mismatch")
        if leg.status != "PLANNED":
            return unavailable("return_unreachable" if target == "BASE" else "task_unreachable")
        if target == "BASE":
            returning = leg.energy_wh
        else:
            transit += leg.energy_wh
            service += tasks[target].dwell_s * request.model.estimated_power_w / 3600
        previous = target
    available = request.observation.available_wh_estimate
    route = transit + service + returning
    if request.budget.mode == "bounded":
        available *= 1 - request.budget.available_fraction_error
        route *= 1 + request.budget.cost_fraction_error
    demand = route + request.budget.reserve_wh
    margin = available - demand
    return BudgetAssessment(status="SUFFICIENT" if margin >= -1e-7 else "INSUFFICIENT", ordered_task_ids=order,
                            transit_wh=transit, service_wh=service, return_wh=returning,
                            reserve_wh=request.budget.reserve_wh, assessed_available_wh=available,
                            assessed_demand_wh=demand, margin_wh=margin, reason="current_observation_budget_only")
