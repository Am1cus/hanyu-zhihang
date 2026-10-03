"""Bounded deterministic task execution, separated from the conservative planner.

Wind changes travel time under constant 5 m/s airspeed. Electrical execution is
an explicitly ideal 4S1P constant 4.2 A reference model, not drone dynamics.
Planner sees current map/wind and estimates at 4.2 V/cell. Only this executor
owns the future event queue and digitized voltage-versus-charge integration.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
import uuid

from .curves import CurveLibrary
from .planning import ESTIMATOR_VERSION, UPPER_POWER_W, ground_speed, plan, wind_at
from .scenarios import get_scenario

CORE_VERSION = "mission-core-v1.1"
SOURCE = "LOCAL_2D_SIM"
TERMINAL = {"COMPLETED", "CANCELLED", "FAILED", "UNAVAILABLE"}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def compare_runs(distance, energy):
    a, b = distance.summary(), energy.summary()
    def inputs(run):
        config = {k: v for k, v in run.configuration.items() if k not in ("strategy", "speedup", "manual_events")}
        config["applied_manual_events"] = [{"t_s": e["t_s"], "payload": e["payload"]} for e in run.events
                                           if e["source"] == "manual" and e["applied"]]
        config["scheduled_event_application"] = [{"t_s": e["t_s"], "payload": e["payload"], "applied": e["applied"]}
                                                 for e in run.events if e["source"] == "scheduled"]
        return canonical_hash(config)

    same_inputs = inputs(distance) == inputs(energy)
    comparable = (same_inputs and a["returned"] and b["returned"] and a["visited_count"] == b["visited_count"]
                  and a["visited_count"] > 0 and a["reserve_margin_wh"] is not None
                  and b["reserve_margin_wh"] is not None and min(a["reserve_margin_wh"], b["reserve_margin_wh"]) >= -1e-7)
    saving = (a["total_energy_wh"] - b["total_energy_wh"]) / a["total_energy_wh"] * 100 if comparable and a["total_energy_wh"] > 0 else None
    return {"status": "comparable" if comparable else "not_comparable", "energy_saving_pct": saving,
            "completion_difference": b["mission_completion_ratio"] - a["mission_completion_ratio"],
            "same_inputs": same_inputs,
            "reason": "same_nonzero_work_and_return_reserve" if comparable else "different_inputs" if not same_inputs else "different_or_zero_work_failed_return_or_reserve",
            "estimator": ESTIMATOR_VERSION, "data_source": SOURCE,
            "interpretation": "Executed reference-model Wh, not actual aircraft energy savings."}


class MissionRun:
    def __init__(self, configuration, library: CurveLibrary, run_id=None):
        self.library, self.id = library, run_id or str(uuid.uuid4())
        config = copy.deepcopy(configuration)
        scenario = config.get("scenario") or get_scenario(config.get("scenario_id", "normal-s1"))
        self.scenario = copy.deepcopy(scenario)
        self.strategy = config.get("strategy", "energy")
        self.temperature_c = float(config.get("temperature_c", -10))
        self.reserve_fraction = float(config.get("reserve_fraction", .2))
        self.speedup = float(config.get("speedup", 20))
        self.load_mismatch_fraction = float(config.get("load_mismatch_fraction", 0))
        self.wind_observation_bias_ms = float(config.get("wind_observation_bias_ms", 0))
        if self.strategy not in ("distance", "energy"):
            raise ValueError("strategy must be distance or energy")
        if not math.isfinite(self.reserve_fraction) or not 0 <= self.reserve_fraction <= .5:
            raise ValueError("reserve_fraction must be between 0 and 0.5")
        if not math.isfinite(self.speedup) or not 1 <= self.speedup <= 200:
            raise ValueError("speedup must be between 1 and 200")
        if not math.isfinite(self.load_mismatch_fraction) or not -.5 <= self.load_mismatch_fraction <= .5:
            raise ValueError("load_mismatch_fraction must be between -0.5 and 0.5")
        if not math.isfinite(self.wind_observation_bias_ms) or abs(self.wind_observation_bias_ms) > 2:
            raise ValueError("wind_observation_bias_ms must be within +/-2")
        self.estimated_power_w = UPPER_POWER_W / (1 + self.load_mismatch_fraction)
        self.configuration = {"scenario_id": scenario["id"], "scenario": copy.deepcopy(scenario),
                              "strategy": self.strategy, "temperature_c": self.temperature_c,
                              "reserve_fraction": self.reserve_fraction, "speedup": self.speedup,
                              "data_source": SOURCE, "core_version": CORE_VERSION, "curve_sha256": library.sha256,
                              "estimator_version": ESTIMATOR_VERSION,
                              "load_mismatch_fraction": self.load_mismatch_fraction,
                              "wind_observation_bias_ms": self.wind_observation_bias_ms,
                              "scenario_sha256": canonical_hash(scenario),
                              "manual_events": copy.deepcopy(config.get("manual_events", []))}
        if config.get("termination_control"):
            self.configuration["termination_control"] = copy.deepcopy(config["termination_control"])
        self.t_s = 0.0
        self._requested_s = 0.0
        self.position = list(map(float, scenario["start"]))
        self.node = tuple(scenario["start"])
        self.blocked = {tuple(p) for p in scenario["blocked"]}
        self.wind_regions = copy.deepcopy(scenario["wind_regions"])
        self.path, self.visited_targets = [], []
        self.telemetry, self.decisions, self.events, self.planned_routes = [], [], [], []
        self.executed_path = [list(self.position)]
        self.currentbudget = {"status": "unavailable", "explanation": "parameters_not_loaded"}
        self.whole_mission_budget = {"status": "unavailable", "explanation": "parameters_not_loaded", "feasible_prefix_count": None}
        self.initial_whole_mission_budget = copy.deepcopy(self.whole_mission_budget)
        self.status, self.stage, self.ended_reason = "RUNNING", "OUTBOUND", None
        self.returned = False
        self.q, self.initial_q, self.initial_wh, self.reserve_wh, self.consumed_wh = 0.0, 0.0, None, None, 0.0
        self.route_distance_m, self.dwell_remaining_s = 0.0, 0.0
        self.pending_replan = False
        self.response_metrics = []
        self._pending_response_indices = []
        self.planning_comparison = {}
        # This private queue is intentionally not passed into plan().
        self._queue = [{**copy.deepcopy(e), "source": "scheduled"} for e in scenario["scheduled_events"]]
        self._queue += [{**copy.deepcopy(e["payload"]), "at_s": e["t_s"], "source": "manual"}
                        for e in config.get("manual_events", [])]
        if config.get("termination_control"):
            self._queue.append({"at_s": config["termination_control"]["t_s"], "type": "cancel", "source": "control"})
        self._queue.sort(key=lambda e: e["at_s"])
        try:
            self.curve = library.curve(self.temperature_c)
            self.initial_q = (1 - scenario["initial_soc"]) * self.curve.capacity_ah
            self.q = self.initial_q
            self.initial_wh = self.curve.energy_between(self.q, self.curve.capacity_ah)
            self.reserve_wh = library.reference_wh * self.reserve_fraction
        except ValueError as exc:
            self.status, self.stage, self.ended_reason = "UNAVAILABLE", "TERMINAL", str(exc)
            self.currentbudget["explanation"] = str(exc)
            return
        self._record(0.0)
        for objective in ("distance", "energy"):
            self.planning_comparison[objective] = self._plan(self.node, scenario["targets"][0], objective)
        self.whole_mission_budget = self._whole_budget()
        self.initial_whole_mission_budget = copy.deepcopy(self.whole_mission_budget)
        self._choose_route("mission_started")

    @property
    def remaining_wh(self):
        return None if self.initial_wh is None else max(0.0, self.initial_wh - self.consumed_wh)

    def _plan(self, start, goal, objective=None):
        return plan(start, goal, self.scenario["width"], self.scenario["height"], self.blocked,
                    self.observed_wind_regions(), self.scenario["cell_size_m"], objective or self.strategy,
                    self.scenario["airspeed_ms"], self.estimated_power_w)

    def observed_wind_regions(self):
        regions = copy.deepcopy(self.wind_regions)
        bias = self.wind_observation_bias_ms
        if bias:
            for region in regions:
                region["vector"][0] += bias
            regions.insert(0, {"id": "observation_bias_background", "x_min": 0, "x_max": self.scenario["width"],
                               "y_min": 0, "y_max": self.scenario["height"], "vector": [bias, 0.0]})
        return regions

    def _budget(self, outbound, return_route, dwell_s=0):
        if outbound.get("status") != "planned" or return_route.get("status") != "planned":
            return {"status": "unavailable", "explanation": "next_task_or_return_path_unavailable",
                    "available_wh": self.remaining_wh, "required_wh": None, "next_task_wh": None,
                    "return_wh": None, "reserve_wh": self.reserve_wh, "margin_wh": None, "as_of_s": self.t_s}
        next_wh = outbound["estimated_energy_wh"] + dwell_s * self.estimated_power_w / 3600
        return_wh = return_route["estimated_energy_wh"]
        required = next_wh + return_wh + self.reserve_wh
        return {"status": "sufficient" if self.remaining_wh + 1e-8 >= required else "insufficient",
                "explanation": "known_current_wind_and_upper_voltage_budget_not_real_flight_safety",
                "available_wh": self.remaining_wh, "required_wh": required,
                "next_task_wh": next_wh, "return_wh": return_wh, "reserve_wh": self.reserve_wh,
                "margin_wh": self.remaining_wh - required, "as_of_s": self.t_s}

    def _decision(self, decision, reason, budget, path):
        self.decisions.append({"t_s": self.t_s, "decision": decision, "reason": reason,
                               "budget": copy.deepcopy(budget), "path": copy.deepcopy(path)})
        self.planned_routes.append({"t_s": self.t_s, "path": copy.deepcopy(path), "decision": decision})

    def _whole_budget(self):
        remaining_targets = self.scenario["targets"][len(self.visited_targets):]
        position = self.node
        task_wh, prefix, legs = 0.0, 0, []
        last_return = self._plan(position, self.scenario["start"])
        unavailable = None
        for index, target in enumerate(remaining_targets):
            route = self._plan(position, target)
            returning = self._plan(target, self.scenario["start"])
            if route["status"] != "planned" or returning["status"] != "planned":
                unavailable = "remaining_task_or_return_path_unavailable"
                break
            task_wh += route["estimated_energy_wh"] + self.scenario["dwell_s"] * self.estimated_power_w / 3600
            legs.append({"kind": "task", "target": target, "path": route["path"],
                         "distance_m": route["distance_m"], "estimated_energy_wh": route["estimated_energy_wh"],
                         "dwell_wh": self.scenario["dwell_s"] * self.estimated_power_w / 3600})
            needed = task_wh + returning["estimated_energy_wh"] + self.reserve_wh
            if needed <= self.remaining_wh + 1e-8 and prefix == index:
                prefix += 1
            position, last_return = tuple(target), returning
        if unavailable or last_return["status"] != "planned":
            return {"status": "unavailable", "available_wh": self.remaining_wh, "required_wh": None,
                    "mission_task_wh": None, "return_wh": None, "reserve_wh": self.reserve_wh,
                    "margin_wh": None, "feasible_prefix_count": prefix, "remaining_target_count": len(remaining_targets),
                    "target_count": len(self.scenario["targets"]), "as_of_s": self.t_s,
                    "explanation": unavailable or "return_path_unavailable", "planned_legs": legs}
        return_wh = last_return["estimated_energy_wh"]
        required = task_wh + return_wh + self.reserve_wh
        return {"status": "sufficient" if required <= self.remaining_wh + 1e-8 else "insufficient",
                "available_wh": self.remaining_wh, "required_wh": required, "mission_task_wh": task_wh,
                "return_wh": return_wh, "reserve_wh": self.reserve_wh, "margin_wh": self.remaining_wh - required,
                "feasible_prefix_count": prefix, "remaining_target_count": len(remaining_targets),
                "target_count": len(self.scenario["targets"]), "as_of_s": self.t_s,
                "explanation": "all_remaining_ordered_targets_dwell_final_return_and_reference_reserve_current_wind_only",
                "planned_legs": legs + [{"kind": "return", "path": last_return["path"], "estimated_energy_wh": return_wh,
                                        "distance_m": last_return["distance_m"]}]}

    def _end(self, status, reason):
        self.status, self.stage, self.ended_reason = status, "TERMINAL", reason
        self.path = []
        if self.telemetry:
            self.telemetry[-1]["groundspeed_ms"] = 0.0
            self.telemetry[-1]["stage"] = "TERMINAL"

    def cancel(self):
        if self.status in TERMINAL:
            raise ValueError("terminal_run_control_refused")
        self.configuration["termination_control"] = {"t_s": self.t_s, "action": "cancel", "reason": "operator_cancelled"}
        self._end("CANCELLED", "operator_cancelled")

    def _finish_pending_response(self, compute_ms):
        for index in self._pending_response_indices:
            metric = self.response_metrics[index]
            metric.update(decision_compute_ms=compute_ms, decision_t_s=self.t_s,
                          simulated_reaction_s=self.t_s - metric["event_t_s"])
        self._pending_response_indices = []

    def _return_route(self, reason, failed_task_budget=None):
        returning = self._plan(self.node, self.scenario["start"])
        if returning["status"] != "planned":
            self._decision("cannot_return", "return_path_unavailable", failed_task_budget or self.currentbudget, [])
            self._end("FAILED", "return_path_unavailable")
            return
        zero = {"status": "planned", "estimated_energy_wh": 0}
        return_budget = self._budget(zero, returning)
        self.currentbudget = return_budget
        if reason != "node_reached":
            self._decision("return", reason, failed_task_budget or return_budget, returning["path"])
        if returning["estimated_energy_wh"] > self.remaining_wh + 1e-8:
            self._end("FAILED", "return_energy_unavailable")
            return
        self.stage, self.path = "RETURN", returning["path"]
        if len(self.path) == 1:
            self.returned = True
            ended = "all_targets_visited" if len(self.visited_targets) == len(self.scenario["targets"]) else "budget_or_route_rejected_at_base"
            self._end("COMPLETED", ended)

    def _choose_route(self, reason):
        started = time.perf_counter()
        self._choose_route_impl(reason)
        if self._pending_response_indices:
            elapsed_ms = (time.perf_counter() - started) * 1000
            self._finish_pending_response(elapsed_ms)

    def _choose_route_impl(self, reason):
        if self.status != "RUNNING":
            return
        self.pending_replan = False
        self.whole_mission_budget = self._whole_budget()
        if self.stage == "RETURN" or len(self.visited_targets) == len(self.scenario["targets"]):
            self._return_route(reason)
            return
        target = self.scenario["targets"][len(self.visited_targets)]
        outgoing, returning = self._plan(self.node, target), self._plan(target, self.scenario["start"])
        budget = self._budget(outgoing, returning, self.scenario["dwell_s"])
        self.currentbudget = budget
        if budget["status"] != "sufficient":
            self._return_route("next_task_budget_insufficient" if budget["status"] == "insufficient" else "next_task_unreachable", budget)
            return
        self.stage, self.path = "OUTBOUND", outgoing["path"]
        if reason != "node_reached":
            self._decision("continue_task", reason, budget, self.path)
        if len(self.path) == 1:
            self.stage, self.dwell_remaining_s = "DWELL", self.scenario["dwell_s"]

    def validate_event(self, payload):
        if payload.get("type") == "wind":
            wind = payload.get("wind")
            if not isinstance(wind, list) or len(wind) != 2 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or abs(x) > 15 for x in wind):
                raise ValueError("wind requires two finite components within +/-15 m/s")
            return {"type": "wind", "wind": list(map(float, wind))}
        if payload.get("type") == "obstacle":
            cells = payload.get("cells")
            if not isinstance(cells, list) or not 1 <= len(cells) <= 100:
                raise ValueError("obstacle requires 1..100 cells")
            occupied = {self.node}
            if len(self.path) > 1:
                occupied.add(tuple(self.path[1]))
            checked = []
            for point in cells:
                if not isinstance(point, list) or len(point) != 2 or any(type(x) is not int for x in point):
                    raise ValueError("obstacle cells must be integer coordinates")
                x, y = point
                if not (0 <= x < self.scenario["width"] and 0 <= y < self.scenario["height"]):
                    raise ValueError("obstacle outside map")
                if tuple(point) in occupied or point == self.scenario["start"]:
                    raise ValueError("cannot add an obstacle on the occupied edge or base")
                checked.append(point)
            return {"type": "obstacle", "cells": checked}
        raise ValueError("event type must be wind or obstacle")

    def apply_event(self, payload, source="manual"):
        started = time.perf_counter()
        if self.status not in ("RUNNING", "PAUSED"):
            raise ValueError("terminal run does not accept events")
        normalized = self.validate_event(payload)
        if normalized["type"] == "wind":
            self.wind_regions[0]["vector"] = normalized["wind"]
        else:
            self.blocked.update(tuple(p) for p in normalized["cells"])
        event = {"event_id": f"event-{len(self.events) + 1}", "t_s": self.t_s,
                 "type": normalized["type"], "source": source, "payload": normalized, "applied": True}
        self.events.append(event)
        self.response_metrics.append({"event_id": event["event_id"], "event_t_s": self.t_s,
                                      "event_compute_ms": None, "decision_compute_ms": None,
                                      "decision_t_s": None, "simulated_reaction_s": None,
                                      "timing_boundary": "event_validation_update_and_immediate_planning; separate_node_decision_cpu_and_simulated_delay"})
        index = len(self.response_metrics) - 1
        self._pending_response_indices.append(index)
        self.pending_replan = True
        if self.position == list(map(float, self.node)) and self.stage != "DWELL" and self.status == "RUNNING":
            self._choose_route("event_applied")
        elif self.pending_replan:
            self.currentbudget.update(status="unavailable", pending_replan=True,
                                      explanation="event_applied_waiting_for_next_grid_node_decision")
        self.response_metrics[index]["event_compute_ms"] = (time.perf_counter() - started) * 1000
        return event

    def _record(self, groundspeed):
        voltage = self.curve.voltage(self.q) * self.library.series_cells
        self.telemetry.append({"t_s": self.t_s, "position": list(self.position), "voltage_v": voltage,
                               "current_a": self.library.current_a, "power_w": voltage * self.library.current_a,
                               "discharged_wh": self.consumed_wh, "remaining_usable_wh": self.remaining_wh,
                               "discharged_ah": self.q - self.initial_q,
                               "wind": list(wind_at(self.position, self.wind_regions)),
                               "groundspeed_ms": groundspeed, "stage": self.stage})

    def advance(self, duration_s):
        if not math.isfinite(duration_s) or duration_s < 0:
            raise ValueError("nonnegative finite duration required")
        if self.status != "RUNNING":
            return self
        self._requested_s += duration_s
        until = self._requested_s
        loops = 0
        while self.status == "RUNNING" and self.t_s < until - 1e-10:
            loops += 1
            if loops > 100000:
                self._end("FAILED", "step_iteration_limit")
                break
            while self._queue and self._queue[0]["at_s"] <= self.t_s + 1e-9:
                event = self._queue.pop(0)
                if event["type"] == "cancel":
                    self._end("CANCELLED", "operator_cancelled")
                    break
                try:
                    self.apply_event(event, event["source"])
                except ValueError as exc:
                    self.events.append({"event_id": f"event-{len(self.events) + 1}", "t_s": self.t_s,
                                        "type": event["type"], "source": event["source"], "payload": event,
                                        "applied": False, "reason": str(exc)})
            if self.status != "RUNNING":
                break
            if self.t_s >= 10000:
                self._end("FAILED", "simulation_time_limit")
                break
            next_grid_time = (math.floor((self.t_s + 1e-9) / .5) + 1) * .5
            dt = min(next_grid_time - self.t_s, self.curve.seconds_to_next_knot(self.q, self.library.current_a))
            if self._queue:
                dt = min(dt, max(0.0, self._queue[0]["at_s"] - self.t_s))
            moving = self.stage in ("OUTBOUND", "RETURN")
            speed = 0.0
            if moving:
                if len(self.path) < 2:
                    self._choose_route("path_finished")
                    continue
                a, b = self.path[0], self.path[1]
                decision_started = time.perf_counter()
                speed = ground_speed(a, b, self.wind_regions, self.scenario["airspeed_ms"])
                if speed is None:
                    self._decision("cannot_execute", "wind_exceeds_track_hold_model", self.currentbudget, self.path)
                    self._finish_pending_response((time.perf_counter() - decision_started) * 1000)
                    self._end("FAILED", "wind_exceeds_track_hold_model")
                    break
                left_m = math.dist(self.position, b) * self.scenario["cell_size_m"]
                dt = min(dt, left_m / speed)
            elif self.stage == "DWELL":
                dt = min(dt, self.dwell_remaining_s)
            else:
                self._end("FAILED", "invalid_execution_stage")
                break
            # Fixed simulation sample/event boundaries: browser polling and speedup
            # never change the numerical execution or make extra partial samples.
            if dt > until - self.t_s + 1e-9:
                break
            if dt < 1e-10:
                if self.q >= self.curve.capacity_ah - 1e-10:
                    self._end("FAILED", "battery_curve_cutoff")
                    break
                # Snap only a numerically reached node, never a physical teleport.
                if moving and math.dist(self.position, self.path[1]) < 1e-8:
                    self.position = list(map(float, self.path[1]))
                    self._arrive_node()
                    continue
                self._end("FAILED", "zero_step")
                break
            previous_q = self.q
            self.q = min(self.curve.capacity_ah, self.q + self.library.current_a * dt / 3600)
            self.consumed_wh += self.curve.energy_between(previous_q, self.q)
            self.t_s += dt
            if moving:
                remaining_grid = math.dist(self.position, b)
                traveled_grid = min(remaining_grid, speed * dt / self.scenario["cell_size_m"])
                direction = [(b[i] - self.position[i]) / remaining_grid for i in (0, 1)]
                self.position = [self.position[i] + direction[i] * traveled_grid for i in (0, 1)]
                self.route_distance_m += traveled_grid * self.scenario["cell_size_m"]
            else:
                self.dwell_remaining_s = max(0.0, self.dwell_remaining_s - dt)
            self._record(speed)
            if not self.executed_path or math.dist(self.executed_path[-1], self.position) > .08:
                self.executed_path.append(list(self.position))
            if self.currentbudget.get("required_wh") is not None:
                field = "return_wh" if self.stage == "RETURN" else "next_task_wh"
                self.currentbudget[field] = max(0.0, self.currentbudget[field] - self.estimated_power_w * dt / 3600)
                self.currentbudget["required_wh"] = self.currentbudget["next_task_wh"] + self.currentbudget["return_wh"] + self.reserve_wh
                self.currentbudget["available_wh"] = self.remaining_wh
                self.currentbudget["margin_wh"] = self.remaining_wh - self.currentbudget["required_wh"]
                self.currentbudget["as_of_s"] = self.t_s
                if not self.currentbudget.get("pending_replan"):
                    self.currentbudget["status"] = "sufficient" if self.currentbudget["margin_wh"] >= -1e-8 else "insufficient"
            if self.q >= self.curve.capacity_ah - 1e-10:
                self._end("FAILED", "battery_curve_cutoff")
            elif moving and math.dist(self.position, b) < 1e-8:
                self.position = list(map(float, b))
                self._arrive_node()
            elif self.stage == "DWELL" and self.dwell_remaining_s <= 1e-9:
                self.visited_targets.append(list(self.node))
                self._choose_route("task_point_completed")
        return self

    def _arrive_node(self):
        self.node = tuple(self.path[1])
        self.path = self.path[1:]
        if self.stage == "RETURN" and self.node == tuple(self.scenario["start"]):
            self.returned = True
            self._end("COMPLETED", "all_targets_visited" if len(self.visited_targets) == len(self.scenario["targets"]) else "partial_task_returned")
        elif self.stage == "OUTBOUND" and self.node == tuple(self.scenario["targets"][len(self.visited_targets)]):
            self.stage, self.dwell_remaining_s = "DWELL", self.scenario["dwell_s"]
            self.path = [list(self.node)]
        else:
            self._choose_route("event_applied" if self.pending_replan else "node_reached")

    def run_all(self, max_seconds=10000):
        if self.status == "RUNNING":
            self.advance(max(0.0, max_seconds - self._requested_s))
        if self.status == "RUNNING":
            self._end("FAILED", "evaluation_time_limit")
        return self

    def summary(self):
        targets = len(self.scenario["targets"])
        return {"mission_completion_ratio": len(self.visited_targets) / targets, "visited_count": len(self.visited_targets),
                "target_count": targets, "returned": self.returned, "ended_reason": self.ended_reason,
                "total_energy_wh": self.consumed_wh if self.initial_wh is not None else None,
                "duration_s": self.t_s, "reserve_margin_wh": None if self.remaining_wh is None else self.remaining_wh - self.reserve_wh,
                "route_distance_m": self.route_distance_m, "initial_usable_wh": self.initial_wh,
                "remaining_usable_wh": self.remaining_wh, "reserve_wh": self.reserve_wh,
                "initial_soc": self.scenario["initial_soc"], "data_source": SOURCE,
                "validated_on_real_drone": False}

    def emitted_configuration(self):
        configuration = copy.deepcopy(self.configuration)
        configuration["manual_events"] = [{"t_s": e["t_s"], "payload": e["payload"]} for e in self.events
                                           if e["source"] == "manual" and e["applied"]]
        return configuration

    def state(self):
        parameter_status = self.library.status()
        parameter_status["profile_kind"] = "source_node" if self.temperature_c in self.library.curves else "temperature_interpolation"
        return {"id": self.id, "status": self.status, "scenario_id": self.scenario["id"], "strategy": self.strategy,
                "temperature_c": self.temperature_c, "reserve_fraction": self.reserve_fraction, "speedup": self.speedup,
                "t_s": self.t_s, "stage": self.stage, "width": self.scenario["width"], "height": self.scenario["height"],
                "cell_size_m": self.scenario["cell_size_m"], "start": self.scenario["start"], "targets": self.scenario["targets"],
                "visited_targets": self.visited_targets, "path": self.path, "position": self.position,
                "blocked": [list(p) for p in sorted(self.blocked)],
                "wind": {"regions": self.wind_regions, "current": list(wind_at(self.position, self.wind_regions)),
                         "observed_regions": self.observed_wind_regions(), "observed_current": list(wind_at(self.position, self.observed_wind_regions()))},
                "telemetry": self.telemetry[-300:], "decisions": self.decisions, "events": self.events,
                "executed_path": self.executed_path, "planned_routes": self.planned_routes,
                "planning_comparison": self.planning_comparison, "currentbudget": self.currentbudget,
                "whole_mission_budget": self.whole_mission_budget,
                "initial_whole_mission_budget": self.initial_whole_mission_budget,
                "response_metrics": self.response_metrics,
                "summary": self.summary(), "parameter_status": parameter_status,
                "configuration_sha256": canonical_hash(self.emitted_configuration())}

    def export(self):
        configuration = self.emitted_configuration()
        return {"metadata": {"schema_version": 1, "data_source": SOURCE, "core_version": CORE_VERSION,
                             "curve_sha256": self.library.sha256, "configuration_sha256": canonical_hash(configuration),
                             "not_real_aircraft_validation": True},
                "configuration": configuration, "state": self.state(), "summary": self.summary(),
                "telemetry": self.telemetry, "decisions": self.decisions, "events": self.events,
                "response_metrics": self.response_metrics,
                "executed_path": self.executed_path,
                "result_sha256": canonical_hash({"summary": self.summary(), "telemetry": self.telemetry,
                                                  "decisions": self.decisions, "events": self.events})}
