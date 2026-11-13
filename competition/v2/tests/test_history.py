"""Durable terminal eviction and stable, lightweight history pagination."""
import base64
import gc
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
import weakref
from unittest.mock import patch

from fastapi.testclient import TestClient

from competition.v2.api import create_app
from competition.v2.runtime import RuntimeRun, preset_config


class HistoryTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'history.sqlite3'

    def test_terminal_evicted_but_export_replay_and_request_retry_work(self):
        app=create_app(self.path,tick_enabled=False)
        with TestClient(app) as client:
            headers={'Idempotency-Key':'terminal'}
            created=client.post('/api/v2/runs',json={'preset':'low_budget'},headers=headers).json()
            self.assertFalse(created['runtime_available'])
            self.assertEqual(app.state.runs,{})
            again=client.post('/api/v2/runs',json={'preset':'low_budget'},headers=headers).json()
            self.assertEqual(again,created)
            source=client.get('/api/v2/runs/'+created['id']+'/export').json()
            replay=client.post('/api/v2/runs/'+created['id']+'/replay',headers={'Idempotency-Key':'replay'}).json()
            repeated=client.get('/api/v2/runs/'+replay['id']+'/export').json()
            self.assertEqual(source['result_sha256'],repeated['result_sha256'])
            self.assertFalse(replay['runtime_available'])
            self.assertEqual(app.state.runs,{})

    def test_pause_is_retained_and_successful_cancel_clears_pending(self):
        app=create_app(self.path,tick_enabled=False)
        with TestClient(app) as client:
            run_id=client.post('/api/v2/runs',json={}).json()['id']
            path='/api/v2/runs/'+run_id
            self.assertTrue(client.post(path+'/control',json={'action':'pause'}).json()['runtime_available'])
            self.assertEqual(client.post(path+'/control',json={'action':'resume'}).json()['status'],'RUNNING')
            app.state.pending_saves.add(run_id)
            cancelled=client.post(path+'/control',json={'action':'cancel'}).json()
            self.assertFalse(cancelled['runtime_available'])
            self.assertNotIn(run_id,app.state.runs)
            self.assertNotIn(run_id,app.state.pending_saves)

    def test_terminal_stays_resident_until_checkpoint_retry_commits(self):
        app=create_app(self.path)
        with TestClient(app) as client:
            run_id=client.post('/api/v2/runs',json={}).json()['id']
            run=app.state.runs[run_id];advance=run.advance
            with patch.object(run,'advance',side_effect=lambda _:advance(10000)):
                with patch.object(app.state.store,'save',side_effect=sqlite3.OperationalError('test failure')):
                    deadline=time.monotonic()+5
                    while run_id not in app.state.pending_saves and time.monotonic()<deadline:time.sleep(.02)
                    self.assertIn(run_id,app.state.pending_saves)
                    self.assertIn(run_id,app.state.runs)
                    self.assertEqual(app.state.store.get(run_id)['state']['status'],'RUNNING')
                deadline=time.monotonic()+5
                while run_id in app.state.runs and time.monotonic()<deadline:time.sleep(.02)
            self.assertNotIn(run_id,app.state.runs)
            self.assertNotIn(run_id,app.state.pending_saves)
            self.assertEqual(app.state.store.get(run_id)['result_sha256'],run.export()['result_sha256'])
            reference=weakref.ref(run)
            del advance,run
            gc.collect()
            self.assertIsNone(reference(),'a completed run is still strongly referenced after eviction')

    def test_history_snapshot_excludes_new_rows_even_with_old_timestamps(self):
        app=create_app(self.path,tick_enabled=False)
        with TestClient(app) as client:
            run=RuntimeRun(preset_config('low_budget'))
            expected=[]
            for i in range(105):
                run.id=f'row-{i:04d}';app.state.store.save(run);expected.append(run.id)
            connection=app.state.store.connection
            connection.execute("UPDATE runs SET created_at='2026-01-01 00:00:00'");connection.commit()
            first=client.get('/api/v2/history?limit=17').json()
            run.id='new-backdated';app.state.store.save(run)
            connection.execute("UPDATE runs SET created_at='2025-01-01 00:00:00' WHERE id=?",(run.id,));connection.commit()
            ids=[r['id'] for r in first['items']];cursor=first['next_cursor']
            while cursor:
                page=client.get('/api/v2/history',params={'limit':17,'cursor':cursor})
                self.assertEqual(page.status_code,200)
                page=page.json();ids.extend(r['id'] for r in page['items']);cursor=page['next_cursor']
            self.assertEqual(ids,list(reversed(expected)))
            self.assertEqual(len(client.get('/api/v2/runs').json()),50)
            queries=[];connection.set_trace_callback(queries.append)
            client.get('/api/v2/history');client.get('/api/v2/runs')
            connection.set_trace_callback(None)
            self.assertTrue(any('json_extract' in query for query in queries))
            self.assertFalse(any('SELECT snapshot' in query for query in queries))

    def test_empty_page_and_invalid_inputs(self):
        with TestClient(create_app(self.path,tick_enabled=False)) as client:
            self.assertEqual(client.get('/api/v2/history').json(),{'items':[],'next_cursor':None})
            for limit in ('0','101','-1','1.2','true'):
                self.assertEqual(client.get('/api/v2/history',params={'limit':limit}).status_code,422)
            invalid=['','!','a'*513,base64.urlsafe_b64encode(b'[1,2,"date",3]').decode(),
                     base64.urlsafe_b64encode(b'[true,2,"date",1]').decode()]
            for cursor in invalid:
                self.assertEqual(client.get('/api/v2/history',params={'cursor':cursor}).status_code,422)


if __name__=='__main__':unittest.main()
