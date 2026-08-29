import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from Phase3 import inference_api
from Phase4.audit_airsim import audit
from Phase4.replay_airsim import (
    advance_gps_from_ned,
    load_flights,
    prepare_flight,
    resolve_columns,
    select_flight,
)


class Phase4IntegrationTest(unittest.TestCase):
    def test_replay_can_reconstruct_gps_from_airsim_ned_velocity(self):
        latitude, longitude = advance_gps_from_ned(45.76, 126.66, 10.0, 5.0)

        self.assertGreater(latitude, 45.76)
        self.assertGreater(longitude, 126.66)
        self.assertAlmostEqual(10.0, (latitude - 45.76) * 111_320.0, places=4)

    def test_incomplete_airsim_data_is_blocked_from_training(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            source_dir = Path(temporary_dir)
            for flight_index in range(3):
                frame = pd.DataFrame(
                    {
                        "timestamp": [0.0, 0.1, 0.2],
                        "voltage": [11.4, 11.4, 11.4],
                        "current": [12.0, 12.5, 12.2],
                        "ambient_temp": [-25.0, -25.0, -25.0],
                        "wind_speed": [8.0, 8.0, 8.0],
                        "velocity_x": [0.0, 1.0, 2.0],
                        "velocity_y": [0.0, 0.0, 0.0],
                        "velocity_z": [0.0, 0.0, 0.0],
                        "altitude": [10.0, 10.1, 10.2],
                    }
                )
                frame.to_csv(source_dir / f"raw_flight_{flight_index:03d}.csv", index=False)

            result = audit(source_dir)

        self.assertFalse(result["training_ready"])
        self.assertEqual(3, result["flight_count"])
        self.assertTrue(any("battery_level" in blocker for blocker in result["blockers"]))

    def test_flight_time_endpoint_reports_missing_model(self):
        sample = {
            "timestamp_s": 0,
            "env_temperature_C": -25,
            "wind_speed_ms": 8,
            "voltage_V": 11.4,
            "current_A": 12,
            "battery_level_pct": 90,
            "speed_ms": 2,
            "altitude_m": 132,
        }
        request = inference_api.FlightTimeRequest(
            drone_id=2,
            samples=[{**sample, "timestamp_s": index} for index in range(30)],
        )
        response = inference_api.predict_flight_time(request)
        self.assertFalse(response.valid)
        self.assertIsNone(response.remaining_flight_time_s)
        self.assertIn("model_not_available", response.reason)

    def test_v1_capacity_model_is_preserved(self):
        self.assertTrue(Path(inference_api.MODEL_PATH).exists())
        self.assertTrue(Path(inference_api.SCALER_PATH).exists())

    def test_airsim_future_capacity_model_assets_are_available(self):
        self.assertTrue(Path(inference_api.AIRSIM_CAPACITY_MODEL_PATH).exists())
        self.assertTrue(Path(inference_api.AIRSIM_CAPACITY_SCALER_PATH).exists())
        self.assertTrue(Path(inference_api.AIRSIM_CAPACITY_REPORT_PATH).exists())

    def test_v1_visual_demo_uses_twenty_holdout_cases(self):
        cases = inference_api.build_capacity_validation_cases(inference_api.load_scaler())

        self.assertEqual(20, len(cases))
        self.assertEqual("B5", cases[0]["battery_id"])
        self.assertEqual(125, cases[0]["input_cycle_start"])
        self.assertEqual(134, cases[0]["input_cycle_end"])
        self.assertEqual(135, cases[0]["target_cycle"])
        self.assertEqual(10, len(cases[0]["cycles"]))

    def test_replay_supports_latest_35_flight_schema(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            source = Path(temporary_dir) / "collected_phase2_data.zip"
            with ZipFile(source, "w") as archive:
                for flight_number in range(2, 37):
                    flight_id = f"flight_{flight_number:03d}"
                    frame = pd.DataFrame(
                        {
                            "flight_id": [flight_id] * 3,
                            "timestamp": [0.0, 0.1, 1.0],
                            "temperature_C": [-25.0, -25.0, -25.0],
                            "wind_speed_ms": [8.0, 8.0, 8.0],
                            "voltage_V": [22.2, 22.1, 22.0],
                            "current_A": [12.0, 12.5, 13.0],
                            "soc_pct": [100.0, 99.9, 99.8],
                            "altitude": [120.0, 121.0, 122.0],
                            "velocity_x": [3.0, 3.0, 3.0],
                            "velocity_y": [4.0, 4.0, 4.0],
                            "velocity_z": [0.0, 0.0, 0.0],
                        }
                    )
                    archive.writestr(f"airsim/{flight_id}.csv", frame.to_csv(index=False))

            flights = load_flights(source)
            selected_id, selected_frame = select_flight(flights, "35")
            columns = resolve_columns(selected_frame)
            prepared = prepare_flight(selected_frame, columns)

        self.assertEqual(35, len(flights))
        self.assertEqual("flight_035", selected_id)
        self.assertEqual("soc_pct", columns["battery_level"])
        self.assertEqual(2, len(prepared))

    def test_replay_keeps_legacy_zip_member_compatible(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            source = Path(temporary_dir) / "legacy.zip"
            frame = pd.DataFrame(
                {
                    "timestamp": [0.0, 1.0],
                    "voltage": [11.4, 11.3],
                    "current": [12.0, 12.5],
                    "ambient_temp": [-25.0, -25.0],
                    "wind_speed": [8.0, 8.0],
                    "velocity_x": [1.0, 1.0],
                    "velocity_y": [0.0, 0.0],
                    "velocity_z": [0.0, 0.0],
                    "altitude": [120.0, 121.0],
                    "latitude": [45.76, 45.76],
                    "longitude": [126.66, 126.66],
                }
            )
            with ZipFile(source, "w") as archive:
                archive.writestr("airsim_data/raw_extreme.csv", frame.to_csv(index=False))

            flights = load_flights(source, "airsim_data/raw_extreme.csv")
            columns = resolve_columns(flights[0][1])

        self.assertEqual("raw_extreme", flights[0][0])
        self.assertIsNone(columns["battery_level"])


if __name__ == "__main__":
    unittest.main()
