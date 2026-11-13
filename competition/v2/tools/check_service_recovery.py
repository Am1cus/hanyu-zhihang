"""Real owned-process crash, lost-response, persistent failure and recovery."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT=Path(__file__).resolve().parents[3]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    database=out/'recovery.sqlite3';log=(out/'service.log').open('w');process=None
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}/api/v2';checks={}

    def call(path,body=None,key=None):
        request=Request(url+path,data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type':'application/json',**({'Idempotency-Key':key} if key else {})})
        with urlopen(request,timeout=10) as response:return json.load(response)

    def wait(check,seconds=20):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if process is not None and process.poll() is not None:raise RuntimeError('owned server exited')
            try:
                value=check()
                if value:return value
            except (URLError,sqlite3.OperationalError):pass
            time.sleep(.05)
        raise TimeoutError('recovery check timeout')

    def sql(statement,parameters=()):
        with sqlite3.connect(database,timeout=2) as db:
            return db.execute(statement,parameters).fetchall()

    def stored(run_id):return json.loads(sql('SELECT snapshot FROM runs WHERE id=?',(run_id,))[0][0])

    def start():
        nonlocal process
        process=subprocess.Popen([sys.executable,'competition/v2/launch.py','--no-browser','--port',str(port),
            '--db',str(database)],cwd=PROJECT,stdout=log,stderr=log)
        wait(lambda:call('/health')['status']=='ok')

    def stop(force=False):
        nonlocal process
        if process:
            (process.kill if force else process.terminate)()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait();raise
            process=None

    try:
        start()
        created=call('/runs',{'preset':'normal','speedup':1.},'crash-create');run_id=created['id']
        wait(lambda:stored(run_id)['state']['t_s']>=1)
        stop(force=True);committed=stored(run_id)
        (out/'crash-checkpoint.json').write_text(json.dumps(committed,ensure_ascii=False)+'\n')
        start();archived=call('/runs/'+run_id+'/export')
        assert archived['result_sha256']==committed['result_sha256']
        assert not call('/runs/'+run_id)['runtime_available']
        assert call('/runs',{'preset':'normal','speedup':1.},'crash-create')['id']==run_id
        try:call('/runs/'+run_id+'/control',{'action':'resume'});raise AssertionError('resumed archived run')
        except HTTPError as exc:assert exc.code==409
        checks['committed_checkpoint_survives_sigkill']=True

        body=json.dumps({'preset':'low_budget'}).encode()
        raw=(f'POST /api/v2/runs HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\n'
             f'Idempotency-Key: lost-reply\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode()+body
        with socket.create_connection(('127.0.0.1',port)) as connection:
            connection.sendall(raw)  # Deliberately never read the server response.
        prior=wait(lambda:sql('SELECT run_id FROM creation_requests WHERE request_key=?',('lost-reply',)))[0][0]
        stop(force=True);start()
        assert call('/runs',{'preset':'low_budget'},'lost-reply')['id']==prior
        assert len(call('/runs/'+prior)['execution_audit']['records'])==1
        checks['lost_response_retry_after_restart_exactly_once']=True

        running=call('/runs',{'preset':'normal','speedup':100.},'failure-create')['id']
        sql("CREATE TRIGGER fail_updates BEFORE UPDATE ON runs BEGIN SELECT RAISE(ABORT,'persistent injected failure'); END")
        before=stored(running)
        try:
            wait(lambda:call('/runs/'+running)['t_s']>before['state']['t_s']+10)
            for _ in range(3):
                try:call('/runs/'+running+'/control',{'action':'pause'});raise AssertionError('write passed')
                except HTTPError as exc:assert exc.code==503
            assert stored(running)['result_sha256']==before['result_sha256']
            terminal=wait(lambda:(s if (s:=call('/runs/'+running))['stage']=='TERMINAL' else None),30)
            assert terminal['runtime_available']
        finally:sql('DROP TRIGGER fail_updates')
        wait(lambda:not call('/runs/'+running)['runtime_available'])
        final=call('/runs/'+running+'/export')
        assert final['summary']['returned'] and final['result_sha256']==stored(running)['result_sha256']
        checks['persistent_failure_terminal_retry_and_eviction']=True

        ids=[call('/runs',{'speedup':1.},f'mix-{i}')['id'] for i in range(2)]
        def action(i):
            kind=i%4
            if kind==0:return call('/runs',{'preset':'low_budget'},'mixed-duplicate')['id']
            path='/runs/'+ids[i%2]+'/control'
            try:return call(path,{'action':('resume' if kind==1 else 'pause' if kind==2 else 'cancel')})['status']
            except HTTPError as exc:assert exc.code==409;return 'expected_conflict'
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(action,range(24)))
        assert len(set(results[0::4]))==1
        live=call('/history',None)['items']
        assert sum(r['runtime_available'] and r['summary']['status']=='RUNNING' for r in live)<=1
        duplicate=call('/runs/'+results[0])
        assert len(duplicate['execution_audit']['records'])==1
        checks['interleaved_actions_and_duplicate_requests']=True
        stop();start()
        assert all(not r['runtime_available'] for r in call('/history')['items'])
        assert sql('PRAGMA integrity_check')==[('ok',)]
        checks['database_integrity_and_restart']=True
        report={'passed':all(checks.values()),'checks':checks,'crash_saved_t_s':committed['state']['t_s'],
            'scope':'owned local subprocess and isolated SQLite only; latest committed checkpoint, no resume after restart'}
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False),flush=True)
    finally:stop();log.close()


if __name__=='__main__':main()
