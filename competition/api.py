"""Single-port local competition app. Run: python -m competition.api"""
from __future__ import annotations

import asyncio
import copy
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import time
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .core.curves import CurveLibrary, DEFAULT_PATH
from .core.scenarios import SCENARIOS, SCENARIO_VERSION, formal_manifest, get_scenario
from .core.simulator import CORE_VERSION, MissionRun, TERMINAL, canonical_hash, compare_runs
from .core.planning import ESTIMATOR_VERSION
from .core.storage import RunStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "output" / "4C" / "runtime" / "missions.sqlite3"
DIST = Path(__file__).parent / "web" / "dist"


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = "normal-s1"
    strategy: str = "energy"
    temperature_c: float = Field(default=-10, ge=-20, le=23)
    reserve_fraction: float = Field(default=.2, ge=0, le=.5)
    speedup: float = Field(default=20, ge=1, le=200)
    replay_of_run_id: str | None = None


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    wind: list[float] | None = None
    cells: list[list[int]] | None = None


class ControlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str


def create_app(db_path=None, curve_path=None, tick_enabled=True):
    live = {}
    execution_lock = threading.RLock()
    library = CurveLibrary(curve_path or os.environ.get("COMPETITION_CURVES_PATH", DEFAULT_PATH))
    app_store = None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal app_store
        app_store = RunStore(db_path or os.environ.get("COMPETITION_DB_PATH", DEFAULT_DB))
        app.state.store = app_store
        app.state.runs = live
        app.state.library = library
        task = None

        async def tick():
            previous = time.monotonic()
            checkpoint = previous
            try:
                while True:
                    await asyncio.sleep(.1)
                    now = time.monotonic()
                    elapsed, previous = min(now - previous, .5), now
                    with execution_lock:
                        for run in list(live.values()):
                            if run.status == "RUNNING":
                                run.advance(elapsed * run.speedup)
                                if run.status in TERMINAL:
                                    app_store.save(run)
                            if now - checkpoint >= .5 and run.status not in TERMINAL:
                                app_store.save(run)
                    if now - checkpoint >= .5:
                        checkpoint = now
            except asyncio.CancelledError:
                return

        if tick_enabled:
            task = asyncio.create_task(tick())
        try:
            yield
        finally:
            if task:
                task.cancel()
                await task
            for run in live.values():
                actions = []
                if run.status == "RUNNING":
                    run.status = "PAUSED"
                    actions.append(audit_action(run, "pause", "server_shutdown", "RUNNING"))
                app_store.save(run, actions)
            app_store.close()

    app = FastAPI(title="寒域智航 · 本机二维任务仿真", version="1.0.0", lifespan=lifespan)

    def audit_action(run, action, source, status_before=None, source_run_id=None):
        return {"action": action, "t_s": run.t_s, "source": source,
                "source_run_id": source_run_id, "status_before": status_before,
                "status_after": run.status}

    def creation_actions(run, request, source):
        actions = [audit_action(run, "create", source)]
        if request.replay_of_run_id:
            actions.append(audit_action(run, "replay_origin", "replay", source_run_id=request.replay_of_run_id))
        return actions

    def attach_audit(exported):
        audit = app_store.execution_audit(exported["state"]["id"])
        exported["execution_audit"] = audit
        exported["state"]["execution_audit"] = audit
        return exported

    def get_export(run_id):
        with execution_lock:
            if run_id in live:
                # JSON serialization happens after this lock is released.
                # Detach nested telemetry/budget/route objects before ticks
                # can mutate them, keeping the response and its hash aligned.
                exported = copy.deepcopy(live[run_id].export())
                exported["state"]["runtime_available"] = True
                return attach_audit(exported)
            archived = app_store.get(run_id)
            if archived is None:
                raise HTTPException(404, "run_not_found")
            archived["state"]["runtime_available"] = False
            return attach_audit(archived)

    def live_state(run):
        with execution_lock:
            return {**copy.deepcopy(run.state()), "runtime_available": True,
                    "execution_audit": app_store.execution_audit(run.id)}

    def get_live(run_id):
        if run_id not in live:
            if app_store.get(run_id):
                raise HTTPException(409, "archived_run_requires_replay_not_resume")
            raise HTTPException(404, "run_not_found")
        return live[run_id]

    def configuration(request):
        if request.replay_of_run_id:
            archived = get_export(request.replay_of_run_id)
            if archived["metadata"].get("curve_sha256") != library.sha256:
                raise HTTPException(409, "curve_fingerprint_changed_replay_refused")
            config = archived["configuration"]
            if config.get("core_version") != CORE_VERSION or config.get("estimator_version") != ESTIMATOR_VERSION:
                raise HTTPException(409, "core_or_estimator_version_changed_replay_refused")
            scenario = config.get("scenario", {})
            try:
                current = get_scenario(config["scenario_id"])
            except (ValueError, KeyError) as exc:
                raise HTTPException(409, "scenario_no_longer_supported_replay_refused") from exc
            if scenario.get("scenario_version") != SCENARIO_VERSION or canonical_hash(scenario) != canonical_hash(current):
                raise HTTPException(409, "scenario_version_or_content_changed_replay_refused")
            return config
        return request.model_dump(exclude={"replay_of_run_id"})

    @app.get("/api/competition/scenarios")
    def scenarios():
        return {"schema_version": 1, "data_source": "LOCAL_2D_SIM",
                "defaults": RunInput().model_dump(exclude={"replay_of_run_id"}),
                "parameter_status": library.status(), "scenarios": SCENARIOS,
                "formal_manifest": formal_manifest(),
                "api_schema": {"envelope": "direct_json_no_java_code_wrapper", "position_unit": "grid_cells",
                               "path": "array_of_[x,y]_current_route", "telemetry": "last_300_samples_export_is_complete",
                               "status": ["RUNNING", "PAUSED", "COMPLETED", "CANCELLED", "FAILED", "UNAVAILABLE"],
                               "event_payloads": [{"type": "wind", "wind": [-3, 0]}, {"type": "obstacle", "cells": [[10, 7]]}],
                               "create": RunInput().model_dump(), "control": {"action": "pause|resume|cancel"},
                               "execution_audit": {"schema_version": 1, "hash_scope": "excluded_from_result_sha256",
                                                   "actions": ["create", "pause", "resume", "cancel", "replay_origin"],
                                                   "historical_missing": "unknown_origin_and_empty_records"},
                               "replay": {"replay_of_run_id": "original_id_configuration_and_applied_manual_events_are_reused"},
                               "temperature": "source_nodes_-20_0_23_and_linear_normalized_capacity_interpolation_without_extrapolation",
                               "forecast_visibility": "planner_receives_only_current_map_wind_not_scheduled_events"}}

    @app.post("/api/competition/runs")
    def create_run(request: RunInput):
        with execution_lock:
            try:
                run = MissionRun(configuration(request), library)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            app_store.save(run, creation_actions(run, request, "operator"))
            live[run.id] = run
            return live_state(run)

    @app.get("/api/competition/runs")
    def list_runs():
        stored = app_store.list(50)
        states = [live_state(live[s["state"]["id"]]) if s["state"]["id"] in live
                  else {**s["state"], "runtime_available": False,
                        "execution_audit": app_store.execution_audit(s["state"]["id"])} for s in stored]
        return {"runs": states}

    @app.get("/api/competition/runs/{run_id}")
    def detail(run_id: str):
        return get_export(run_id)["state"]

    @app.post("/api/competition/runs/{run_id}/events")
    def event(run_id: str, request: EventInput):
        with execution_lock:
            run = get_live(run_id)
            if run.status in TERMINAL:
                raise HTTPException(409, "terminal_run_does_not_accept_events")
            try:
                run.apply_event(request.model_dump(exclude_none=True))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            app_store.save(run)
            return live_state(run)

    @app.post("/api/competition/runs/{run_id}/control")
    def control(run_id: str, request: ControlInput):
        with execution_lock:
            run = get_live(run_id)
            if request.action not in ("pause", "resume", "cancel"):
                raise HTTPException(400, "control_action_must_be_pause_resume_cancel")
            if run.status in TERMINAL:
                raise HTTPException(409, "terminal_run_control_refused")
            if ((request.action == "pause" and run.status != "RUNNING") or
                    (request.action == "resume" and run.status != "PAUSED")):
                raise HTTPException(409, "control_requires_running_to_pause_or_paused_to_resume")
            status_before = run.status
            if request.action == "pause":
                run.status = "PAUSED"
            elif request.action == "resume":
                run.status = "RUNNING"
            else:
                run.cancel()
            app_store.save(run, [audit_action(run, request.action, "operator", status_before)])
            return live_state(run)

    @app.get("/api/competition/runs/{run_id}/export")
    def export(run_id: str):
        return JSONResponse(get_export(run_id), headers={"Content-Disposition": f'attachment; filename="mission-{run_id}.json"'})

    @app.post("/api/competition/evaluate")
    async def evaluate(request: RunInput):
        config = configuration(request)

        def execute():
            paired = []
            for strategy in ("distance", "energy"):
                run = MissionRun({**config, "strategy": strategy}, library)
                app_store.save(run, creation_actions(run, request, "evaluation"))
                run.run_all()
                app_store.save(run)
                paired.append(run)
            return copy.deepcopy({"runs": [{**r.state(), "runtime_available": False,
                                             "execution_audit": app_store.execution_audit(r.id)} for r in paired],
                                  "comparison": compare_runs(*paired),
                                  "whole_mission_budget": {r.strategy: r.initial_whole_mission_budget for r in paired},
                                  "data_source": "LOCAL_2D_SIM", "curve_sha256": library.sha256})

        try:
            return await asyncio.to_thread(execute)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/competition/health")
    def health():
        return {"status": "ok", "app_identity": "competition_local_2d_v1", "data_source": "LOCAL_2D_SIM",
                "parameters_available": library.available}

    @app.get("/{path:path}")
    def static(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "api_not_found")
        root = DIST.resolve()
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root):
            raise HTTPException(404, "file_not_found")
        if candidate.is_file():
            return FileResponse(candidate)
        if (root / "index.html").is_file():
            return FileResponse(root / "index.html")
        return JSONResponse({"status": "web_build_missing", "message": "Build competition/web before opening the local UI."}, status_code=503)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("competition.api:app", host="127.0.0.1", port=8091, reload=False)
