"""One-command checks students can run on the actual presentation computer."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

PROJECT=Path(__file__).resolve().parents[3]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verified-on',default=datetime.now().date().isoformat())
    args=parser.parse_args()
    out=(args.output or PROJECT/'runtime'/('checks-'+datetime.now().strftime('%Y%m%d-%H%M%S'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    manifest_path=PROJECT/'PACKAGE_MANIFEST.json'
    mismatches=[]
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        for name,expected in manifest['files'].items():
            path=PROJECT/name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                mismatches.append(name)
    print('检查文件、依赖、87项软件检查，以及服务重启和复演。约需一分钟。',flush=True)
    results={}
    for name,command in (
        ('dependencies',[sys.executable,'-m','pip','check']),
        ('software_tests',[sys.executable,'-m','unittest','discover','-s','competition/v2/tests','-v']),
        ('service_smoke',[sys.executable,'-m','competition.v2.tools.smoke_delivery',
                          '--output',str(out/'service'),'--verified-on',args.verified_on])):
        with (out/(name+'.log')).open('w',encoding='utf-8') as log:
            try:
                result=subprocess.run(command,cwd=PROJECT,stdout=log,stderr=log,timeout=180)
                results[name]=result.returncode==0
            except subprocess.TimeoutExpired:
                results[name]=False
        print(name+('：通过' if results[name] else '：未通过，详见日志'),flush=True)
    report={'verified_on':args.verified_on,'system':platform.system(),'machine':platform.machine(),
            'python':sys.version.split()[0],'package_manifest_present':manifest_path.is_file(),
            'file_mismatches':mismatches,'checks':results,
            'passed':not mismatches and all(results.values()),'human_operation_or_projection_test':False}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(('软件检查通过。' if report['passed'] else '检查未通过。')+'报告目录：'+str(out),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
