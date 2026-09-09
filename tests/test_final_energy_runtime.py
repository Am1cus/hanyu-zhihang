"""Frozen package integration and invalid-input tests; no original-file mutation."""
import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/"Phase4/releases/energy_residual_lstm_v3_rc1"


@unittest.skipUnless((RELEASE/"manifest.json").exists(),"Requires frozen release")
class FrozenEnergyRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location("exported_energy_runtime",RELEASE/"runtime.py")
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        cls.Predictor=module.FrozenEnergyPredictor
        cls.predictor=cls.Predictor(RELEASE)
        cls.request=json.loads((RELEASE/"example_request.json").read_text())

    def predict(self,request):
        return self.predictor.predict(request["samples"],sampling_contract=request["sampling_contract"],data_source=request["data_source"])

    def test_exported_runtime_reproduces_persisted_example(self):
        result=self.predict(self.request)
        expected=json.loads((RELEASE/"example_response.json").read_text())
        self.assertTrue(result["valid"])
        self.assertAlmostEqual(result["predicted_consumption_ah"],expected["predicted_consumption_ah"],delta=1e-9)
        self.assertEqual(result["target_available_at_s"],70)

    def test_all_1864_archived_predictions_were_reproduced(self):
        evidence=json.loads((RELEASE/"runtime_verification.json").read_text())
        self.assertEqual(evidence["windows_reproduced"],1864)
        self.assertTrue(evidence["all_valid"])
        self.assertLessEqual(evidence["maximum_absolute_difference_ah"],1e-7)

    def test_future_fields_do_not_influence_prediction(self):
        changed=copy.deepcopy(self.request)
        for s in changed["samples"]:
            s["future_current"]=1000000;s["termination_time"]=1
        self.assertEqual(self.predict(changed)["predicted_consumption_ah"],self.predict(self.request)["predicted_consumption_ah"])

    def test_missing_sensor_and_gap_are_not_imputed(self):
        changed=copy.deepcopy(self.request);del changed["samples"][2]["wind_x"]
        self.assertFalse(self.predict(changed)["valid"])
        changed=copy.deepcopy(self.request);changed["samples"][2]["available_at_s"]+=.5
        response=self.predict(changed)
        self.assertFalse(response["valid"]);self.assertIsNone(response["predicted_consumption_ah"])

    def test_mixed_flights_and_missing_identity_are_rejected(self):
        changed=copy.deepcopy(self.request);changed["samples"][1]["flight_id"]="OTHER"
        self.assertFalse(self.predict(changed)["valid"])
        changed=copy.deepcopy(self.request);del changed["samples"][1]["flight_id"]
        self.assertFalse(self.predict(changed)["valid"])

    def test_raw_point_sampling_and_real_flight_domain_are_not_mislabelled(self):
        changed=copy.deepcopy(self.request);changed["sampling_contract"]="nearest_1hz_points"
        self.assertFalse(self.predict(changed)["valid"])
        changed=copy.deepcopy(self.request);changed["data_source"]="REAL_UAV"
        self.assertFalse(self.predict(changed)["valid"])

    def test_inference_success_does_not_claim_final_acceptance(self):
        response=self.predict(self.request)
        self.assertTrue(response["valid"])
        self.assertFalse(response["validated_on_real_data"])
        self.assertFalse(response["project_acceptance_passed"])
        self.assertIn("pending_independent_confirmation",response["research_status"])

    def test_tampered_model_is_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as temp:
            destination=Path(temp)/"release";shutil.copytree(RELEASE,destination)
            member=json.loads((destination/"manifest.json").read_text())["members"][0]["file"]
            (destination/member).write_bytes(b"corrupted test fixture, not the real model")
            with self.assertRaisesRegex(ValueError,"fingerprint mismatch"):
                self.Predictor(destination)


if __name__=="__main__":unittest.main()
