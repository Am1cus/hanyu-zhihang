"""Choose optional tasks from one current snapshot, without executing them.

All selectors use the same directed leg table and ``assess_order`` budget.
Subset DP is exact for the additive, static costs of this snapshot (within
floating-point precision), not for unknown future weather or obstacles.
"""
from __future__ import annotations

import math
from time import perf_counter

from .contracts import (
    CONTRACT_VERSION, DecisionRecord, DecisionRequest, DeferredTask,
    fingerprint, validate_decision_for_request,
)
from .planning_inputs import assess_order, build_leg_table


SELECTOR_VERSION = "competition-v2-selectors-0.1"


def _remaining(request):
    completed = set(request.observation.completed_task_ids)
    return tuple(task for task in request.task_catalog if task.id not in completed)


def _prefix_cost(request, legs, order):
    """Stable summation of transit and service, excluding the final return."""
    tasks = {task.id: task for task in request.task_catalog}
    previous = "CURRENT"
    transit, service = [], []
    for target in order:
        leg = legs[(previous, target)]
        transit.append(leg.energy_wh)
        service.append(tasks[target].dwell_s * request.model.estimated_power_w / 3600)
        previous = target
    transit_wh, service_wh = math.fsum(transit), math.fsum(service)
    return transit_wh, service_wh


def _route_cost(request, legs, order):
    transit, service = _prefix_cost(request, legs, order)
    last = order[-1] if order else "CURRENT"
    return math.fsum((transit, service, legs[(last, "BASE")].energy_wh))


def _greedy_order(request, legs):
    """Append feasible tasks; each trial includes the whole prefix and return."""
    remaining = list(_remaining(request))
    order = ()
    while remaining:
        if request.selector_id == "fixed_order":
            chosen = remaining[0]
            if assess_order(request, legs, (*order, chosen.id)).status != "SUFFICIENT":
                break
        else:
            previous = order[-1] if order else "CURRENT"
            candidates = []
            for task in remaining:
                trial = (*order, task.id)
                if assess_order(request, legs, trial).status != "SUFFICIENT":
                    continue
                outbound = legs[(previous, task.id)]
                if request.selector_id == "nearest_feasible":
                    rank = (outbound.distance_m, task.id)
                else:
                    cost = math.fsum((outbound.energy_wh,
                                      task.dwell_s * request.model.estimated_power_w / 3600,
                                      legs[(task.id, "BASE")].energy_wh))
                    ratio = task.value / cost if cost else math.inf
                    rank = (-ratio, cost, task.id)
                candidates.append((rank, task))
            if not candidates:
                break
            chosen = min(candidates, key=lambda item: item[0])[1]
        order = (*order, chosen.id)
        remaining = [task for task in remaining if task.id != chosen.id]
    return order


def _subset_order(request, legs):
    """Keep a minimum-energy prefix for each (visited mask, final task).

    Budget feasibility is checked with the shared assessor, including directed
    return, reserve and the selected uncertainty policy. Energy ranks use fsum
    and strict comparisons; exact ties use the full task-ID tuple. Validation
    compares numerical energy within 1e-7 Wh and checks ID ties on exact cases.
    """
    tasks = tuple(sorted(_remaining(request), key=lambda task: task.id))
    states = {}
    for index, task in enumerate(tasks):
        leg = legs.get(("CURRENT", task.id))
        if leg is not None and leg.status == "PLANNED":
            order = (task.id,)
            states[(1 << index, index)] = (math.fsum(_prefix_cost(request, legs, order)), order)

    for mask in range(1, 1 << len(tasks)):
        for last in range(len(tasks)):
            current = states.get((mask, last))
            if current is None:
                continue
            _, order = current
            for target, task in enumerate(tasks):
                if mask & (1 << target):
                    continue
                leg = legs.get((tasks[last].id, task.id))
                if leg is None or leg.status != "PLANNED":
                    continue
                next_order = (*order, task.id)
                candidate = (math.fsum(_prefix_cost(request, legs, next_order)), next_order)
                state = (mask | (1 << target), target)
                if state not in states or candidate < states[state]:
                    states[state] = candidate

    best_rank, best_order = None, ()
    for (mask, _), (_, order) in states.items():
        if assess_order(request, legs, order).status != "SUFFICIENT":
            continue
        value = sum(task.value for index, task in enumerate(tasks) if mask & (1 << index))
        rank = (-value, _route_cost(request, legs, order), order)
        if best_rank is None or rank < best_rank:
            best_rank, best_order = rank, order
    return best_order


def select_order(request: DecisionRequest, legs) -> tuple[str, ...]:
    """Pure task-order selection; ``decide`` adds action and full accounting.

    ``legs`` is the common current-observation table, supplied separately for
    controlled static tests. A returned order is a plan, never completed work.
    """
    if request.observation.data_status != "AVAILABLE":
        return ()
    if request.selector_id == "subset_dp":
        return _subset_order(request, legs)
    return _greedy_order(request, legs)


def _deferred(request, legs, selected):
    selected = set(selected)
    records = []
    for task in _remaining(request):
        if task.id in selected:
            continue
        if request.observation.data_status != "AVAILABLE":
            reason = "DATA_UNAVAILABLE"
        else:
            single = assess_order(request, legs, (task.id,))
            if single.status == "UNAVAILABLE":
                reason = ("UNREACHABLE" if single.reason in {"task_unreachable", "return_unreachable"}
                          else "DATA_UNAVAILABLE")
            elif single.status == "INSUFFICIENT":
                reason = "BUDGET"
            else:
                # The wire name is shared by all policies. It means feasible
                # alone but not chosen by this policy, not an unimportant task.
                reason = "LOWER_VALUE_PLAN"
        records.append(DeferredTask(id=task.id, reason=reason,
                                    follow_up_state="REQUIRES_OPERATOR_REVIEW"))
    return tuple(records)


def decide(request: DecisionRequest) -> DecisionRecord:
    """Return a validated decision using only the supplied current snapshot.

    At base, no feasible optional task produces REFUSED, including energy below
    the reserve. Away from base, an impossible return produces STOP. RETURN
    itself never establishes arrival at the base or execution of any task.
    ``computation_ms`` includes graph construction and is nondeterministic;
    exclude this timing field when comparing repeatable decision contents.
    """
    started = perf_counter()
    legs = build_leg_table(request)
    returning = assess_order(request, legs, ())
    remaining = _remaining(request)
    order = ()
    budget = returning
    if request.observation.data_status != "AVAILABLE":
        action, reason = "STOP", "DATA_UNAVAILABLE"
    elif returning.status == "UNAVAILABLE":
        action = "STOP"
        reason = ("RETURN_UNREACHABLE" if returning.reason == "return_unreachable"
                  else "DATA_UNAVAILABLE")
    elif not remaining:
        action, reason = (("RETURN", "ALL_TASKS_VISITED") if returning.status == "SUFFICIENT"
                          else ("STOP", "RETURN_BUDGET_INSUFFICIENT"))
    elif returning.status == "INSUFFICIENT":
        action, reason = (("REFUSED", "NO_FEASIBLE_TASK")
                          if request.observation.position == request.observation.base
                          else ("STOP", "RETURN_BUDGET_INSUFFICIENT"))
    else:
        order = select_order(request, legs)
        if order:
            budget = assess_order(request, legs, order)
            action, reason = "CONTINUE", "PLAN_SELECTED"
        else:
            action = ("REFUSED" if request.observation.position == request.observation.base else "RETURN")
            reason = "NO_FEASIBLE_TASK"

    deferred = _deferred(request, legs, order)
    record = DecisionRecord(
        contract_version=CONTRACT_VERSION, request_sha256=fingerprint(request),
        as_of_s=request.observation.as_of_s, selector_id=request.selector_id,
        budget_mode=request.budget.mode, action=action, reason_code=reason,
        ordered_task_ids=order, deferred_tasks=deferred, budget=budget,
        computation_ms=(perf_counter() - started) * 1000,
    )
    return validate_decision_for_request(request, record)
