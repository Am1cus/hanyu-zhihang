"""Software regression tests: no real model training and no dataset mutation."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from Phase4.replay_airsim import prepare_flight, resolve_columns
from Phase3 import inference_api as api


def raw(times):
    return pd.DataFrame({"timestamp": times, "voltage": [11]*len(times), "current": [4]*len(times),
        "ambient_temp": [-20]*len(times), "wind_speed": [1]*len(times),
        "velocity_x": [1]*len(times), "velocity_y": [0]*len(times), "velocity_z": [0]*len(times),
        "altitude": [10]*len(times), "soc_pct": [90]*len(times), "remaining_capacity_ah": [1]*len(times)})


def request(times):
    return api.FlightTimeRequest(drone_id=2, samples=[api.FlightTelemetrySample(
        timestamp_s=t, env_temperature_C=-20, wind_speed_ms=1, voltage_V=11, current_A=4,
        battery_level_pct=90, speed_ms=1, altitude_m=10, remaining_capacity_Ah=1) for t in times])


class ReplayQualityTest(unittest.TestCase):
    def test_does_not_interpolate_missing_seconds(self):
        frame = raw([0, 2])
        prepared = prepare_flight(frame, resolve_columns(frame))
        self.assertEqual([x.total_seconds() for x in prepared.index], [0, 2])

    def test_conflicting_duplicate_raw_time_is_rejected(self):
        frame = raw([0, 0, 1])
        frame.loc[1, "voltage"] = 12
        with self.assertRaisesRegex(ValueError, "冲突"):
            prepare_flight(frame, resolve_columns(frame))

    def test_identical_raw_duplicates_are_deduplicated(self):
        frame = raw([0, 0, 1])
        self.assertEqual(len(prepare_flight(frame, resolve_columns(frame))), 2)

    def test_non_finite_required_values_are_rejected(self):
        frame = raw([0, 1]).astype({"current": float})
        frame.loc[1, "current"] = np.inf
        with self.assertRaises(ValueError):
            prepare_flight(frame, resolve_columns(frame))

    def test_api_rejects_gap_before_scaler_or_model_call(self):
        times = list(range(29)) + [30]
        with patch.object(api, "AIRSIM_CAPACITY_MODEL", object()), patch.object(api, "AIRSIM_CAPACITY_SCALER", object()):
            result = api.predict_airsim_capacity(request(times))
        self.assertFalse(result.valid)
        self.assertIn("non_contiguous", result.reason)

    def test_api_rejects_duplicate_timestamp(self):
        times = list(range(29)) + [28]
        with patch.object(api, "AIRSIM_CAPACITY_MODEL", object()), patch.object(api, "AIRSIM_CAPACITY_SCALER", object()):
            self.assertFalse(api.predict_airsim_capacity(request(times)).valid)


if __name__ == "__main__":
    unittest.main()
