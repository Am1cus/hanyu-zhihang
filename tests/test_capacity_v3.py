"""Causality/label/serialization regression tests for isolated V3 experiments."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"Phase4"))
from capacity_v3 import (ALL_FEATURES, EnergyLSTM, aggregate_raw, build_windows,
                         causal_baselines, predict_network, tabular_features)


def raw(seconds=75):
    times = np.arange(0, seconds+0.01, 0.1)
    frame = pd.DataFrame({"timestamp": times, "current": 3.6, "voltage": 11,
        "soc_pct": 90, "remaining_capacity_ah": 2-times*0.001,
        "ambient_temp": -20, "battery_temperature": -18, "payload_kg": .5,
        "altitude": 10, "wind_speed": 2, "wind_x": 2, "wind_y": 0, "wind_z": 0,
        "velocity_x": 1, "velocity_y": 0, "velocity_z": 0})
    return frame


class CapacityV3Test(unittest.TestCase):
    def test_right_boundary_and_terminal_partial_bucket(self):
        source = raw()
        result = aggregate_raw(source)
        self.assertEqual(result.available_at_s.iloc[0], 1)
        self.assertEqual(result.available_at_s.iloc[-1], 75)
        self.assertEqual(len(result), 75)

    def test_label_is_future_ten_seconds_not_present_soc(self):
        samples = build_windows({"F": aggregate_raw(raw())}, ["F"])
        np.testing.assert_allclose(samples["y"], .01, atol=1e-10)
        self.assertEqual(samples["time"][0], 30)

    def test_future_change_cannot_change_inputs_or_baselines(self):
        a = raw(); b = a.copy()
        # First forecast becomes available at t=30. All later data is unknown.
        b.loc[b.timestamp >= 30, "current"] = 12
        b.loc[b.timestamp >= 30, "wind_speed"] = 8
        b.loc[b.timestamp >= 30, "remaining_capacity_ah"] -= .002*(b.loc[b.timestamp>=30,"timestamp"]-30)
        sa = build_windows({"F": aggregate_raw(a)}, ["F"])
        sb = build_windows({"F": aggregate_raw(b)}, ["F"])
        np.testing.assert_array_equal(sa["x"][0], sb["x"][0])
        np.testing.assert_array_equal(tabular_features(sa)[0], tabular_features(sb)[0])
        for name, values in causal_baselines(sa).items():
            self.assertEqual(values[0], causal_baselines(sb)[name][0])
        self.assertNotAlmostEqual(sa["y"][0], sb["y"][0])

    def test_missing_second_is_not_interpolated_or_bridged(self):
        source = raw(100)
        source = source[~((source.timestamp>=40)&(source.timestamp<41))]
        samples = build_windows({"F": aggregate_raw(source)}, ["F"])
        self.assertFalse(np.any((samples["time"]>=31)&(samples["time"]<=70)))

    def test_flight_windows_never_cross_boundary(self):
        frames = {"A": aggregate_raw(raw(45)), "B": aggregate_raw(raw(45))}
        samples = build_windows(frames, ["A", "B"])
        self.assertEqual(set(samples["flight"]), {"A", "B"})
        self.assertTrue(np.all(samples["time"]>=30))
        self.assertEqual(len(samples["y"]), 12)

    def test_duplicates_are_rejected(self):
        source = raw(); source.loc[1,"timestamp"] = source.loc[0,"timestamp"]
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            aggregate_raw(source)

    def test_zero_residual_exactly_matches_history_without_linear_correction(self):
        samples = build_windows({"F": aggregate_raw(raw())}, ["F"])
        model = EnergyLSTM(1, 16)
        scaler = StandardScaler().fit(samples["x"][:,:,0].reshape(-1,1))
        prediction = predict_network(model, scaler, {"features":"current_only", "residual":True}, samples, 1)
        np.testing.assert_allclose(prediction, samples["base"], rtol=0, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
