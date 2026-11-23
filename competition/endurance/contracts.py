"""Inputs for the direct endurance calculator (percent, Celsius and m/s)."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PredictionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    temperature_c: float = Field(default=-20, ge=-40, le=40)
    battery_percent: float = Field(default=80, ge=0, le=100)
    wind_speed_ms: float = Field(default=5, ge=0, le=20)
    ground_speed_ms: float = Field(default=2, ge=0, le=10)
    reserve_percent: float = Field(default=20, ge=0, le=80)
    nominal_capacity_ah: float | None = Field(default=None, gt=0, le=100)


Coordinate = tuple[Annotated[int, Field(strict=True, ge=0)], Annotated[int, Field(strict=True, ge=0)]]


class WindRegion(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    vector: tuple[float, float]

    @model_validator(mode="after")
    def bounds(self):
        if self.x_min > self.x_max or self.y_min > self.y_max:
            raise ValueError("风区的下界不能大于上界")
        if self.vector[0] ** 2 + self.vector[1] ** 2 > 20 ** 2:
            raise ValueError("风速不能超过 20 m/s")
        return self


class RouteGrid(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    width: int = Field(ge=2, le=128, strict=True)
    height: int = Field(ge=2, le=128, strict=True)
    cell_size_m: float = Field(default=10, gt=0, le=1000)
    blocked: list[Coordinate] = Field(default_factory=list, max_length=16384)
    wind_regions: list[WindRegion] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def cells_inside(self):
        if any(x >= self.width or y >= self.height for x, y in self.blocked):
            raise ValueError("障碍格超出了地图范围")
        return self


class RoutingConditions(PredictionInput):
    ground_speed_ms: float = Field(default=2, ge=.25, le=10)
    max_airspeed_ms: float = Field(default=15, ge=.25, le=30)
    wind_direction_deg: float = Field(default=0, ge=0, lt=360)


class RouteInput(RoutingConditions):
    grid: RouteGrid | None = None
    start: Coordinate | None = None
    goal: Coordinate | None = None

    @model_validator(mode="after")
    def endpoints(self):
        if self.grid is not None:
            if self.start is None or self.goal is None:
                raise ValueError("自定义地图需要 start 和 goal")
            for point in (self.start, self.goal):
                if point[0] >= self.grid.width or point[1] >= self.grid.height:
                    raise ValueError("起点或终点超出了地图范围")
        elif self.start is not None or self.goal is not None:
            raise ValueError("自定义起终点时请同时提供地图")
        return self


class ReplanInput(RoutingConditions):
    grid: RouteGrid
    current: Coordinate
    base: Coordinate
    goal: Coordinate | None = None
    alternates: list[Coordinate] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def endpoints(self):
        points = [self.current, self.base, *self.alternates]
        if self.goal is not None:
            points.append(self.goal)
        if any(x >= self.grid.width or y >= self.grid.height for x, y in points):
            raise ValueError("航点超出了地图范围")
        return self
