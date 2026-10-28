"""Check the real local HTTP service, export, restart and deterministic replay."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

PROJECT=Path(__file__).resolve().parents[3]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--verified-on',required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'smoke.json').exists(): raise ValueError('Use a fresh output directory')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}'
    database=out/'runtime.sqlite3';process=None
    log=(out/'server.log').open('w',encoding='utf-8')
    def call(path,data=None):
        request=Request(url+'/api/v2'+path,data=None if data is None else json.dumps(data).encode(),
                        headers={'Content-Type':'application/json'})
        with urlopen(request,timeout=10) as response:return json.load(response)
    def wait_for(predicate,timeout=45):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if process is not None and process.poll() is not None:raise RuntimeError('Server exited: see server.log')
            try:
                result=predicate()
                if result:return result
            except (URLError,OSError):pass
            time.sleep(.15)
        raise TimeoutError('Service check timed out')
    def start():
        nonlocal process
        process=subprocess.Popen([sys.executable,str(PROJECT/'competition/v2/launch.py'),
            '--no-browser','--port',str(port),'--db',str(database)],cwd=PROJECT,stdout=log,stderr=log)
        wait_for(lambda:call('/health')['status']=='ok',20)
    def stop():
        nonlocal process
        if process is not None:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait();raise
            process=None
    def finish(run_id):
        def terminal():
            result=call('/runs/'+run_id)
            return result if result['status'] not in {'RUNNING','PAUSED'} else None
        return wait_for(terminal)
    try:
        start()
        created=call('/runs',{'preset':'obstacle','speedup':100.})
        run_id=created['id'];finish(run_id)
        original=call('/runs/'+run_id+'/export')
        assert original['summary']['returned']
        integrated=sum(t['average_voltage_v']*t['current_a']*t['dt_s']/3600 for t in original['telemetry'])
        error=abs(integrated-original['summary']['consumed_wh']);assert error<1e-7
        (out/'original.json').write_text(json.dumps(original,ensure_ascii=False)+'\n')
        stop();start()
        archived=call('/runs/'+run_id);assert archived['runtime_available'] is False
        replay=call('/runs/'+run_id+'/replay',{});finish(replay['id'])
        repeated=call('/runs/'+replay['id']+'/export')
        assert repeated['result_sha256']==original['result_sha256']
        assert repeated['execution_audit']['origin']['source_run_id']==run_id
        report={'verified_on':args.verified_on,'platform':sys.platform,'python':sys.version.split()[0],
            'source':'LOCAL_2D_SIM','real_flight':False,'passed':True,'service_started':True,
            'returned':True,'archive_survived_restart':True,'replay_matching':True,
            'integral_error_wh':error,'result_sha256':original['result_sha256'],
            'database_inside_requested_directory':database.is_file(),
            'source_sha256':original['metadata']['source_sha256'],
            'ui_sha256':hashlib.sha256((PROJECT/'competition/v2/presentation/live.html').read_bytes()).hexdigest()}
        (out/'smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False))
    finally:stop();log.close()


if __name__=='__main__':main()
