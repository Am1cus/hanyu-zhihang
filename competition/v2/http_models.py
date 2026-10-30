"""HTTP response contracts; independent of the frozen simulation model."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from .contracts import (BudgetMode, DecisionRecord, DecisionRequest, GridMap,
                        LegEstimate, Point, Selector, Task, Vector)
from .runtime import RuntimeConfig
from .scenarios import Event
from .version import API_VERSION

Status = Literal['RUNNING', 'PAUSED', 'COMPLETED_RETURNED', 'PARTIAL_RETURNED',
                 'REFUSED', 'FAILED', 'UNAVAILABLE', 'CANCELLED']


class Response(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Health(Response):
    status: Literal['ok']
    runtime_version: str
    api_version: Literal['competition-v2-api-0.2']
    source: Literal['LOCAL_2D_SIM']
    library_available: bool


class Summary(Response):
    status: Status
    ended_reason: str | None
    returned: bool
    completed_ids: list[str]
    completed_count: int
    task_count: int
    raw_value: int
    effective_value: int
    initial_wh: float | None
    consumed_wh: float
    remaining_wh: float | None
    reserve_wh: float | None
    reserve_margin_wh: float | None
    consumed_ah: float
    t_s: float
    distance_m: float
    source: Literal['LOCAL_2D_SIM']
    real_flight: Literal[False]


class Counterfactual(Response):
    scope: str
    request_sha256: str
    record: DecisionRecord
    planned_paths: list[list[Point]]


class Decision(Response):
    t_s: float
    trigger: str
    request: DecisionRequest
    record: DecisionRecord
    planned_legs: list[LegEstimate]
    plan_changed: bool
    budget_changed: bool
    responding_to: list[str]
    same_state_counterfactual: Counterfactual | None = None


class AppliedEvent(Response):
    event_id: str
    t_s: float
    source: Literal['scheduled', 'manual']
    payload: Event
    applied: bool
    intersects_occupied_edge: bool


class EventResponseMetric(Response):
    event_id: str
    event_t_s: float
    decision_t_s: float
    simulated_delay_s: float
    decision_compute_ms: float
    plan_changed: bool
    budget_changed: bool
    decision_index: int
    same_state_counterfactual: Counterfactual | None = None


class State(Response):
    id: str
    status: Status
    stage: str
    t_s: float
    speedup: float
    position: Vector
    grid: GridMap
    base: Point
    tasks: list[Task]
    completed_ids: list[str]
    path: list[Point]
    executed_path: list[Vector]
    current_decision: Decision | None
    decisions: list[Decision]
    events: list[AppliedEvent]
    response_metrics: list[EventResponseMetric]
    pending_replan: bool
    summary: Summary
    source: Literal['LOCAL_2D_SIM']
    runtime_version: str
    scenario_label: str
    temperature_c: float
    initial_soc: float
    error_profile: str
    selector_id: Selector
    budget_mode: BudgetMode
    queued_manual_events: int


class AuditOrigin(Response):
    status: Literal['original', 'replay', 'unknown']
    source_run_id: str | None


class AuditAction(Response):
    action: str
    source: str
    t_s: float
    seq: int
    recorded_at: str
    source_run_id: str | None = None
    event: 'QueuedEvent | None' = None


class Audit(Response):
    schema_version: Literal[1]
    status: Literal['recorded', 'unknown']
    origin: AuditOrigin
    records: list[AuditAction]


class LiveState(State):
    runtime_available: bool
    execution_audit: Audit


class Preview(State):
    is_preview: Literal[True]
    runtime_available: Literal[False]


class RunListItem(Response):
    id: str
    summary: Summary
    configuration: RuntimeConfig
    runtime_available: bool


class QueuedEvent(Response):
    event_id: str
    scheduled_at_s: float
    status: Literal['QUEUED']


class Telemetry(Response):
    t_s: float
    dt_s: float
    position: Vector
    position_before: Vector
    voltage_start_v: float
    voltage_v: float
    average_voltage_v: float
    current_a: float
    consumed_wh: float
    remaining_wh: float
    consumed_ah: float
    groundspeed_ms: float
    stage: str
    known_map_sha256: str


class EnergyInterval(Response):
    kind: str
    start_s: float
    start_position: Vector
    estimated_wh: float
    lower_wh: float
    upper_wh: float
    interval_scope: str
    end_s: float
    end_position: Vector
    integrated_wh: float
    partial: bool
    covered: bool | None


class Metadata(Response):
    runtime_version: str
    selector_version: str
    source: Literal['LOCAL_2D_SIM']
    curve_sha256: str | None
    curve_source: dict[str, JsonValue]
    source_sha256: dict[str, str]
    reference_conditions: dict[str, JsonValue]
    seed_usage: str


class Archive(Response):
    metadata: Metadata
    configuration: RuntimeConfig
    configuration_sha256: str
    state: State
    summary: Summary
    telemetry: list[Telemetry]
    events: list[AppliedEvent]
    decisions: list[Decision]
    intervals: list[EnergyInterval]
    response_metrics: list[EventResponseMetric]
    result_sha256: str
    execution_audit: Audit


class Error(Response):
    detail: str


AuditAction.model_rebuild()
Audit.model_rebuild()
LiveState.model_rebuild()
