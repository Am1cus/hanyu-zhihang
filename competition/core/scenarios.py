"""Synthetic software scenarios: not maps or measurements from an actual park."""
import copy
import hashlib
import json

SCENARIO_VERSION = "local-2d-scenarios-v1"
FORMAL_TEMPERATURES = (0, -10, -20)
KINDS = ("normal", "low_budget", "gust", "dynamic_obstacle")


def build_scenarios():
    result = []
    names = {"normal": "正常巡检", "low_budget": "低初始能量", "gust": "中部区域突风", "dynamic_obstacle": "动态障碍"}
    for kind in KINDS:
        for seed in (1, 2):
            # Fixed minor geometry variation; no tuning after formal evaluation.
            targets = [[12, 3], [19, 7], [12, 11]] if seed == 1 else [[12, 4], [19, 8], [12, 11]]
            events = []
            if kind == "gust":
                events = [{"at_s": 120, "type": "wind", "wind": [-3.0, 0.0]}]
            elif kind == "dynamic_obstacle":
                events = [{"at_s": 120, "type": "obstacle", "cells": [[10, y] for y in range(5, 10)]}]
            result.append({"id": f"{kind}-s{seed}", "name": f"{names[kind]} · 场景 {seed}",
                           "category": kind, "seed": seed, "width": 22, "height": 14, "cell_size_m": 80.0,
                           "start": [1, 7], "targets": targets, "blocked": [[8, 6], [8, 7], [8, 8]],
                           "wind_regions": [{"id": "central", "x_min": 8, "x_max": 14,
                                             "y_min": 1, "y_max": 12, "vector": [-2.0, 0.0]}],
                           "scheduled_events": events, "initial_soc": .55 if kind == "low_budget" else 1.0,
                           "dwell_s": 10.0, "airspeed_ms": 5.0, "fixed_height_m": 40,
                           "provenance": "synthetic_software_scenario_not_a_real_park",
                           "scenario_version": SCENARIO_VERSION})
    return result


SCENARIOS = build_scenarios()
SCENARIO_MAP = {s["id"]: s for s in SCENARIOS}


def get_scenario(scenario_id):
    if scenario_id not in SCENARIO_MAP:
        raise ValueError("unknown_scenario_id")
    return copy.deepcopy(SCENARIO_MAP[scenario_id])


def formal_manifest():
    cases = [{"scenario_id": s["id"], "temperature_c": t, "reserve_fraction": .2, "strategies": ["distance", "energy"]}
             for t in FORMAL_TEMPERATURES for s in SCENARIOS]
    frozen = {"schema_version": 1, "scenario_version": SCENARIO_VERSION, "scenarios": SCENARIOS,
              "cases": cases, "independent_real_flights": 0, "software_scenarios": len(cases),
              "paired_executions": len(cases) * 2,
              "policy": "same_estimator_reserve_and_information_only_route_objective_changes"}
    content = json.dumps(frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**frozen, "manifest_sha256": hashlib.sha256(content.encode()).hexdigest()}
