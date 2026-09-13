"""Measured/simulated discharge integration, not a low-temperature capacity model."""
import math


def integrate_discharge(samples, max_gap_s):
    """Trapezoidal integration of V*I and I; refuse gaps and charging segments."""
    if not math.isfinite(max_gap_s) or max_gap_s <= 0:
        raise ValueError("positive max_gap_s required")
    if len(samples) < 2:
        return {"status": "unavailable", "reason": "need_two_samples"}
    wh = ah = 0.0
    runs = {s.get("run_id") for s in samples}
    if len(runs) != 1 or not all(isinstance(r, str) and r for r in runs):
        raise ValueError("exactly one run_id required")
    for sample in samples:
        for key in ("t_s", "voltage_v", "current_a"):
            v = sample.get(key)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                return {"status": "unavailable", "reason": f"missing_or_invalid_{key}"}
        if sample["voltage_v"] <= 0 or sample["current_a"] < 0:
            return {"status": "unavailable", "reason": "invalid_voltage_or_charging"}
    for a, b in zip(samples, samples[1:]):
        dt = b["t_s"] - a["t_s"]
        if not 0 < dt <= max_gap_s:
            return {"status": "unavailable", "reason": "time_gap_or_out_of_order"}
        wh += (a["voltage_v"]*a["current_a"] + b["voltage_v"]*b["current_a"]) * 0.5 * dt / 3600
        ah += (a["current_a"] + b["current_a"]) * 0.5 * dt / 3600
    return {"status": "integrated", "discharged_wh": wh, "discharged_ah": ah,
            "duration_s": samples[-1]["t_s"]-samples[0]["t_s"],
            "remaining_usable_wh": None, "scope": "observed_interval_only"}
