"""Cross-request/restart guarantees for clients replacing the current UI."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from competition.core.storage import RunStore
from competition.v2.api import create_app
from competition.v2.contracts import fingerprint
from competition.v2.runtime import RuntimeRun, RuntimeConfig, preset_config
from competition.v2.tools.verify_package import verify_manifest


class HttpDeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name)/'中文 record.sqlite3'

    def test_every_api_operation_has_response_schema(self):
        schema=create_app(self.path,tick_enabled=False).openapi()
        operations=[operation for path,item in schema['paths'].items() if path.startswith('/api/')
                    for method,operation in item.items() if method in {'get','post'}]
        self.assertEqual(len(operations),10)
        for operation in operations:
            self.assertTrue(operation['responses']['200']['content']['application/json']['schema'])

    def test_serialized_archives_preserve_all_numbers_fields_and_failure_states(self):
        app=create_app(self.path,tick_enabled=False)
        with TestClient(app) as client:
            cases=[{'preset':preset} for preset in ('normal','obstacle','gust','low_budget','unavailable','blocked_return')]
            cases += [{'preset':'normal','initial_soc':.55}]
            statuses=set()
            for request in cases:
                with self.subTest(request=request):
                    preview=client.post('/api/v2/preview',json=request)
                    self.assertEqual(preview.status_code,200)
                    result=client.post('/api/v2/runs',json=request)
                    self.assertEqual(result.status_code,200)
                    run_id=result.json()['id']
                    initial=client.get('/api/v2/runs/'+run_id+'/export').json()
                    run=app.state.runs.get(run_id) or RuntimeRun(
                        RuntimeConfig.model_validate(initial['configuration']),run_id=run_id)
                    run.run_all();app.state.store.save(run)
                    saved=client.get('/api/v2/runs/'+run.id+'/export').json()
                    saved.pop('execution_audit')
                    self.assertEqual(fingerprint(saved),fingerprint(run.export()))
                    statuses.add(saved['summary']['status'])
            self.assertTrue({'COMPLETED_RETURNED','PARTIAL_RETURNED','REFUSED','FAILED','UNAVAILABLE'}<=statuses,statuses)
            self.assertEqual(len(client.get('/api/v2/runs').json()),len(cases))

    def test_mid_edge_pause_and_cancel_export_keep_null_interval_coverage(self):
        app=create_app(self.path,tick_enabled=False)
        with TestClient(app) as client:
            state=client.post('/api/v2/runs',json={}).json();run=app.state.runs[state['id']]
            run.advance(.5)
            paused=client.post('/api/v2/runs/'+run.id+'/control',json={'action':'pause'})
            self.assertEqual(paused.json()['status'],'PAUSED')
            cancelled=client.post('/api/v2/runs/'+run.id+'/control',json={'action':'cancel'})
            self.assertEqual(cancelled.json()['status'],'CANCELLED')
            exported=client.get('/api/v2/runs/'+run.id+'/export').json()
            self.assertIsNone(exported['intervals'][-1]['covered'])
            exported.pop('execution_audit')
            self.assertEqual(fingerprint(exported),fingerprint(app.state.store.get(run.id)))
            self.assertNotIn(run.id,app.state.runs)

    def test_same_key_survives_restart_and_does_not_pause_other_run(self):
        headers={'Idempotency-Key':'create-001'}
        with TestClient(create_app(self.path,tick_enabled=False)) as client:
            first=client.post('/api/v2/runs',json={},headers=headers).json()
            other=client.post('/api/v2/runs',json={}).json()
            retry=client.post('/api/v2/runs',json={},headers=headers).json()
            self.assertEqual(retry['id'],first['id'])
            self.assertEqual(client.get('/api/v2/runs/'+other['id']).json()['status'],'RUNNING')
            self.assertEqual(len(retry['execution_audit']['records']),2)  # create + pause by second run
        with TestClient(create_app(self.path,tick_enabled=False)) as client:
            retry=client.post('/api/v2/runs',json={},headers=headers).json()
            self.assertEqual(retry['id'],first['id'])
            self.assertFalse(retry['runtime_available'])
            self.assertEqual(len(client.get('/api/v2/runs').json()),2)

    def test_concurrent_retries_create_one_run_and_one_audit_action(self):
        with TestClient(create_app(self.path,tick_enabled=False)) as client:
            def send(_):
                return client.post('/api/v2/runs',json={},headers={'Idempotency-Key':'parallel'}).json()
            with ThreadPoolExecutor(max_workers=4) as pool: responses=list(pool.map(send,range(8)))
            self.assertEqual(len({r['id'] for r in responses}),1)
            self.assertEqual(len(client.get('/api/v2/runs').json()),1)
            self.assertEqual(len(responses[-1]['execution_audit']['records']),1)

    def test_conflicting_key_returns_409_without_changing_live_run(self):
        with TestClient(create_app(self.path,tick_enabled=False)) as client:
            headers={'Idempotency-Key':'unique-intent'}
            first=client.post('/api/v2/runs',json={},headers=headers).json()
            self.assertEqual(client.post('/api/v2/runs',json={'temperature_c':-20.},headers=headers).status_code,409)
            self.assertEqual(client.post('/api/v2/runs/'+first['id']+'/replay',headers=headers).status_code,409)
            self.assertEqual(client.get('/api/v2/runs/'+first['id']).json()['status'],'RUNNING')
            self.assertEqual(len(client.get('/api/v2/runs').json()),1)

    def test_replay_retry_survives_restart_without_duplicate_origin(self):
        headers={'Idempotency-Key':'repeat-record-001'}
        with TestClient(create_app(self.path,tick_enabled=False)) as client:
            source=client.post('/api/v2/runs',json={}).json()['id']
            replay=client.post('/api/v2/runs/'+source+'/replay',headers=headers).json()
            again=client.post('/api/v2/runs/'+source+'/replay',headers=headers).json()
            self.assertEqual(again['id'],replay['id'])
            self.assertEqual(len(again['execution_audit']['records']),2)
        with TestClient(create_app(self.path,tick_enabled=False)) as client:
            again=client.post('/api/v2/runs/'+source+'/replay',headers=headers).json()
            self.assertEqual(again['id'],replay['id'])
            self.assertFalse(again['runtime_available'])
            self.assertEqual(again['execution_audit']['origin']['source_run_id'],source)

    def test_invalid_key_and_missing_run_do_not_modify_database(self):
        with TestClient(create_app(self.path,tick_enabled=False)) as client:
            for key in ('', 'has space', 'a'*129):
                self.assertEqual(client.post('/api/v2/runs',json={},headers={'Idempotency-Key':key}).status_code,422)
            self.assertEqual(client.post('/api/v2/runs/missing/control',json={'action':'pause'}).status_code,404)
            self.assertEqual(client.post('/api/v2/runs/missing/events',json={'kind':'gust'}).status_code,404)
            self.assertEqual(client.get('/api/v2/runs').json(),[])

    def test_failed_save_rolls_back_both_key_and_run(self):
        store=RunStore(self.path);self.addCleanup(store.close)
        store.connection.execute("CREATE TRIGGER fail_run BEFORE INSERT ON runs BEGIN SELECT RAISE(ABORT,'injected write failure'); END")
        run=RuntimeRun(preset_config())
        with self.assertRaises(sqlite3.IntegrityError):
            store.save(run,creation_request=('failed-request','sha'))
        self.assertIsNone(store.creation_request('failed-request'))
        self.assertIsNone(store.get(run.id))
        store.connection.execute('DROP TRIGGER fail_run')
        store.save(run,creation_request=('failed-request','sha'))
        self.assertEqual(store.creation_request('failed-request'),('sha',run.id))

    def test_existing_database_without_request_table_keeps_its_archive(self):
        run=RuntimeRun(preset_config());store=RunStore(self.path);store.save(run)
        store.connection.execute('DROP TABLE creation_requests');store.connection.commit();store.close()
        reopened=RunStore(self.path);self.addCleanup(reopened.close)
        self.assertEqual(reopened.get(run.id)['result_sha256'],run.export()['result_sha256'])
        self.assertIsNone(reopened.creation_request('never-seen'))

    def test_nonfinite_input_returns_json_validation_error_without_writing(self):
        with TestClient(create_app(self.path,tick_enabled=False)) as client:
            for path in ('/api/v2/runs','/api/v2/preview'):
                for value in ('NaN', '1e999', '-1e999', '[NaN]'):
                    response=client.post(path,content='{"speedup":'+value+'}',
                                         headers={'Content-Type':'application/json','Idempotency-Key':'invalid'})
                    self.assertEqual(response.status_code,422)
                    self.assertEqual(response.json()['detail'][0]['loc'],['body','speedup'])
            self.assertEqual(client.get('/api/v2/runs').json(),[])
            self.assertEqual(client.post('/api/v2/runs',json={},headers={'Idempotency-Key':'invalid'}).status_code,200)

    def test_create_and_replay_roll_back_when_previous_run_cannot_be_paused(self):
        app=create_app(self.path,tick_enabled=False)
        with TestClient(app) as client:
            root='/api/v2/runs'
            active=client.post(root,json={}).json()['id']
            connection=app.state.store.connection
            for path in (root,f'{root}/{active}/replay'):
                with self.subTest(path=path):
                    headers={'Idempotency-Key':'switch-'+active}
                    before=client.get(root).json()
                    connection.execute("""CREATE TRIGGER fail_pause BEFORE UPDATE ON runs
                        WHEN NEW.status='PAUSED' BEGIN SELECT RAISE(ABORT,'injected pause failure'); END""")
                    try:
                        self.assertEqual(client.post(path,json={},headers=headers).status_code,503)
                        self.assertEqual(client.get(root).json(),before)
                        self.assertEqual(client.get(f'{root}/{active}').json()['status'],'RUNNING')
                        self.assertIsNone(app.state.store.creation_request(headers['Idempotency-Key']))
                    finally:
                        connection.execute('DROP TRIGGER fail_pause')
                    retried=client.post(path,json={},headers=headers)
                    self.assertEqual(retried.status_code,200)
                    self.assertEqual(client.get(f'{root}/{active}').json()['status'],'PAUSED')
                    active=retried.json()['id']

    def test_failed_control_and_event_leave_export_and_audit_unchanged(self):
        app=create_app(self.path,tick_enabled=False)
        with TestClient(app) as client:
            run_id=client.post('/api/v2/runs',json={}).json()['id']
            path=f'/api/v2/runs/{run_id}'
            before=client.get(path+'/export').json()
            connection=app.state.store.connection
            connection.execute("""CREATE TRIGGER fail_audit BEFORE INSERT ON execution_audit
                BEGIN SELECT RAISE(ABORT,'injected audit failure'); END""")
            try:
                self.assertEqual(client.post(path+'/control',json={'action':'cancel'}).status_code,503)
                self.assertEqual(client.post(path+'/events',json={'kind':'gust'}).status_code,503)
                self.assertEqual(client.get(path+'/export').json(),before)
                self.assertEqual(app.state.store.get(run_id)['result_sha256'],before['result_sha256'])
            finally:
                connection.execute('DROP TRIGGER fail_audit')
            queued=client.post(path+'/events',json={'kind':'gust'}).json()
            self.assertEqual(queued['event_id'],'manual:manual-1')
            self.assertEqual(client.post(path+'/control',json={'action':'cancel'}).status_code,200)

    def test_resume_switches_active_run_and_lifespan_restart_archives_both(self):
        app=create_app(self.path,tick_enabled=False)
        root='/api/v2/runs'
        with TestClient(app) as client:
            first=client.post(root,json={}).json()['id']
            second=client.post(root,json={}).json()['id']
            before=[client.get(f'{root}/{run_id}/export').json() for run_id in (first,second)]
            connection=app.state.store.connection
            connection.execute("""CREATE TRIGGER fail_resume_switch BEFORE UPDATE ON runs
                WHEN NEW.status='PAUSED' BEGIN SELECT RAISE(ABORT,'injected switch failure'); END""")
            try:
                self.assertEqual(client.post(f'{root}/{first}/control',json={'action':'resume'}).status_code,503)
                self.assertEqual([client.get(f'{root}/{run_id}/export').json() for run_id in (first,second)],before)
            finally:
                connection.execute('DROP TRIGGER fail_resume_switch')
            self.assertEqual(client.post(f'{root}/{first}/control',json={'action':'resume'}).json()['status'],'RUNNING')
            other=client.get(f'{root}/{second}').json()
            self.assertEqual(other['status'],'PAUSED')
            self.assertEqual(other['execution_audit']['records'][-1]['source'],'resume_demo')
        with TestClient(app) as client:
            self.assertTrue(all(not row['runtime_available'] for row in client.get(root).json()))
            self.assertEqual(client.post(f'{root}/{first}/control',json={'action':'resume'}).status_code,409)
            self.assertEqual(client.get(f'{root}/{first}/export').json()['state']['status'],'PAUSED')

    def test_checkpoint_retries_after_sqlite_write_failure(self):
        app=create_app(self.path)
        with TestClient(app) as client:
            store=app.state.store
            run_id=client.post('/api/v2/runs',json={}).json()['id']
            with store.lock:
                store.connection.execute("""CREATE TRIGGER fail_checkpoint BEFORE UPDATE ON runs
                    BEGIN SELECT RAISE(ABORT,'injected checkpoint failure'); END""")
            try:
                with self.assertLogs('competition.v2.api',level='WARNING'):
                    deadline=time.monotonic()+5
                    while client.get(f'/api/v2/runs/{run_id}').json()['t_s']<15 and time.monotonic()<deadline:
                        time.sleep(.05)
                    self.assertEqual(store.get(run_id)['state']['t_s'],0)
            finally:
                with store.lock:
                    store.connection.execute('DROP TRIGGER fail_checkpoint')
            deadline=time.monotonic()+5
            while store.get(run_id)['state']['t_s']==0 and time.monotonic()<deadline:
                time.sleep(.05)
            self.assertGreater(store.get(run_id)['state']['t_s'],0)

    def test_terminal_snapshot_is_retried_even_after_execution_has_finished(self):
        app=create_app(self.path)
        with TestClient(app) as client:
            run_id=client.post('/api/v2/runs',json={}).json()['id']
            run=app.state.runs[run_id]
            advance=run.advance
            save=app.state.store.save
            failed=[]

            def fail_first_terminal_snapshot(current):
                if current.status=='COMPLETED_RETURNED' and not failed:
                    failed.append(current.id)
                    raise sqlite3.OperationalError('injected terminal checkpoint failure')
                return save(current)

            with self.assertLogs('competition.v2.api',level='WARNING'):
                with patch.object(run,'advance',side_effect=lambda duration:advance(10000)):
                    with patch.object(app.state.store,'save',side_effect=fail_first_terminal_snapshot):
                        deadline=time.monotonic()+5
                        while app.state.store.get(run_id)['summary']['status']=='RUNNING' and time.monotonic()<deadline:
                            time.sleep(.05)
                        saved=app.state.store.get(run_id)
                        self.assertEqual(failed,[run_id])
                        self.assertEqual(saved['summary']['status'],'COMPLETED_RETURNED')
                        self.assertEqual(saved['result_sha256'],run.export()['result_sha256'])


class DeliveryManifestTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.file=self.root/'sample.txt';self.file.write_text('参数',encoding='utf-8')
        self.manifest=self.root/'PACKAGE_MANIFEST.json'

    def write_manifest(self,files):
        self.manifest.write_text(json.dumps({'files':files}),encoding='utf-8')

    def test_missing_or_empty_manifest_never_passes(self):
        self.assertTrue(verify_manifest(self.root))
        self.write_manifest({});self.assertTrue(verify_manifest(self.root))

    def test_corrupt_manifest_never_passes(self):
        self.manifest.write_text('{broken',encoding='utf-8')
        self.assertTrue(verify_manifest(self.root))

    def test_modified_or_deleted_file_never_passes(self):
        self.write_manifest({'sample.txt':hashlib.sha256(self.file.read_bytes()).hexdigest()})
        self.assertEqual(verify_manifest(self.root),[])
        self.file.write_text('changed',encoding='utf-8');self.assertTrue(verify_manifest(self.root))
        self.file.unlink();self.assertTrue(verify_manifest(self.root))

    def test_manifest_paths_cannot_escape_package(self):
        for name in ('../outside','/absolute','..\\outside'):
            self.write_manifest({name:'0'*64});self.assertTrue(verify_manifest(self.root))


if __name__=='__main__':unittest.main()
