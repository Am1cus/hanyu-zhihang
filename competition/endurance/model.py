"""A fitted capacity/load model with an explicit charge-to-time calculation.

The training data are short AirSim flights, not observed exhaustion times.
Time is an extrapolation under constant conditions, not a learned end label.
"""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import PredictionInput

MODEL_PATH = Path(__file__).parent / "artifacts" / "endurance-v1.json"


class EnduranceModel:
    def __init__(self, model_path=MODEL_PATH):
        self.artifact = json.loads(Path(model_path).read_text(encoding="utf-8"))
        self.version = self.artifact["model_version"]
        self.capacity = self.artifact["capacity_model"]
        self.load = self.artifact["current_model"]
        self.nominal_voltage_v = self.artifact["profile"]["nominal_voltage_v"]

    def full_capacity_ah(self, temperature_c, nominal_capacity_ah=None):
        """Temperature-adjusted Ah; user battery changes scale the reference pack."""
        c = self.capacity
        nominal = c["capacity_at_reference_ah"]
        capacity = nominal + c["slope_ah_per_c"] * (
            min(temperature_c, c["reference_temperature_c"]) - c["reference_temperature_c"])
        return max(0., capacity) * (nominal_capacity_ah / nominal if nominal_capacity_ah is not None else 1.)

    def current_a(self, wind_speed_ms, ground_speed_ms):
        c = self.load["coefficients"]
        return c["intercept_a"] + c["wind_a_per_ms"] * wind_speed_ms + c["speed_a_per_ms2"] * ground_speed_ms ** 2

    def predict(self, *, temperature_c=-20, battery_percent=80, wind_speed_ms=5,
                ground_speed_ms=2, reserve_percent=20, nominal_capacity_ah=None):
        request = PredictionInput(temperature_c=temperature_c, battery_percent=battery_percent,
                                  wind_speed_ms=wind_speed_ms, ground_speed_ms=ground_speed_ms,
                                  reserve_percent=reserve_percent, nominal_capacity_ah=nominal_capacity_ah)
        return self.predict_input(request)

    def predict_input(self, request: PredictionInput):
        full = self.full_capacity_ah(request.temperature_c, request.nominal_capacity_ah)
        remaining = full * request.battery_percent / 100
        usable = full * max(0., request.battery_percent - request.reserve_percent) / 100
        current = self.current_a(request.wind_speed_ms, request.ground_speed_ms)
        inputs = request.model_dump()
        if inputs["nominal_capacity_ah"] is None:
            inputs["nominal_capacity_ah"] = self.capacity["capacity_at_reference_ah"]
        ranges = self.artifact["observed_ranges"]
        extrapolated = [key for key, bounds in ranges.items()
                        if key in inputs and not bounds[0] <= inputs[key] <= bounds[1]]
        return {
            "model_version": self.version,
            "profile_name": self.artifact["profile"]["name"],
            "remaining_minutes": remaining / current * 60,
            "usable_minutes": usable / current * 60,
            "estimated_current_a": current,
            "estimated_power_w": current * self.nominal_voltage_v,
            "full_capacity_ah": full,
            "available_capacity_ah": remaining,
            "usable_capacity_ah": usable,
            "nominal_voltage_v": self.nominal_voltage_v,
            "inputs": inputs,
            "extrapolated_fields": extrapolated,
            "assumptions": ["按输入条件和指定平飞速度持续飞行，未计入起降与载荷变化。",
                            "电量按当前温度下可用容量的百分比解释；温度按电池与环境平衡处理。",
                            "分钟数由仿真数据拟合的耗电率推算；Wh 使用 11.1 V 标称电压换算。"],
            "evidence_type": "airsim_fitted_load_and_capacity_extrapolation",
        }

    def metadata(self):
        return {key: self.artifact[key] for key in (
            "model_version", "profile", "capacity_model", "current_model",
            "observed_ranges", "training", "interpretation")}
