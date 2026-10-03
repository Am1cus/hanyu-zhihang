from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from competition.api import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app(db_path=Path(self.directory.name) / "test.sqlite3", tick_enabled=False)
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.directory.cleanup()

    def create_run(self, **configuration):
        response = self.client.post("/api/competition/runs", json=configuration)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_contract_identity_defaults_and_initial_budget(self):
        response = self.client.get("/api/competition/scenarios").json()
        self.assertEqual(response["data_source"], "LOCAL_2D_SIM")
        self.assertTrue(response["parameter_status"]["available"])
        self.assertEqual(response["formal_manifest"]["paired_executions"], 48)
        self.assertEqual(self.client.get("/api/competition/health").json()["app_identity"], "competition_local_2d_v1")
        run = self.create_run()
        self.assertEqual(run["status"], "RUNNING")
        self.assertEqual(run["parameter_status"]["profile_kind"], "temperature_interpolation")
        self.assertIn("initial_whole_mission_budget", run)
        self.assertTrue(run["runtime_available"])

    def test_pause_resume_cancel_and_terminal_controls(self):
        run = self.create_run()
        url = f"/api/competition/runs/{run['id']}"
        self.assertEqual(self.client.post(url + "/control", json={"action": "pause"}).json()["status"], "PAUSED")
        self.assertEqual(self.client.get(url).json()["t_s"], 0)
        self.assertEqual(self.client.post(url + "/control", json={"action": "resume"}).json()["status"], "RUNNING")
        self.assertEqual(self.client.post(url + "/control", json={"action": "cancel"}).json()["status"], "CANCELLED")
        self.assertEqual(self.client.post(url + "/control", json={"action": "resume"}).status_code, 409)
        archive = self.client.get(url + "/export").json()
        self.assertEqual(archive["summary"]["ended_reason"], "operator_cancelled")
        self.assertFalse(archive["summary"]["returned"])

    def test_invalid_input_and_event_on_occupied_edge(self):
        self.assertEqual(self.client.post("/api/competition/runs", json={"scenario_id": "unknown"}).status_code, 400)
        self.assertEqual(self.client.post("/api/competition/runs", json={"strategy": "fake-ai"}).status_code, 400)
        self.assertEqual(self.client.post("/api/competition/runs", json={"temperature_c": -30}).status_code, 422)
        self.assertEqual(self.client.post("/api/competition/runs", json={"speedup": 0}).status_code, 422)
        self.assertEqual(self.client.post("/api/competition/runs", json={"data_source": "AIRSIM"}).status_code, 422)
        run = self.create_run()
        url = f"/api/competition/runs/{run['id']}"
        self.assertEqual(self.client.post(url + "/events", json={"type": "obstacle", "cells": [run["start"]]}).status_code, 400)
        self.assertEqual(self.client.post(url + "/events", json={"type": "wind", "wind": [-3, 0]}).json()["events"][0]["source"], "manual")
        self.assertEqual(self.client.get("/api/competition/runs/not-found").status_code, 404)

    def test_full_evaluation_and_replay_share_frozen_configuration(self):
        evaluated = self.client.post("/api/competition/evaluate", json={"scenario_id": "gust-s1", "temperature_c": -10}).json()
        self.assertEqual(len(evaluated["runs"]), 2)
        self.assertEqual(set(evaluated["whole_mission_budget"]), {"distance", "energy"})
        original = evaluated["runs"][0]
        exported = self.client.get(f"/api/competition/runs/{original['id']}/export").json()
        replay = self.create_run(replay_of_run_id=original["id"])
        self.assertEqual(replay["strategy"], "distance")
        self.assertEqual(replay["scenario_id"], "gust-s1")
        self.app.state.runs[replay["id"]].run_all()
        actual = self.client.get(f"/api/competition/runs/{replay['id']}/export").json()
        self.assertEqual(exported["result_sha256"], actual["result_sha256"])
        self.assertGreater(len(actual["telemetry"]), 300)
        self.assertLessEqual(len(actual["state"]["telemetry"]), 300)

    def test_missing_curves_report_unavailable_over_api(self):
        missing = create_app(db_path=Path(self.directory.name) / "missing.sqlite3",
                             curve_path=Path(self.directory.name) / "absent.json", tick_enabled=False)
        with TestClient(missing) as client:
            run = client.post("/api/competition/runs", json={}).json()
            self.assertEqual(run["status"], "UNAVAILABLE")
            self.assertEqual(run["telemetry"], [])
            self.assertIsNone(run["summary"]["total_energy_wh"])
            evaluated = client.post("/api/competition/evaluate", json={}).json()
            self.assertIsNone(evaluated["comparison"]["energy_saving_pct"])

    def test_replay_rejects_core_estimator_or_scenario_changes(self):
        for key in ("core_version", "estimator_version", "scenario"):
            with self.subTest(key=key):
                state = self.create_run()
                run = self.app.state.runs[state["id"]]
                if key == "scenario":
                    run.configuration["scenario"]["cell_size_m"] = 999
                else:
                    run.configuration[key] = "unsupported-version"
                response = self.client.post("/api/competition/runs", json={"replay_of_run_id": run.id})
                self.assertEqual(response.status_code, 409)

    def test_process_restart_marks_archives_uncontrollable_and_replayable(self):
        temporary_db = Path(self.directory.name) / "restart.sqlite3"
        with TestClient(create_app(db_path=temporary_db, tick_enabled=False)) as first:
            run = first.post("/api/competition/runs", json={}).json()
            self.assertTrue(run["runtime_available"])
        with TestClient(create_app(db_path=temporary_db, tick_enabled=False)) as second:
            archived = second.get(f"/api/competition/runs/{run['id']}").json()
            self.assertFalse(archived["runtime_available"])
            self.assertFalse(second.get("/api/competition/runs").json()["runs"][0]["runtime_available"])
            self.assertEqual(second.post(f"/api/competition/runs/{run['id']}/control", json={"action": "resume"}).status_code, 409)
            replay = second.post("/api/competition/runs", json={"replay_of_run_id": run["id"]}).json()
            self.assertTrue(replay["runtime_available"])
            self.assertNotEqual(run["id"], replay["id"])


if __name__ == "__main__":
    unittest.main()
