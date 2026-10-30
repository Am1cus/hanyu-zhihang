"""One-command checks students can run on the actual presentation computer."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import platform
import os
import re
import subprocess
import sys

PROJECT=Path(__file__).resolve().parents[3]


def verify_manifest(project):
    """Fail closed before executing files from an incomplete delivery."""
    project=project.resolve()
    manifest_path=project/'PACKAGE_MANIFEST.json'
    if not manifest_path.is_file(): return ['PACKAGE_MANIFEST.json: missing']
    try:
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        files=manifest.get('files')
        if not isinstance(files,dict) or not files: return ['PACKAGE_MANIFEST.json: empty or invalid files']
        errors=[]
        for name,expected in files.items():
            relative=PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\' in name:
                errors.append(name+': invalid relative path');continue
            path=(project/name).resolve()
            if not path.is_relative_to(project) or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):
                errors.append(name+': invalid path or digest');continue
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                errors.append(name)
        return errors
    except (OSError,ValueError,TypeError,AttributeError) as exc:
        return ['PACKAGE_MANIFEST.json: '+str(exc)]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verified-on',default=datetime.now().date().isoformat())
    args=parser.parse_args()
    out=(args.output or PROJECT/'runtime'/('checks-'+datetime.now().strftime('%Y%m%d-%H%M%S'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    manifest_path=PROJECT/'PACKAGE_MANIFEST.json'
    mismatches=verify_manifest(PROJECT)
    print('检查交付文件、依赖、软件测试，以及服务重启和复演。',flush=True)
    results={}
    for name,command in (
        ('dependencies',[sys.executable,'-m','pip','check']),
        ('software_tests',[sys.executable,'-m','unittest','discover','-s','competition/v2/tests','-v']),
        ('service_smoke',[sys.executable,'-m','competition.v2.tools.smoke_delivery',
                          '--output',str(out/'service'),'--verified-on',args.verified_on])):
        if mismatches:
            results[name]=False
            continue
        with (out/(name+'.log')).open('w',encoding='utf-8') as log:
            try:
                result=subprocess.run(command,cwd=PROJECT,stdout=log,stderr=log,timeout=180,
                    env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'})
                results[name]=result.returncode==0
            except subprocess.TimeoutExpired:
                results[name]=False
        print(name+('：通过' if results[name] else '：未通过，详见日志'),flush=True)
    report={'verified_on':args.verified_on,'system':platform.system(),'machine':platform.machine(),
            'python':sys.version.split()[0],'package_manifest_present':manifest_path.is_file(),
            'file_mismatches':mismatches,'checks':results,'execution_skipped_due_to_manifest_error':bool(mismatches),
            'passed':not mismatches and all(results.values()),'human_operation_or_projection_test':False}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(('软件检查通过。' if report['passed'] else '检查未通过。')+'报告目录：'+str(out),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
