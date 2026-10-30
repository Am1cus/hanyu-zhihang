"""Cross-request/restart guarantees for clients replacing the current UI."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fastapi.testclient import TestClient

from competition.core.storage import RunStore
from competition.v2.api import create_app
from competition.v2.contracts import fingerprint
from competition.v2.runtime import RuntimeRun, preset_config
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
        self.assertEqual(len(operations),9)
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
                    run=app.state.runs[result.json()['id']]
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
            self.assertEqual(fingerprint(exported),fingerprint(run.export()))

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
