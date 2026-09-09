"""Re-load saved candidates and reproduce archived held-out predictions.

Tests read local experiment artifacts only; no model training or service calls.
"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"Phase4"))
from capacity_v3 import read_dataset, sha256
from predict_capacity_v3 import CapacityV3Predictor
from train_capacity_v3 import check_protocol

EXPERIMENT = ROOT/"Phase4/experiments/capacity_v3_20260908"


@unittest.skipUnless((EXPERIMENT/"evaluation.json").exists(), "Requires completed versioned local experiment")
class CapacityV3ArtifactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = check_protocol(EXPERIMENT)
        cls.frames, _, _ = read_dataset(cls.protocol["source"])
        cls.rows = json.loads((EXPERIMENT/"heldout_predictions.json").read_text())
        cls.predictor = CapacityV3Predictor(EXPERIMENT)

    def window(self, flight="F022", at=60):
        f = self.frames[flight]
        return f[f.available_at_s<=at].tail(30).copy()

    def test_exact_protocol_source_and_model_fingerprints(self):
        self.assertEqual(sha256(self.protocol["source"]), self.protocol["source_sha256"])
        self.assertEqual(self.predictor.name, "direct_full32")

    def test_reloaded_primary_matches_archived_test_values(self):
        for flight in ("F012", "F018", "F022"):
            result = self.predictor.predict_window(self.window(flight))
            row = next(r for r in self.rows if r["flight_id"]==flight and r["prediction_available_at_s"]==60)
            self.assertTrue(result["valid"])
            self.assertAlmostEqual(result["predicted_consumption_ah"], row["direct_full32"], delta=1e-7)
            self.assertEqual(result["target_available_at_s"], 70)

    def test_exploratory_candidate_is_never_mislabelled_as_preselected(self):
        predictor = CapacityV3Predictor(EXPERIMENT, "residual_core32")
        result = predictor.predict_window(self.window())
        row = next(r for r in self.rows if r["flight_id"]=="F022" and r["prediction_available_at_s"]==60)
        self.assertAlmostEqual(result["predicted_consumption_ah"],row["residual_core32"],delta=1e-7)
        self.assertEqual(result["selection_role"], "exploratory_requires_fresh_confirmation")
        self.assertFalse(result["promotion_eligible"])

    def test_invalid_window_returns_null_not_minus_one(self):
        for f in (self.window().iloc[:-1], self.window().assign(current=np.nan)):
            result = self.predictor.predict_window(f)
            self.assertFalse(result["valid"])
            self.assertIsNone(result["predicted_consumption_ah"])

    def test_gap_in_window_is_unavailable(self):
        f = self.window(); f.loc[f.index[-1],"available_at_s"] += 1
        self.assertEqual(self.predictor.predict_window(f)["reason"], "noncontiguous_source_clock")

    def test_unknown_candidate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown frozen candidate"):
            CapacityV3Predictor(EXPERIMENT, "fake")

    def test_no_online_promotion_and_manifest_matches_checkpoint_semantics(self):
        result = self.predictor.predict_window(self.window())
        self.assertFalse(result["deployed"])
        self.assertFalse(result["promotion_eligible"])
        self.assertIn("training_geometric_mean",self.predictor.manifest["prediction_transform"])


if __name__=="__main__":
    unittest.main()
