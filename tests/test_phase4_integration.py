import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Phase3 import inference_api
from Phase4.audit_airsim import audit


class Phase4IntegrationTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
