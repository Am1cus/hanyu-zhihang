"""The endurance endpoints share the current local v2 HTTP service."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from .contracts import PredictionInput, ReplanInput, RouteInput
from .model import EnduranceModel
from .routes import plan_round_trip, replan_from_current


class PredictionResult(BaseModel):
    model_version: str
    profile_name: str
    remaining_minutes: float
    usable_minutes: float
    estimated_current_a: float
    estimated_power_w: float
    full_capacity_ah: float
    available_capacity_ah: float
    usable_capacity_ah: float
    nominal_voltage_v: float
    inputs: PredictionInput
    extrapolated_fields: list[str]
    assumptions: list[str]
    evidence_type: str


class OutboundWaypoint(BaseModel):
    position: tuple[int, int]
    distance_m: float
    duration_s: float


class ReturnableWaypoint(OutboundWaypoint):
    remaining_battery_percent: float


class ReturnLimit(BaseModel):
    """Reserve limit along the energy-minimizing outbound route."""
    status: Literal["goal_with_reserve", "turn_back", "start_below_reserve", "outbound_unreachable"]
    last_feasible: ReturnableWaypoint | None = None
    first_limited: OutboundWaypoint | None = None
    reason: Literal["reserve_shortfall", "return_unreachable"] | None = None


class RouteResult(BaseModel):
    model_version: str
    planner_version: str
    prediction: PredictionResult
    grid: dict[str, Any]
    start: list[int]
    goal: list[int]
    energy_route: dict[str, Any]
    distance_route: dict[str, Any]
    return_limit: ReturnLimit
    saving_percent: float | None
    build_time_ms: float
    edge_model_calls: int
    route_assumptions: dict[str, Any]


class ModelMetadata(BaseModel):
    model_version: str
    profile: dict[str, Any]
    capacity_model: dict[str, Any]
    current_model: dict[str, Any]
    observed_ranges: dict[str, list[float]]
    training: dict[str, Any]
    interpretation: dict[str, Any]


class ReplanResult(BaseModel):
    model_version: str
    planner_version: str
    action: Literal["continue_to_goal", "return_to_base", "divert", "no_feasible_landing"]
    reason: Literal["return_requested", "goal_unreachable", "goal_return_unreachable",
                    "goal_reserve_shortfall", "goal_with_reserve"]
    legs: list[dict[str, Any]]
    available_capacity_ah: float
    reserve_capacity_ah: float
    estimated_consumption_ah: float | None = None
    remaining_battery_percent: float | None = None
    feasible_with_reserve: bool


def create_router(model=None):
    model = model or EnduranceModel()
    router = APIRouter(tags=["续航预测"])

    @router.get("/api/v2/endurance/model", response_model=ModelMetadata)
    def metadata():
        return model.metadata()

    @router.post("/api/v2/endurance/predict", response_model=PredictionResult)
    def predict(request: PredictionInput):
        return model.predict_input(request)

    @router.post("/api/v2/endurance/route", response_model=RouteResult)
    def route(request: RouteInput):
        return plan_round_trip(request, model)

    @router.post("/api/v2/endurance/replan", response_model=ReplanResult)
    def replan(request: ReplanInput):
        return replan_from_current(request, model)

    return router
