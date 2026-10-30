"""Local-only v2 demo service: python -m competition.v2.api (port 8094)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import copy
from pathlib import Path
import threading
import time
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import ConfigDict, BaseModel, Field

from competition.core.curves import CurveLibrary
from competition.core.storage import RunStore
from .contracts import Selector, BudgetMode, fingerprint
from .runtime import RuntimeRun, RuntimeConfig, RUNTIME_VERSION, TERMINAL, preset_config, execution_source_hashes
from .http_models import (API_VERSION, Archive, Error, Health, LiveState, Preview,
                          QueuedEvent, RunListItem)

RequestKey = Annotated[str | None, Header(alias='Idempotency-Key', min_length=1,
                                        max_length=128, pattern=r'^[A-Za-z0-9._:-]+$')]

ROOT=Path(__file__).resolve().parents[3]
DEFAULT_DB=ROOT/'output/4C/v2/runtime/missions-v2.sqlite3'
PAGE=Path(__file__).parent/'presentation/live.html'


class CreateInput(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False,strict=True)
    preset: Literal['normal','obstacle','gust','low_budget','unavailable','blocked_return']='obstacle'
    selector_id: Selector='value_per_cost'
    temperature_c: float=Field(default=0.,ge=-40,le=30)
    initial_soc: float=Field(default=.85,ge=0,le=1)
    budget_mode: BudgetMode='bounded'
    speedup: float=Field(default=20.,ge=1,le=100)


class ActionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action: Literal['pause','resume','cancel']


class EventInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['obstacle_ahead','gust','both_gates']


def create_app(db_path=None,tick_enabled=True):
    runs={}
    lock=threading.RLock()
    library=CurveLibrary()
    store=None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal store
        store=RunStore(db_path or DEFAULT_DB)
        app.state.runs=runs
        app.state.store=store
        async def tick():
            previous=checkpoint=time.monotonic()
            try:
                while True:
                    await asyncio.sleep(.1)
                    now=time.monotonic();elapsed=min(.5,now-previous);previous=now
                    with lock:
                        for run in runs.values():
                            if run.status=='RUNNING':
                                run.advance(elapsed*run.speedup)
                                if run.status in TERMINAL or now-checkpoint>=.5: store.save(run)
                        if now-checkpoint>=.5: checkpoint=now
            except asyncio.CancelledError: return
        task=asyncio.create_task(tick()) if tick_enabled else None
        try: yield
        finally:
            if task: task.cancel();await task
            with lock:
                for run in runs.values():
                    if run.status=='RUNNING':
                        run.control('pause')
                        store.save(run,[{'action':'pause','source':'server_shutdown','t_s':run.t_s}])
                    else: store.save(run)
                store.close()

    app=FastAPI(title='寒域智航 · 任务决策后端',version=API_VERSION,lifespan=lifespan,
                responses={404: {'model': Error}, 409: {'model': Error}})

    def live(run_id):
        if run_id not in runs:
            if store.get(run_id) is None: raise HTTPException(404,'未找到这次运行')
            raise HTTPException(409,'该记录已归档，请从头复演')
        return runs[run_id]

    def archive(run_id):
        result=runs[run_id].export() if run_id in runs else store.get(run_id)
        if result is None: raise HTTPException(404,'未找到这次运行')
        return copy.deepcopy(result)

    def state(run):
        return {**run.state(),'runtime_available':True,'execution_audit':store.execution_audit(run.id)}

    def saved_state(run_id):
        if run_id in runs: return state(runs[run_id])
        item=archive(run_id)
        return {**item['state'],'runtime_available':False,'execution_audit':store.execution_audit(run_id)}

    def retry_state(key, request_sha256):
        prior=store.creation_request(key) if key is not None else None
        if prior is None: return None
        if prior[0]!=request_sha256:
            raise HTTPException(409,'同一个请求编号已用于不同操作或参数，请使用新的 Idempotency-Key')
        return saved_state(prior[1])

    @app.get('/')
    def page(): return FileResponse(PAGE)

    @app.get('/api/v2/health',response_model=Health)
    def health(): return {'status':'ok','runtime_version':RUNTIME_VERSION,'api_version':API_VERSION,
                         'source':'LOCAL_2D_SIM','library_available':library.available}

    @app.post('/api/v2/preview',response_model=Preview,response_model_exclude_unset=True)
    def preview(request:CreateInput):
        config=preset_config(request.preset,**request.model_dump(exclude={'preset'}))
        run=RuntimeRun(config,library)
        return {**run.state(),'is_preview':True,'runtime_available':False}

    @app.post('/api/v2/runs',response_model=LiveState,response_model_exclude_unset=True)
    def create(request:CreateInput,idempotency_key:RequestKey=None):
        with lock:
            request_sha256=fingerprint({'operation':'create','input':request.model_dump(mode='json')})
            prior=retry_state(idempotency_key,request_sha256)
            if prior is not None: return prior
            config=preset_config(request.preset,**request.model_dump(exclude={'preset'}))
            run=RuntimeRun(config,library)
            store.save(run,[{'action':'create','source':'operator','t_s':0.}],
                       creation_request=(idempotency_key,request_sha256) if idempotency_key is not None else None)
            # One running demonstration per service; previous data remains saved.
            for previous in runs.values():
                if previous.status=='RUNNING':
                    previous.control('pause');store.save(previous,[{'action':'pause','source':'new_demo','t_s':previous.t_s}])
            runs[run.id]=run
            return state(run)

    @app.get('/api/v2/runs',response_model=list[RunListItem],response_model_exclude_unset=True)
    def listing():
        with lock:
            return [{'id':r['state']['id'],'summary':r['summary'],'configuration':r['configuration'],
                     'runtime_available':r['state']['id'] in runs} for r in store.list()]

    @app.get('/api/v2/runs/{run_id}',response_model=LiveState,response_model_exclude_unset=True)
    def get(run_id:str):
        with lock:
            return saved_state(run_id)

    @app.post('/api/v2/runs/{run_id}/control',response_model=LiveState,response_model_exclude_unset=True)
    def control(run_id:str,request:ActionInput):
        with lock:
            run=live(run_id)
            try: run.control(request.action)
            except ValueError as exc: raise HTTPException(409,str(exc)) from exc
            store.save(run,[{'action':request.action,'source':'operator','t_s':run.t_s}])
            return state(run)

    @app.post('/api/v2/runs/{run_id}/events',response_model=QueuedEvent)
    def event(run_id:str,request:EventInput):
        with lock:
            run=live(run_id)
            if request.kind=='gust': payload={'type':'wind','region_id':'east','vector':[-4.,0.]}
            elif request.kind=='both_gates': payload={'type':'obstacle','cells':[[8,3],[8,9]]}
            else:
                candidates=[p for p in run.path[2:] if tuple(p)!=run.scenario.base
                            and tuple(p) not in {t.position for t in run.scenario.tasks}]
                if not candidates: raise HTTPException(409,'当前航段太短；请在下一段航行时再加入禁入区')
                payload={'type':'obstacle','cells':[candidates[0]]}
            try: queued=run.inject(payload)
            except ValueError as exc: raise HTTPException(409,str(exc)) from exc
            store.save(run,[{'action':'event_queued','source':'operator','t_s':run.t_s,'event':queued}])
            return queued

    @app.get('/api/v2/runs/{run_id}/export',response_model=Archive,response_model_exclude_unset=True)
    def export(run_id:str):
        with lock:
            item=archive(run_id)
            item['execution_audit']=store.execution_audit(run_id)
            return item

    @app.post('/api/v2/runs/{run_id}/replay',response_model=LiveState,response_model_exclude_unset=True)
    def replay(run_id:str,idempotency_key:RequestKey=None):
        with lock:
            request_sha256=fingerprint({'operation':'replay','source_run_id':run_id})
            prior=retry_state(idempotency_key,request_sha256)
            if prior is not None: return prior
            original=archive(run_id)
            if original['metadata']['runtime_version']!=RUNTIME_VERSION or original['metadata']['curve_sha256']!=library.sha256:
                raise HTTPException(409,'版本或参考曲线已变化，不能按原版本复演')
            if original['metadata'].get('source_sha256')!=execution_source_hashes():
                raise HTTPException(409,'执行源码已变化，请用原源码包复演')
            if original['configuration_sha256']!=fingerprint(original['configuration']):
                raise HTTPException(409,'原配置指纹不一致')
            run=RuntimeRun(RuntimeConfig.model_validate(original['configuration']),library)
            store.save(run,[{'action':'create','source':'replay','t_s':0.},
                            {'action':'replay_origin','source':'replay','source_run_id':run_id,'t_s':0.}],
                       creation_request=(idempotency_key,request_sha256) if idempotency_key is not None else None)
            for other in runs.values():
                if other.status=='RUNNING':
                    other.control('pause');store.save(other,[{'action':'pause','source':'replay_start','t_s':other.t_s}])
            runs[run.id]=run
            return state(run)

    return app


if __name__=='__main__':
    import uvicorn
    uvicorn.run(create_app(),host='127.0.0.1',port=8094)
