from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from competition.api import create_app
from competition.core.curves import CurveLibrary
from competition.core.simulator import MissionRun, canonical_hash


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

    def test_execution_audit_records_only_valid_controls_without_changing_hash(self):
        state = self.create_run()
        run = self.app.state.runs[state["id"]]
        run.advance(7.5)
        url = f"/api/competition/runs/{run.id}"
        before = self.client.get(url + "/export").json()
        self.assertEqual(state["execution_audit"]["origin"], {"status": "original", "source_run_id": None})
        self.assertEqual(self.client.post(url + "/control", json={"action": "resume"}).status_code, 409)
        self.assertEqual(self.client.post(url + "/control", json={"action": "pause"}).status_code, 200)
        self.assertEqual(self.client.post(url + "/control", json={"action": "pause"}).status_code, 409)
        self.assertEqual(self.client.post(url + "/control", json={"action": "invalid"}).status_code, 400)
        self.assertEqual(self.client.post(url + "/events", json={"type": "obstacle", "cells": [state["start"]]}).status_code, 400)
        self.assertEqual(self.client.post(url + "/control", json={"action": "resume"}).status_code, 200)
        after = self.client.get(url + "/export").json()
        records = after["execution_audit"]["records"]
        self.assertEqual([r["action"] for r in records], ["create", "pause", "resume"])
        self.assertEqual([r["seq"] for r in records], [1, 2, 3])
        self.assertEqual([r["t_s"] for r in records], [0, 7.5, 7.5])
        self.assertEqual(records[1]["status_before"], "RUNNING")
        self.assertEqual(records[1]["status_after"], "PAUSED")
        self.assertTrue(all(r["recorded_at"].endswith("+00:00") for r in records))
        self.assertEqual(after["execution_audit"], after["state"]["execution_audit"])
        self.assertEqual(before["result_sha256"], after["result_sha256"])
        self.assertEqual(after["result_sha256"], canonical_hash({key: after[key] for key in ("summary", "telemetry", "decisions", "events")}))
        self.assertEqual(after["telemetry"], before["telemetry"])
        self.assertNotIn("execution_audit", run.export())
        self.client.post(url + "/control", json={"action": "cancel"})
        self.assertEqual(self.client.post(url + "/control", json={"action": "pause"}).status_code, 409)
        self.assertEqual(self.client.post(url + "/events", json={"type": "wind", "wind": [-3, 0]}).status_code, 409)
        cancelled = self.client.get(url + "/export").json()
        self.assertEqual([r["action"] for r in cancelled["execution_audit"]["records"]], ["create", "pause", "resume", "cancel"])
        self.assertEqual(cancelled["execution_audit"]["records"][-1]["t_s"], 7.5)

    def test_replay_origin_and_operator_history_survive_process_restart(self):
        db = Path(self.directory.name) / "audit-restart.sqlite3"
        with TestClient(create_app(db_path=db, tick_enabled=False)) as first:
            original = first.post("/api/competition/runs", json={}).json()
            url = f"/api/competition/runs/{original['id']}"
            first.app.state.runs[original["id"]].advance(62.2)
            first.post(url + "/control", json={"action": "pause"})
            first.post(url + "/control", json={"action": "resume"})
            first.post(url + "/control", json={"action": "cancel"})
            original_export = first.get(url + "/export").json()
        with TestClient(create_app(db_path=db, tick_enabled=False)) as second:
            archived = second.get(url + "/export").json()
            self.assertEqual(archived["execution_audit"], original_export["execution_audit"])
            replay = second.post("/api/competition/runs", json={"replay_of_run_id": original["id"]}).json()
            expected_origin = {"status": "replay", "source_run_id": original["id"]}
            self.assertEqual(replay["execution_audit"]["origin"], expected_origin)
            records = replay["execution_audit"]["records"]
            self.assertEqual([r["action"] for r in records], ["create", "replay_origin"])
            self.assertEqual(records[1]["source_run_id"], original["id"])
            self.assertEqual(records[1]["t_s"], 0)
            second.app.state.runs[replay["id"]].run_all()
            replay_export = second.get(f"/api/competition/runs/{replay['id']}/export").json()
            self.assertEqual(replay_export["result_sha256"], original_export["result_sha256"])
            self.assertNotEqual(replay_export["execution_audit"], original_export["execution_audit"])
        with TestClient(create_app(db_path=db, tick_enabled=False)) as third:
            restored = third.get(f"/api/competition/runs/{replay['id']}/export").json()
            self.assertEqual(restored["execution_audit"], replay_export["execution_audit"])
            self.assertEqual(third.get(url + "/export").json()["execution_audit"], original_export["execution_audit"])

    def test_shutdown_pause_is_real_system_action_and_archives_missing_history_are_unknown(self):
        db = Path(self.directory.name) / "shutdown-audit.sqlite3"
        with TestClient(create_app(db_path=db, tick_enabled=False)) as first:
            running = first.post("/api/competition/runs", json={}).json()
            historical = MissionRun({}, CurveLibrary()).run_all()
            first.app.state.store.save(historical)
            unknown = first.get(f"/api/competition/runs/{historical.id}/export").json()["execution_audit"]
            self.assertEqual(unknown, {"schema_version": 1, "status": "unknown", "origin": {"status": "unknown", "source_run_id": None}, "records": []})
        with TestClient(create_app(db_path=db, tick_enabled=False)) as second:
            archived = second.get(f"/api/competition/runs/{running['id']}/export").json()
            records = archived["execution_audit"]["records"]
            self.assertEqual([r["action"] for r in records], ["create", "pause"])
            self.assertEqual(records[-1]["source"], "server_shutdown")
            self.assertEqual((records[-1]["status_before"], records[-1]["status_after"]), ("RUNNING", "PAUSED"))
            self.assertEqual(second.get(f"/api/competition/runs/{historical.id}").json()["execution_audit"], unknown)
            listing = {run["id"]: run for run in second.get("/api/competition/runs").json()["runs"]}
            self.assertEqual(listing[historical.id]["execution_audit"], unknown)
            self.assertEqual(listing[running["id"]]["execution_audit"], archived["execution_audit"])

    def test_evaluated_runs_record_creation_and_keep_core_hash(self):
        evaluated = self.client.post("/api/competition/evaluate", json={}).json()
        for state in evaluated["runs"]:
            record = state["execution_audit"]["records"][0]
            self.assertEqual((record["action"], record["source"], record["t_s"]), ("create", "evaluation", 0))
            exported = self.client.get(f"/api/competition/runs/{state['id']}/export").json()
            independently_simulated = MissionRun(exported["configuration"], CurveLibrary()).run_all()
            self.assertEqual(exported["result_sha256"], independently_simulated.export()["result_sha256"])

    def test_live_export_remains_consistent_when_tick_advances_before_serialization(self):
        ticking_app = create_app(db_path=Path(self.directory.name) / "snapshot-race.sqlite3", tick_enabled=True)
        with TestClient(ticking_app) as client:
            state = client.post("/api/competition/runs", json={"speedup": 200}).json()
            observed = {}

            def serialize_after_tick(content, *args, **kwargs):
                # Force an ordinary scheduling window between preparing a
                # response and encoding it. The live simulator continues to
                # tick; an export must still describe one consistent instant.
                snapshot_t_s = content["state"]["t_s"]
                deadline = time.monotonic() + 2
                while ticking_app.state.runs[state["id"]].t_s <= snapshot_t_s:
                    if time.monotonic() >= deadline:
                        raise AssertionError("simulation did not advance during the serialization window")
                    time.sleep(.01)
                observed["advanced_t_s"] = ticking_app.state.runs[state["id"]].t_s
                return JSONResponse(content, *args, **kwargs)

            with patch("competition.api.JSONResponse", serialize_after_tick):
                exported = client.get(f"/api/competition/runs/{state['id']}/export").json()
            self.assertGreater(observed["advanced_t_s"], exported["state"]["t_s"])
            self.assertEqual(exported["telemetry"][-1]["t_s"], exported["state"]["t_s"])
            self.assertEqual(exported["summary"]["duration_s"], exported["state"]["t_s"])
            recomputed = canonical_hash({key: exported[key] for key in ("summary", "telemetry", "decisions", "events")})
            self.assertEqual(exported["result_sha256"], recomputed)


if __name__ == "__main__":
    unittest.main()
