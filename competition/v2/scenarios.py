"""Executor-side scenario inputs. Only explicit current snapshots reach planning."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from competition.core.curves import CurveLibrary
from competition.core.planning import UPPER_POWER_W
from .contracts import (CONTRACT_VERSION, DecisionRequest, GridMap, Identifier,
                        NonNegative, Point, Positive, Record, Task, Vector, fingerprint)


class ObstacleEvent(Record):
    id: Identifier
    at_s: NonNegative
    type: Literal["obstacle"]
    cells: Annotated[tuple[Point, ...], Field(min_length=1)]


class WindEvent(Record):
    id: Identifier
    at_s: NonNegative
    type: Literal["wind"]
    region_id: Identifier
    vector: Vector


Event = Annotated[ObstacleEvent | WindEvent, Field(discriminator="type")]


class Scenario(Record):
    id: Identifier
    version: Literal["v2-development-maps-0.3", "v2-heldout-maps-0.1"]
    split: Literal["development", "held_out"]
    label: str
    provenance: Literal["synthetic_software_map_not_a_real_park"]
    need_validation: Literal["PENDING"]
    grid: GridMap
    base: Point
    tasks: Annotated[tuple[Task, ...], Field(min_length=5, max_length=8)]
    airspeed_ms: Positive
    fixed_height_m: Positive
    scheduled_events: tuple[Event, ...]

    @model_validator(mode="after")
    def initial_geometry(self):
        expected = "v2-development-maps-0.3" if self.split == "development" else "v2-heldout-maps-0.1"
        if self.version != expected:
            raise ValueError("scenario_split_version_mismatch")
        positions = [self.base, *(t.position for t in self.tasks)]
        if len(set(positions)) != len(positions):
            raise ValueError("duplicate_initial_task_or_base_position")
        if len({t.id for t in self.tasks}) != len(self.tasks):
            raise ValueError("duplicate_task_id")
        if any(not self.grid.contains(p) or p in self.grid.blocked for p in positions):
            raise ValueError("initial_task_or_base_blocked_or_outside")
        if len({e.id for e in self.scheduled_events}) != len(self.scheduled_events):
            raise ValueError("duplicate_event_id")
        if list(self.scheduled_events) != sorted(self.scheduled_events, key=lambda e: (e.at_s, e.id)):
            raise ValueError("events_must_be_sorted_by_time_and_id")
        for event in self.scheduled_events:
            if event.type == "obstacle":
                if len(set(event.cells)) != len(event.cells) or any(not self.grid.contains(p) for p in event.cells):
                    raise ValueError("invalid_event_cells")
            elif event.region_id not in {r.id for r in self.grid.wind_regions}:
                raise ValueError("unknown_wind_region")
        return self


def development_scenarios():
    path = Path(__file__).parent / "data" / "development_scenarios.json"
    return tuple(Scenario.model_validate(row) for row in json.loads(path.read_text(encoding="utf-8")))


def observed_grid(scenario, as_of_s):
    """Executor projection: only events already observed affect the returned map.

    This does not advance aircraft position, energy or time. The runtime executor
    must supply those when integrated in D4.
    """
    if isinstance(as_of_s, bool) or not isinstance(as_of_s, (int, float)) or not 0 <= as_of_s < float("inf"):
        raise ValueError("invalid_observation_time")
    grid = copy.deepcopy(scenario.grid.model_dump(mode="json"))
    blocked = {tuple(p) for p in grid["blocked"]}
    for event in scenario.scheduled_events:
        if event.at_s > as_of_s:
            continue
        if event.type == "obstacle":
            blocked.update(event.cells)
        else:
            for region in grid["wind_regions"]:
                if region["id"] == event.region_id:
                    region["vector"] = list(event.vector)
    grid["blocked"] = sorted(blocked)
    return GridMap.model_validate(grid)


def initial_request(scenario, temperature_c=-10.0, initial_soc=0.55,
                    selector="subset_dp", budget_mode="bounded", error_profile="no_added_bias", library=None):
    """Initial fixture adapter; it is intentionally not a running-state factory."""
    from .contracts import BudgetPolicy, Observation, PlanningModel

    if isinstance(initial_soc, bool) or not isinstance(initial_soc, (int, float)) or not 0 <= initial_soc <= 1:
        raise ValueError("initial_soc_out_of_range")
    profiles = {"no_added_bias": (1.0, 1.0), "joint_within_declared": (0.9, 1.1),
                "joint_outside_declared": (0.8, 1.3)}
    if error_profile not in profiles:
        raise ValueError("unknown_error_profile")
    available_divisor, power_divisor = profiles[error_profile]
    library = library if library is not None else CurveLibrary()
    reserve = library.reference_wh * 0.2 if library.available else None
    if reserve is None:
        raise ValueError("reference_curve_missing_no_reserve_denominator")
    available, reason = None, None
    try:
        curve = library.curve(temperature_c)
        discharged_ah = (1 - initial_soc) * curve.capacity_ah
        available = curve.energy_between(discharged_ah, curve.capacity_ah) / available_divisor
    except ValueError as exc:
        reason = str(exc)
    known = observed_grid(scenario, 0.0)
    return DecisionRequest(
        contract_version=CONTRACT_VERSION,
        observation=Observation(as_of_s=0.0, position=scenario.base, base=scenario.base,
                                known_map=known, known_map_sha256=fingerprint(known),
                                available_wh_estimate=available, temperature_c=temperature_c,
                                completed_task_ids=(), data_status="UNAVAILABLE" if reason else "AVAILABLE",
                                unavailable_reason=reason),
        task_catalog=scenario.tasks, selector_id=selector,
        budget=BudgetPolicy(mode=budget_mode, reserve_wh=reserve, available_fraction_error=0.1,
                            cost_fraction_error=0.1, parameter_source="simulation_policy_not_calibrated_probability"),
        model=PlanningModel(airspeed_ms=scenario.airspeed_ms, estimated_power_w=UPPER_POWER_W / power_divisor,
                            curve_sha256=library.sha256, estimator="constant_power_times_current_observed_travel_time",
                            source="LOCAL_2D_SIM"))
