"""Measure 200 lifecycle cycles and traverse a 1,000-record history."""
import argparse
import gc
import json
from pathlib import Path
import resource
import statistics
import time
import tracemalloc

from fastapi.testclient import TestClient

from competition.v2.api import create_app
from competition.v2.runtime import RuntimeRun, preset_config


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    app=create_app(out/'acceptance.sqlite3',tick_enabled=False)
    tracemalloc.start();groups=[];latencies=[]
    with TestClient(app) as client:
        for i in range(200):
            started=time.perf_counter()
            response=client.post('/api/v2/runs',json={'preset':'normal'})
            response.raise_for_status();run_id=response.json()['id']
            app.state.runs[run_id].advance(1.)
            cancelled=client.post('/api/v2/runs/'+run_id+'/control',json={'action':'cancel'})
            cancelled.raise_for_status()
            assert not cancelled.json()['runtime_available'] and not app.state.runs
            assert not app.state.pending_saves
            latencies.append((time.perf_counter()-started)*1000)
            if (i+1)%50==0:
                gc.collect();current,peak=tracemalloc.get_traced_memory()
                groups.append({'cycles':i+1,'resident_runs':len(app.state.runs),
                    'traced_live_bytes':current,'traced_peak_bytes':peak,
                    'process_maxrss_platform_units':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    'cycle_ms_median':statistics.median(latencies[-50:]),
                    'cycle_ms_p95':sorted(latencies[-50:])[47]})
                print(json.dumps(groups[-1]),flush=True)
        tracemalloc.stop()
        small=RuntimeRun(preset_config('low_budget'))
        full=RuntimeRun(preset_config('normal')).run_all()
        for i in range(800):
            run=full if i%80==0 else small
            run.id=f'history-fixture-{i:04d}';app.state.store.save(run)
        expected={row[0] for row in app.state.store.connection.execute('SELECT id FROM runs')}
        assert len(expected)==1000
        seen=[];cursor=None;timings=[]
        while True:
            started=time.perf_counter()
            page=client.get('/api/v2/history',params={'limit':100,**({'cursor':cursor} if cursor else {})})
            page.raise_for_status();timings.append((time.perf_counter()-started)*1000)
            page=page.json();seen.extend(item['id'] for item in page['items'])
            cursor=page['next_cursor']
            if cursor is None:break
        assert len(seen)==len(set(seen))==1000 and set(seen)==expected
        assert len(client.get('/api/v2/runs').json())==50
        exported=client.get('/api/v2/runs/history-fixture-0000/export');exported.raise_for_status()
        assert exported.json()['result_sha256']==full.export()['result_sha256']
        integrity=app.state.store.connection.execute('PRAGMA integrity_check').fetchone()[0]
        assert integrity=='ok'
        report={'passed':True,'cycles':200,'history_records':1000,'pages':len(timings),
            'history_exactly_once':True,'terminal_resident_after_commit':0,'groups':groups,
            'history_ms_median':statistics.median(timings),'history_ms_max':max(timings),
            'integrity_check':integrity,'scope':'single-process local test; paused and unsaved runs are retained',
            'rss_note':'ru_maxrss is a process high-water mark, not evidence of leaked live objects'}
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
