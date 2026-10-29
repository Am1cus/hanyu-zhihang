"""Build a self-contained source/wheel delivery without private runtime data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

PROJECT = Path(__file__).resolve().parents[3]
SUFFIXES = {'.py', '.md', '.json', '.html', '.txt', '.csv', '.png', '.command', '.bat'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output, name, wheelhouses=(), media=None):
    if Path(name).name != name or name in {'.', '..'}:
        raise ValueError('Package name must be a single directory name')
    folder = output / name
    archive = output / (name + '.zip')
    if folder.exists() or archive.exists():
        raise ValueError('Output exists; choose a new delivery directory')
    folder.mkdir(parents=True)
    sources = [PROJECT/'competition/__init__.py', PROJECT/'competition/data/p42a_reference.json']
    for subdir in ('competition/core', 'competition/v2'):
        sources += [p for p in (PROJECT/subdir).rglob('*') if p.is_file()
                    and p.suffix in SUFFIXES and '__pycache__' not in p.parts]
    source_hashes = {}
    for source in sorted(set(sources)):
        relative = source.relative_to(PROJECT)
        target = folder/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_hashes[str(relative)] = digest(source)
    shutil.copy2(PROJECT/'启动寒域智航.command', folder/'启动寒域智航.command')
    shutil.copy2(PROJECT/'competition/v2/PORTABLE_README.md', folder/'先读我.md')
    (folder/'启动Windows.bat').write_bytes(b'@echo off\r\ncall "%~dp0competition\\v2\\start_v2.bat" %*\r\n')
    (folder/'检查Mac.command').write_text('#!/bin/zsh\ncd -- "$(dirname -- "$0")"\n'
        'if [[ ! -x .competition-venv/bin/python ]]; then\n'
        '  printf "请先启动程序一次，完成环境安装。\\n"\n'
        'else\n  .competition-venv/bin/python -m competition.v2.tools.verify_package\nfi\n'
        'read -r "?按回车关闭窗口…"\n')
    (folder/'检查Mac.command').chmod(0o755)
    (folder/'检查Windows.bat').write_bytes(('@echo off\nchcp 65001 >nul\ncd /d "%~dp0"\n'
        'if not exist ".competition-venv\\Scripts\\python.exe" (\n'
        '  echo 请先启动程序一次，完成环境安装。\n  pause\n  exit /b 1\n)\n'
        'set PYTHONUTF8=1\n".competition-venv\\Scripts\\python.exe" -m competition.v2.tools.verify_package\n'
        'pause\n').replace('\n','\r\n').encode('utf-8'))
    (folder/'PORTABLE_PACKAGE').write_text('Local runtime records belong in runtime/missions-v2.sqlite3.\n')
    (folder/'启动寒域智航.command').chmod(0o755)
    (folder/'competition/v2/start_v2.command').chmod(0o755)
    for wheelhouse in wheelhouses:
        (folder/'wheelhouse').mkdir(exist_ok=True)
        for source in sorted(wheelhouse.glob('*.whl')):
            target = folder/'wheelhouse'/source.name
            if target.exists() and digest(target) != digest(source):
                raise ValueError('Conflicting wheel: '+source.name)
            shutil.copy2(source, target)
    if media:
        (folder/'media').mkdir()
        for source in sorted(media.iterdir()):
            if source.is_file() and source.suffix in {'.mp4', '.json', '.md', '.srt'}:
                shutil.copy2(source, folder/'media'/source.name)
    try:
        commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    manifest = {'delivery_version': name, 'scope': 'local_2d_reference_simulation',
                'python': '3.12', 'offline_wheels_for': ['macOS_arm64','Windows_amd64'] if wheelhouses else [],
                'git_head_at_build': commit, 'identity_rule': 'file hashes identify delivered bytes; git head alone may precede working edits',
                'source_sha256': source_hashes,
                'files': {str(p.relative_to(folder)): digest(p) for p in sorted(folder.rglob('*')) if p.is_file()}}
    (folder/'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(folder.rglob('*')):
            if path.is_file(): z.write(path,path.relative_to(output))
    return {'directory':str(folder),'archive':str(archive),'archive_sha256':digest(archive),
            'files':len(manifest['files'])+1,'size_bytes':archive.stat().st_size}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--name',default='寒域智航-v2-20261028')
    parser.add_argument('--wheelhouse',action='append',default=[],type=Path)
    parser.add_argument('--media',type=Path)
    args=parser.parse_args()
    print(json.dumps(build(args.output.resolve(),args.name,args.wheelhouse,args.media),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
