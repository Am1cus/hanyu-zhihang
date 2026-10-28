"""Independent ordered-subset enumeration for static selector verification.

This is a small-input reference, not an execution simulator or a new planner.
It can share the directed A* leg table with a selector because its purpose is
to check selection, ordering and budget arithmetic, not to independently
validate A*. No selector implementation or ``assess_order`` is used here.
"""
from __future__ import annotations

from itertools import permutations
from math import fsum

from .contracts import DecisionRequest, fingerprint
from .planning_inputs import build_leg_table


REFERENCE_VERSION = "ordered-subset-enumeration-0.1"


def brute_force_reference(request: DecisionRequest, legs=None):
    """Enumerate every ordered subset, including empty, under current data.

    Strict energy ordering breaks equal-value ties; equal energy is resolved
    by the lexicographic tuple of task IDs. The 1e-7 Wh tolerance applies only
    to feasibility. Results describe a proposed route, never completed work.
    A missing or mismatched edge means incomplete data, not zero energy.
    """
    result = {
        "version": REFERENCE_VERSION,
        "request_sha256": fingerprint(request),
        "status": "DATA_UNAVAILABLE",
        "best_order": None,
        "best_value": None,
        "route_wh": None,
        "assessed_available_wh": None,
        "assessed_demand_wh": None,
        "margin_wh": None,
        "enumerated_orders": 0,
        "feasible_orders": 0,
        "execution_verified": False,
    }
    if request.observation.data_status != "AVAILABLE":
        return result
    legs = build_leg_table(request) if legs is None else legs
    done = set(request.observation.completed_task_ids)
    tasks = {t.id: t for t in request.task_catalog if t.id not in done}
    identifiers = tuple(sorted(tasks))
    nodes = ("CURRENT", "BASE", *identifiers)
    # Require a complete directed table so omitted information cannot hide a
    # better candidate or silently make a task appear unreachable.
    for origin in nodes:
        for target in nodes:
            edge = legs.get((origin, target))
            if edge is None or (edge.from_id, edge.to_id) != (origin, target):
                return result

    available = request.observation.available_wh_estimate
    multiplier = 1.0
    if request.budget.mode == "bounded":
        available *= 1.0 - request.budget.available_fraction_error
        multiplier += request.budget.cost_fraction_error
    result["assessed_available_wh"] = available
    result["status"] = "NO_FEASIBLE_PLAN"
    best_key = None
    for size in range(len(identifiers) + 1):
        for order in permutations(identifiers, size):
            result["enumerated_orders"] += 1
            path = ("CURRENT", *order, "BASE")
            edges = [legs[a, b] for a, b in zip(path, path[1:])]
            if any(edge.status != "PLANNED" for edge in edges):
                continue
            transit = fsum(edge.energy_wh for edge in edges[:-1])
            service = fsum(tasks[t].dwell_s * request.model.estimated_power_w / 3600 for t in order)
            route = fsum((transit, service, edges[-1].energy_wh))
            demand = route * multiplier + request.budget.reserve_wh
            margin = available - demand
            if margin < -1e-7:
                continue
            result["feasible_orders"] += 1
            value = sum(tasks[t].value for t in order)
            key = (-value, route, order)
            if best_key is None or key < best_key:
                best_key = key
                result.update(status="FEASIBLE_PLAN", best_order=list(order), best_value=value,
                              route_wh=route, assessed_demand_wh=demand, margin_wh=margin)
    return result
