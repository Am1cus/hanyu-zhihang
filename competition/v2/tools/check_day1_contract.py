"""Exact, dependency-free check of the v2 design on a five-task teaching case.

This is an exhaustive reference calculator, not the online planner or a flight
simulator. No v1 imports, API calls, UI changes or production data writes occur.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
from fractions import Fraction
from pathlib import Path


def number(value):
    return Fraction(str(value))


def matrix(case):
    """Explicit directed energy costs; the geometric rule is a toy definition."""
    costs = {}
    rule = case["cost_rule"]
    for a, (ax, ay) in case["positions"].items():
        for b, (bx, by) in case["positions"].items():
            dx = bx - ax
            costs[a, b] = (
                number(rule["east_wh_per_unit"]) * max(dx, 0)
                + number(rule["west_wh_per_unit"]) * max(-dx, 0)
                + number(rule["north_south_wh_per_unit"]) * abs(by - ay)
            )
    return costs


def budget(case, mode):
    if mode not in ("nominal", "bounded"):
        raise ValueError("unknown_budget_mode")
    energy = number(case["available_wh"])
    multiplier = Fraction(1)
    if mode == "bounded":
        energy *= 1 - number(case["available_fraction_error"])
        multiplier += number(case["cost_fraction_error"])
    return energy, multiplier, number(case["reserve_wh"])


def route_cost(case, costs, route):
    tasks = {t["id"]: t for t in case["tasks"]}
    previous, total = case["base"], Fraction(0)
    for target in route:
        edge = costs[previous, target]
        if edge is None:
            return None
        total += edge + number(tasks[target]["service_wh"])
        previous = target
    returning = costs[previous, case["base"]]
    return None if returning is None else total + returning


def margin(case, mode, cost):
    energy, multiplier, reserve = budget(case, mode)
    return energy - cost * multiplier - reserve


def result(case, costs, route, mode):
    cost = route_cost(case, costs, route)
    tasks = {t["id"]: t for t in case["tasks"]}
    energy, multiplier, reserve = budget(case, mode)
    return {
        "status": "PLAN_SELECTED" if route else "NO_FEASIBLE_TASK",
        "route": list(route),
        "value": sum(tasks[t]["value"] for t in route),
        "route_wh": str(cost),
        "assessed_route_wh": str(cost * multiplier),
        "assessed_available_wh": str(energy),
        "reserve_wh": str(reserve),
        "margin_wh": str(margin(case, mode, cost)),
        "actual_return_verified": False,
    }


def check_inputs(case, costs):
    nodes = {case["base"], *(t["id"] for t in case["tasks"])}
    # Missing means unknown data. None explicitly means unreachable.
    if any((a, b) not in costs for a in nodes for b in nodes):
        raise ValueError("missing_directed_cost")
    if any(c is not None and c < 0 for c in costs.values()):
        raise ValueError("negative_cost")


def solve_exact(case, costs, mode):
    check_inputs(case, costs)
    ids = tuple(t["id"] for t in case["tasks"])
    if len(ids) > 8 or len(set(ids)) != len(ids):
        raise ValueError("reference_calculator_requires_at_most_8_unique_tasks")
    values = {t["id"]: t["value"] for t in case["tasks"]}
    best_key, best_route, considered = None, (), 0
    for length in range(len(ids) + 1):
        for route in itertools.permutations(ids, length):
            considered += 1
            cost = route_cost(case, costs, route)
            if cost is None or margin(case, mode, cost) < 0:
                continue
            # Highest value, then lowest assessed energy, then stable ID order.
            key = (-sum(values[t] for t in route), cost, route)
            if best_key is None or key < best_key:
                best_key, best_route = key, route
    if best_key is None:
        return {"status": "RESERVE_ALREADY_UNMET", "route": [], "considered": considered}
    return {**result(case, costs, best_route, mode), "considered": considered}


def solve_greedy(case, costs, mode, selector):
    check_inputs(case, costs)
    remaining = [t["id"] for t in case["tasks"]]
    tasks = {t["id"]: t for t in case["tasks"]}
    route = []
    while remaining:
        current = route[-1] if route else case["base"]
        feasible = [t for t in remaining
                    if (cost := route_cost(case, costs, route + [t])) is not None
                    and margin(case, mode, cost) >= 0]
        if not feasible:
            break
        if selector == "fixed_order":
            # Prefix policy: it returns when the next required point cannot fit.
            if remaining[0] not in feasible:
                break
            target = remaining[0]
        elif selector == "nearest_feasible":
            ax, ay = case["positions"][current]
            target = min(feasible, key=lambda t: (
                abs(case["positions"][t][0] - ax)
                + abs(case["positions"][t][1] - ay), t))
        elif selector == "value_per_cost":
            def rank(t):
                prospective = (costs[current, t] + number(tasks[t]["service_wh"])
                               + costs[t, case["base"]])
                return (-Fraction(tasks[t]["value"]) / prospective, prospective, t)
            target = min(feasible, key=rank)
        else:
            raise ValueError("unknown_selector")
        route.append(target)
        remaining.remove(target)
    return result(case, costs, route, mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "fixtures" / "day1_example.json"
    case = json.loads(source.read_text(encoding="utf-8"))
    costs = matrix(case)
    checks, examples = [], {}

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})

    for mode in ("nominal", "bounded"):
        exact = solve_exact(case, costs, mode)
        expected = case["expected"][mode]
        examples[mode] = {selector: solve_greedy(case, costs, mode, selector)
                          for selector in ("fixed_order", "nearest_feasible", "value_per_cost")}
        examples[mode]["exhaustive_reference"] = exact
        check(mode + "_matches_hand_calculation", exact["route"] == expected["route"]
              and exact["value"] == expected["value"]
              and number(exact["route_wh"]) == number(expected["route_wh"])
              and number(exact["margin_wh"]) == number(expected["margin_wh"]))
        check(mode + "_all_326_ordered_subsets_checked", exact["considered"] == 326)
    check("return_cost_is_directional", route_cost(case, costs, ("A",)) == number("2.7"))
    check("exact_reference_not_always_better_than_strong_greedy",
          examples["nominal"]["value_per_cost"]["value"]
          == examples["nominal"]["exhaustive_reference"]["value"])

    empty = copy.deepcopy(case)
    empty["available_wh"] = empty["reserve_wh"]
    check("no_task_when_only_reserve_remains", solve_exact(empty, costs, "nominal")["status"] == "NO_FEASIBLE_TASK")
    blocked = costs.copy()
    for task in case["tasks"]:
        blocked[task["id"], case["base"]] = None
    check("unreachable_return_not_treated_as_zero", solve_exact(case, blocked, "nominal")["status"] == "NO_FEASIBLE_TASK")
    missing = costs.copy()
    del missing[case["base"], "C"]
    try:
        solve_exact(case, missing, "nominal")
    except ValueError as exc:
        missing_rejected = str(exc) == "missing_directed_cost"
    else:
        missing_rejected = False
    check("missing_cost_is_data_error", missing_rejected)

    # Replay arithmetic for the fixed C-only plan, not simulated flight evidence.
    selected_cost = route_cost(case, costs, ("C",))
    stress = []
    for error in ("0", "0.1", "0.3"):
        available = number(case["available_wh"]) * (1 - number(case["available_fraction_error"]))
        consumed = selected_cost * (1 + number(error))
        reserve_margin = available - consumed - number(case["reserve_wh"])
        stress.append({"cost_fraction_error": error, "available_wh": str(available),
                       "consumed_wh": str(consumed), "remaining_wh": str(available - consumed),
                       "reserve_margin_wh": str(reserve_margin), "reserve_violated": reserve_margin < 0})
    check("declared_error_boundary_retains_reserve", not stress[1]["reserve_violated"])
    check("out_of_bound_error_can_violate_reserve", stress[2]["reserve_violated"])

    report = {"schema_version": 1, "source": case["source"], "case_id": case["id"],
              "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "checks": checks, "passed": all(c["passed"] for c in checks),
              "examples": examples, "fixed_route_error_arithmetic": stress,
              "interpretation": "Design handcheck only; no flight, no formal benchmark, no implemented online v2 planner."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "output": str(args.output),
                      "nominal_exact": examples["nominal"]["exhaustive_reference"],
                      "bounded_exact": examples["bounded"]["exhaustive_reference"]}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
