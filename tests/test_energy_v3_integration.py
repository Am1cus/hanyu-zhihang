import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from Phase4.energy_v3_service import EnergyV3Service, RELEASE
from Phase4.replay_airsim import load_flights, prepare_flight, resolve_columns, build_parser, run_metadata
from Phase4.capacity_v3 import aggregate_raw
from Phase4.dataset_v2_replay import load_manifest_flights
from Phase3 import inference_api as api

SOURCE = Path("/Users/kedong/Downloads/dataset_v2.zip")


class EnergyV3AdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service=EnergyV3Service()
        cls.request=json.loads((RELEASE / "example_request.json").read_text())

    def test_served_prediction_is_exact_frozen_runtime_with_unit_aliases(self):
        response=self.service.predict(self.request)
        frozen=self.service.predictor.predict(**self.request)
        self.assertEqual(response["predicted_consumption_Ah"],frozen["predicted_consumption_ah"])
        self.assertEqual(response["predicted_capacity_Ah"],frozen["predicted_future_capacity_ah"])
        self.assertFalse(response["project_acceptance_passed"])
        self.assertEqual(response["execution_mode"],"research_shadow")
        self.assertEqual(len(response["model_sha256"]),64)
        currents=np.asarray([s["current"] for s in self.request["samples"]],dtype=np.float32)
        self.assertAlmostEqual(response["baselines"]["mean_current_20s"],float(currents[-20:].mean()*10/3600),places=7)

    def test_offline_candidate_returns_null_without_affecting_legacy_endpoints(self):
        with patch.object(api,"ENERGY_V3",None):
            result=api.predict_energy_v3(api.EnergyV3Request(drone_id=2,**self.request))
        self.assertFalse(result["valid"])
        self.assertIsNone(result["predicted_consumption_Ah"])

    def test_unknown_domain_gap_missing_vector_and_cross_run_fail(self):
        cases=[]
        wrong=copy.deepcopy(self.request);wrong["data_source"]="REAL_FLIGHT";cases.append(wrong)
        wrong=copy.deepcopy(self.request);wrong["samples"][-1]["available_at_s"]+=1;cases.append(wrong)
        wrong=copy.deepcopy(self.request);del wrong["samples"][-1]["wind_x"];cases.append(wrong)
        wrong=copy.deepcopy(self.request);wrong["samples"][-1]["flight_id"]="another";cases.append(wrong)
        for request in cases:
            result=self.service.predict(request)
            self.assertFalse(result["valid"])
            self.assertIsNone(result["predicted_consumption_Ah"])
            self.assertNotIn("baselines",result)

    def test_report_separates_reproduction_from_accuracy(self):
        report=self.service.report()
        self.assertFalse(report["independent_confirmation_passed"])
        self.assertTrue(report["offline_recheck"]["verification_is_reproduction_not_independent_accuracy_validation"])

    def test_manifest_without_end_reason_is_quarantined(self):
        files={"dataset_manifest_batch.json":json.dumps({"flights":[{"flight_id":"new001"}]}).encode(),
               "flight_new001/manifest.json":json.dumps({"flight_id":"new001","sample_rate_hz":10}).encode(),
               "flight_new001/flights/new001_raw_10Hz.csv":b"flight_id,timestamp\nnew001,0\n"}
        class Archive:
            def namelist(self): return list(files)
            def read(self,name): return files[name]
        frame=load_manifest_flights(Archive(),"unknown_new_batch")[0][1]
        self.assertEqual(frame.attrs["v3_provenance"]["quarantine_reason"],"missing_end_reason")
        self.assertEqual(frame.attrs["v3_provenance"]["evaluation_role"],"unconfirmed_new_data")


@unittest.skipUnless(SOURCE.exists(),"External read-only dataset not present")
class DatasetV2ReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flights=dict(load_flights(SOURCE))

    def test_raw_manifest_imports_26_not_52_flights_and_quarantines_six(self):
        self.assertEqual(len(self.flights),26)
        excluded=[f for f,frame in self.flights.items() if frame.attrs["v3_provenance"]["quarantine_reason"]]
        self.assertEqual(len(excluded),6)
        for flight in excluded:
            frame=self.flights[flight]
            with self.assertRaisesRegex(ValueError,"隔离"):
                prepare_flight(frame,resolve_columns(frame))

    def test_online_bins_exactly_match_frozen_training_bins(self):
        frame=self.flights["F022"]
        prepared=prepare_flight(frame,resolve_columns(frame))
        frozen=aggregate_raw(frame).dropna()
        self.assertEqual(prepared.index.total_seconds().tolist(),frozen.available_at_s.tolist())
        for column in ["current","velocity_x","velocity_y","velocity_z","wind_x","wind_y","wind_z"]:
            np.testing.assert_array_equal(prepared[column],frozen[column])
        self.assertEqual(prepared.index[0].total_seconds(),1)
        self.assertEqual(prepared.index[-1].total_seconds(),195)

    def test_metadata_discloses_sampling_domain_split_and_raw_fingerprint(self):
        frame=self.flights["F022"];columns=resolve_columns(frame)
        args=build_parser().parse_args([str(SOURCE),"--flight-id","F022"])
        meta=run_metadata(args,"F022",frame,prepare_flight(frame,columns),columns)
        self.assertEqual(meta["configuration"]["evaluation_role"],"exploratory_test")
        self.assertEqual(meta["configuration"]["source_hash_definition"],"sha256(raw_10hz_csv_bytes)")
        self.assertFalse(meta["configuration"]["independent_confirmation"])

    def test_missing_second_keeps_gap_and_future_changes_do_not_change_early_bins(self):
        frame=self.flights["F022"].copy()
        original=prepare_flight(frame,resolve_columns(frame))
        frame.loc[frame.timestamp>=60,"current"]*=2
        changed=prepare_flight(frame,resolve_columns(frame))
        np.testing.assert_array_equal(original.iloc[:59].current,changed.iloc[:59].current)
        frame=frame[(frame.timestamp<40)|(frame.timestamp>=41)].copy()
        changed=prepare_flight(frame,resolve_columns(frame))
        self.assertNotIn(41,changed.index.total_seconds())
        self.assertIn(42,changed.index.total_seconds())


if __name__=="__main__": unittest.main()
