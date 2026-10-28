"""Strict wire contracts for current observations, never executor future state."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator

CONTRACT_VERSION = "competition-v2-contract-0.3"
Point = tuple[StrictInt, StrictInt]
Vector = tuple[StrictFloat, StrictFloat]
NonNegative = Annotated[StrictFloat, Field(ge=0)]
Positive = Annotated[StrictFloat, Field(gt=0)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")]
Selector = Literal["fixed_order", "nearest_feasible", "value_per_cost", "subset_dp"]
BudgetMode = Literal["nominal", "bounded"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, validate_default=True)


class WindRegion(Record):
    id: Identifier
    x_min: StrictInt
    x_max: StrictInt
    y_min: StrictInt
    y_max: StrictInt
    vector: Vector

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.x_min > self.x_max or self.y_min > self.y_max:
            raise ValueError("wind_bounds_reversed")
        return self


class GridMap(Record):
    width: Annotated[StrictInt, Field(ge=2, le=256)]
    height: Annotated[StrictInt, Field(ge=2, le=256)]
    cell_size_m: Positive
    blocked: tuple[Point, ...]
    wind_regions: tuple[WindRegion, ...]
    blocked_cell_meaning: Literal["fixed_altitude_2d_exclusion_area"]

    def contains(self, point):
        return 0 <= point[0] < self.width and 0 <= point[1] < self.height

    @model_validator(mode="after")
    def geometry(self):
        if len(set(self.blocked)) != len(self.blocked) or any(not self.contains(p) for p in self.blocked):
            raise ValueError("invalid_or_duplicate_blocked_cell")
        if len({r.id for r in self.wind_regions}) != len(self.wind_regions):
            raise ValueError("duplicate_wind_region")
        if any(not self.contains((r.x_min, r.y_min)) or not self.contains((r.x_max, r.y_max))
               for r in self.wind_regions):
            raise ValueError("wind_region_outside_map")
        return self


class Task(Record):
    id: Identifier
    label: str
    position: Point
    value: Annotated[StrictInt, Field(ge=1, le=100)]
    dwell_s: NonNegative
    value_source: Literal["synthetic_assumption_pending_need_check"]
    service_level: Literal["optional_supplemental_observation"]
    action_semantics: Literal["simulated_dwell_only"]

    @model_validator(mode="after")
    def reserved_ids(self):
        if self.id in {"BASE", "CURRENT"}:
            raise ValueError("reserved_task_id")
        return self


class BudgetPolicy(Record):
    mode: BudgetMode
    reserve_wh: NonNegative
    available_fraction_error: Annotated[StrictFloat, Field(ge=0, lt=1)]
    cost_fraction_error: NonNegative
    parameter_source: Literal["simulation_policy_not_calibrated_probability"]


class PlanningModel(Record):
    airspeed_ms: Positive
    estimated_power_w: Positive
    curve_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None
    estimator: Literal["constant_power_times_current_observed_travel_time"]
    source: Literal["LOCAL_2D_SIM"]


class Observation(Record):
    as_of_s: NonNegative
    position: Point
    base: Point
    known_map: GridMap
    known_map_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    available_wh_estimate: NonNegative | None
    temperature_c: StrictFloat | None
    completed_task_ids: tuple[Identifier, ...]
    data_status: Literal["AVAILABLE", "UNAVAILABLE"]
    unavailable_reason: str | None

    @model_validator(mode="after")
    def availability_and_geometry(self):
        if not self.known_map.contains(self.position) or not self.known_map.contains(self.base):
            raise ValueError("position_or_base_outside_map")
        if len(set(self.completed_task_ids)) != len(self.completed_task_ids):
            raise ValueError("duplicate_completed_task")
        if self.known_map_sha256 != fingerprint(self.known_map):
            raise ValueError("known_map_fingerprint_mismatch")
        covered = self.temperature_c is not None and -20 <= self.temperature_c <= 23
        if self.data_status == "AVAILABLE":
            if self.available_wh_estimate is None or not covered or self.unavailable_reason is not None:
                raise ValueError("available_observation_requires_covered_data")
        elif not self.unavailable_reason or self.available_wh_estimate is not None:
            raise ValueError("unavailable_observation_requires_reason_and_null_energy")
        return self


class DecisionRequest(Record):
    contract_version: Literal["competition-v2-contract-0.3"]
    observation: Observation
    task_catalog: Annotated[tuple[Task, ...], Field(min_length=5, max_length=8)]
    selector_id: Selector
    budget: BudgetPolicy
    model: PlanningModel

    @model_validator(mode="after")
    def tasks_match_observation(self):
        ids = [t.id for t in self.task_catalog]
        positions = [t.position for t in self.task_catalog]
        if len(set(ids)) != len(ids) or len(set(positions)) != len(positions):
            raise ValueError("duplicate_task_id_or_position")
        if self.observation.base in positions or any(not self.observation.known_map.contains(p) for p in positions):
            raise ValueError("task_at_base_or_outside_map")
        if not set(self.observation.completed_task_ids).issubset(ids):
            raise ValueError("unknown_completed_task")
        if self.observation.data_status == "AVAILABLE" and self.model.curve_sha256 is None:
            raise ValueError("available_request_requires_curve_provenance")
        return self


class LegEstimate(Record):
    from_id: Identifier
    to_id: Identifier
    status: Literal["PLANNED", "UNREACHABLE"]
    path: tuple[Point, ...]
    distance_m: NonNegative | None
    duration_s: NonNegative | None
    energy_wh: NonNegative | None
    reason: str | None

    @model_validator(mode="after")
    def no_faked_cost(self):
        costs = (self.distance_m, self.duration_s, self.energy_wh)
        if self.status == "PLANNED":
            if not self.path or any(x is None for x in costs) or self.reason is not None:
                raise ValueError("planned_leg_requires_path_and_costs")
        elif self.path or any(x is not None for x in costs) or not self.reason:
            raise ValueError("unreachable_leg_has_null_costs_and_reason")
        return self


class BudgetAssessment(Record):
    status: Literal["SUFFICIENT", "INSUFFICIENT", "UNAVAILABLE"]
    ordered_task_ids: tuple[Identifier, ...]
    transit_wh: NonNegative | None
    service_wh: NonNegative | None
    return_wh: NonNegative | None
    reserve_wh: NonNegative
    assessed_available_wh: NonNegative | None
    assessed_demand_wh: NonNegative | None
    margin_wh: StrictFloat | None
    reason: str
    execution_verified: Literal[False] = False

    @model_validator(mode="after")
    def known_or_unknown(self):
        values = (self.transit_wh, self.service_wh, self.return_wh,
                  self.assessed_available_wh, self.assessed_demand_wh, self.margin_wh)
        if len(set(self.ordered_task_ids)) != len(self.ordered_task_ids):
            raise ValueError("duplicate_selected_task")
        if self.status == "UNAVAILABLE":
            if any(x is not None for x in values):
                raise ValueError("unavailable_budget_must_not_show_numeric_demand")
        else:
            if any(x is None for x in values):
                raise ValueError("numeric_budget_required")
            if abs(self.margin_wh - (self.assessed_available_wh - self.assessed_demand_wh)) > 1e-7:
                raise ValueError("budget_margin_mismatch")
            if (self.margin_wh >= -1e-7) != (self.status == "SUFFICIENT"):
                raise ValueError("budget_status_mismatch")
        return self


class DeferredTask(Record):
    id: Identifier
    reason: Literal["BUDGET", "UNREACHABLE", "LOWER_VALUE_PLAN", "DATA_UNAVAILABLE"]
    follow_up_state: Literal["REQUIRES_OPERATOR_REVIEW"]


class DecisionRecord(Record):
    """Output shape; pair with its request before accepting or exporting it."""
    contract_version: Literal["competition-v2-contract-0.3"]
    request_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    as_of_s: NonNegative
    selector_id: Selector
    budget_mode: BudgetMode
    action: Literal["CONTINUE", "RETURN", "REFUSED", "STOP"]
    reason_code: Literal["PLAN_SELECTED", "NO_FEASIBLE_TASK", "ALL_TASKS_VISITED",
                         "RETURN_UNREACHABLE", "RETURN_BUDGET_INSUFFICIENT", "DATA_UNAVAILABLE"]
    ordered_task_ids: tuple[Identifier, ...]
    deferred_tasks: tuple[DeferredTask, ...]
    budget: BudgetAssessment
    computation_ms: NonNegative

    @model_validator(mode="after")
    def consistent_action(self):
        if self.ordered_task_ids != self.budget.ordered_task_ids:
            raise ValueError("decision_and_budget_order_differ")
        allowed_reasons = {"CONTINUE": {"PLAN_SELECTED"},
                           "RETURN": {"NO_FEASIBLE_TASK", "ALL_TASKS_VISITED"},
                           "REFUSED": {"NO_FEASIBLE_TASK"},
                           "STOP": {"RETURN_UNREACHABLE", "RETURN_BUDGET_INSUFFICIENT", "DATA_UNAVAILABLE"}}
        if self.reason_code not in allowed_reasons[self.action]:
            raise ValueError("action_reason_mismatch")
        deferred_ids = [task.id for task in self.deferred_tasks]
        if len(set(deferred_ids)) != len(deferred_ids) or set(deferred_ids) & set(self.ordered_task_ids):
            raise ValueError("duplicate_or_selected_deferred_task")
        if self.action == "CONTINUE":
            if not self.ordered_task_ids or self.budget.status != "SUFFICIENT" or self.reason_code != "PLAN_SELECTED":
                raise ValueError("continue_requires_feasible_selected_plan")
        elif self.ordered_task_ids:
            raise ValueError("non_continue_cannot_claim_future_tasks")
        if self.action == "RETURN" and self.budget.status != "SUFFICIENT":
            raise ValueError("return_action_requires_feasible_return_budget")
        if self.action == "STOP":
            expected = "INSUFFICIENT" if self.reason_code == "RETURN_BUDGET_INSUFFICIENT" else "UNAVAILABLE"
            if self.budget.status != expected:
                raise ValueError("stop_reason_budget_mismatch")
        return self


def validate_decision_for_request(request: DecisionRequest, record: DecisionRecord):
    """Check provenance and task accounting, without claiming execution occurred.

    D3 must call this boundary after constructing a decision. The scalar budget
    checks establish arithmetic consistency, not the correctness of its paths.
    """
    if record.request_sha256 != fingerprint(request):
        raise ValueError("decision_request_fingerprint_mismatch")
    if record.as_of_s != request.observation.as_of_s:
        raise ValueError("decision_observation_time_mismatch")
    if record.selector_id != request.selector_id or record.budget_mode != request.budget.mode:
        raise ValueError("decision_policy_mismatch")

    catalog = {task.id for task in request.task_catalog}
    completed = set(request.observation.completed_task_ids)
    selected = set(record.ordered_task_ids)
    deferred = {task.id for task in record.deferred_tasks}
    if (selected | deferred) - catalog:
        raise ValueError("decision_unknown_task")
    if completed & (selected | deferred):
        raise ValueError("decision_completed_task_reused")
    if (selected & deferred) or (completed | selected | deferred) != catalog:
        raise ValueError("decision_task_accounting_incomplete")
    if record.action == "REFUSED" and request.observation.position != request.observation.base:
        raise ValueError("refused_requires_position_at_base")
    if record.reason_code == "ALL_TASKS_VISITED" and completed != catalog:
        raise ValueError("all_tasks_visited_has_unfinished_tasks")
    if request.observation.data_status != "AVAILABLE" and record.reason_code != "DATA_UNAVAILABLE":
        raise ValueError("decision_requires_available_observation")

    budget = record.budget
    if abs(budget.reserve_wh - request.budget.reserve_wh) > 1e-7:
        raise ValueError("decision_reserve_mismatch")
    if budget.status != "UNAVAILABLE":
        available = request.observation.available_wh_estimate
        demand = budget.transit_wh + budget.service_wh + budget.return_wh
        if request.budget.mode == "bounded":
            available *= 1 - request.budget.available_fraction_error
            demand *= 1 + request.budget.cost_fraction_error
        demand += request.budget.reserve_wh
        if (abs(budget.assessed_available_wh - available) > 1e-7
                or abs(budget.assessed_demand_wh - demand) > 1e-7):
            raise ValueError("decision_budget_arithmetic_mismatch")
    return record


def fingerprint(value):
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
