"""Read digitized constant-current cell curves without inventing temperature data."""
from __future__ import annotations

from dataclasses import dataclass
import bisect
import hashlib
import json
import math
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "p42a_reference.json"


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


@dataclass(frozen=True)
class CellCurve:
    temperature_c: float
    points: tuple[tuple[float, float], ...]

    @property
    def capacity_ah(self):
        return self.points[-1][0]

    def voltage(self, q):
        q = min(self.capacity_ah, max(0.0, q))
        capacities = [p[0] for p in self.points]
        right = bisect.bisect_right(capacities, q)
        if right >= len(self.points):
            return self.points[-1][1]
        a, b = self.points[max(0, right - 1)], self.points[right]
        return a[1] + (b[1] - a[1]) * (q - a[0]) / (b[0] - a[0])

    def energy_between(self, qa, qb, series_cells=4):
        if not 0 <= qa <= qb <= self.capacity_ah + 1e-10:
            raise ValueError("charge interval outside digitized curve")
        qb = min(qb, self.capacity_ah)
        knots = [qa] + [q for q, _ in self.points if qa < q < qb] + [qb]
        return series_cells * sum((self.voltage(a) + self.voltage(b)) * .5 * (b - a)
                                  for a, b in zip(knots, knots[1:]))

    def seconds_to_next_knot(self, q, current_a):
        for knot, _ in self.points:
            if knot > q + 1e-12:
                return (knot - q) * 3600 / current_a
        return 0.0


class CurveLibrary:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)
        self.available = False
        self.reason = "reference_curve_missing"
        self.curves = {}
        self.source = {}
        self.sha256 = None
        self.current_a = 4.2
        self.series_cells = 4
        self.reference_temperature_c = 23.0
        try:
            raw = self.path.read_bytes()
            self.load(json.loads(raw))
            self.sha256 = hashlib.sha256(raw).hexdigest()
            self.available, self.reason = True, None
        except FileNotFoundError:
            pass
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.reason = f"reference_curve_invalid: {exc}"

    def load(self, data):
        if data.get("schema_version", 1) != 1:
            raise ValueError("unsupported curve schema")
        self.source = data.get("source", {})
        if not isinstance(self.source, dict) or not self.source:
            raise ValueError("curve provenance is required")
        self.current_a = finite(data.get("discharge_current_a", 4.2), "discharge_current_a")
        self.series_cells = data.get("series_cells", 4)
        self.reference_temperature_c = finite(data.get("reference_temperature_c", 23), "reference temperature")
        if abs(self.current_a - 4.2) > 1e-9 or self.series_cells != 4:
            raise ValueError("this simulator requires the declared 4.2 A, ideal 4S1P model")
        parsed = {}
        for item in data["curves"]:
            temperature = finite(item["temperature_c"], "temperature_c")
            points = tuple((finite(p["capacity_ah"], "capacity_ah"), finite(p["voltage_v"], "voltage_v"))
                           for p in item["points"])
            if len(points) < 2 or points[0][0] != 0 or any(q < 0 or not 1.5 <= v <= 4.3 for q, v in points):
                raise ValueError("curve needs a zero-charge origin and valid positive cell voltages")
            if any(b[0] <= a[0] for a, b in zip(points, points[1:])) or temperature in parsed:
                raise ValueError("curve capacities must increase and temperatures must be unique")
            parsed[temperature] = CellCurve(temperature, points)
        if self.reference_temperature_c not in parsed:
            raise ValueError("23 C reference curve required for the reserve denominator")
        self.curves = parsed

    def curve(self, temperature_c):
        if not self.available:
            raise ValueError(self.reason)
        temperature = finite(temperature_c, "temperature_c")
        if temperature in self.curves:
            return self.curves[temperature]
        temperatures = sorted(self.curves)
        if not temperatures[0] <= temperature <= temperatures[-1]:
            raise ValueError("temperature_outside_source_nodes_no_extrapolation")
        upper = bisect.bisect_right(temperatures, temperature)
        low, high = self.curves[temperatures[upper - 1]], self.curves[temperatures[upper]]
        weight = (temperature - low.temperature_c) / (high.temperature_c - low.temperature_c)
        capacity = low.capacity_ah * (1 - weight) + high.capacity_ah * weight
        normalized = sorted({0.0, 1.0, *(q / low.capacity_ah for q, _ in low.points),
                             *(q / high.capacity_ah for q, _ in high.points)})
        points = tuple((z * capacity, low.voltage(z * low.capacity_ah) * (1 - weight)
                        + high.voltage(z * high.capacity_ah) * weight) for z in normalized)
        return CellCurve(temperature, points)

    @property
    def reference_wh(self):
        curve = self.curve(self.reference_temperature_c)
        return curve.energy_between(0, curve.capacity_ah, self.series_cells)

    def status(self):
        return {"available": self.available, "reason": self.reason,
                "temperatures_c": sorted({*self.curves, -10.0}) if self.available else [],
                "source_temperature_nodes_c": sorted(self.curves),
                "temperature_scope_c": [min(self.curves), max(self.curves)] if self.curves else None,
                "temperature_interpolation": "linear_voltage_on_union_normalized_capacity_nodes_then_integrate",
                "source": self.source, "sha256": self.sha256,
                "model": "digitized_constant_4.2A_cell_curves_ideal_4S1P_not_a_real_drone_battery",
                "reference_temperature_c": self.reference_temperature_c,
                "no_temperature_extrapolation": True, "validated_on_real_drone": False}
