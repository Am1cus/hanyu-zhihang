"""Local demo launcher. Bootstrap only the project's private environment."""
from __future__ import annotations

import sys
from pathlib import Path

# Direct execution must not shadow stdlib selectors with v2/selectors.py.
if not __package__:
    sys.path[0] = str(Path(__file__).resolve().parents[2])

import argparse
from importlib import metadata
import json
import os
import socket
import subprocess
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

PROJECT = Path(__file__).resolve().parents[2]
LOCK = Path(__file__).with_name('requirements-lock.txt')
VENV = PROJECT / '.competition-venv'


def environment_report():
    missing = []
    versions = {}
    for line in LOCK.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        name, expected = line.split('==')
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            actual = None
        versions[name] = actual
        if actual != expected:
            missing.append(f'{name}: {actual or "未安装"}，需要 {expected}')
    python_ok = sys.version_info[:2] == (3, 12)
    return {'ready': python_ok and not missing,
            'python': sys.version.split()[0], 'python_supported': python_ok,
            'executable': sys.executable, 'dependencies': versions,
            'dependency_mismatches': missing, 'project': str(PROJECT)}


def prepare_environment():
    python = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    # Comparing prefixes avoids resolving a venv symlink back to the system Python.
    if Path(sys.prefix).resolve() != VENV.resolve():
        if not python.exists():
            if sys.version_info[:2] != (3, 12):
                raise RuntimeError('请安装 Python 3.12 后再双击启动。本机已验证 Python 3.12。')
            print('首次启动：正在建立项目专用 Python 环境…', flush=True)
            subprocess.run([sys.executable, '-m', 'venv', str(VENV)], check=True)
        os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    report = environment_report()
    if not report['python_supported']:
        raise RuntimeError('项目环境需要 Python 3.12；离线依赖包也按此版本准备。')
    if report['dependency_mismatches']:
        wheels = PROJECT / 'wheelhouse'
        command = [sys.executable, '-m', 'pip', 'install', '-r', str(LOCK)]
        if wheels.is_dir():
            print('首次安装：使用包内固定依赖，不连接网络。', flush=True)
            command += ['--no-index', '--find-links', str(wheels)]
        else:
            print('首次安装：正在联网安装固定依赖；安装成功后可离线演示。', flush=True)
        subprocess.run(command, check=True)
    if not environment_report()['ready']:
        raise RuntimeError('依赖仍未安装完整；请保留窗口中的错误信息。')


def service_health(url):
    try:
        with urlopen(url + '/api/v2/health', timeout=1) as response:
            value = json.load(response)
        return (value.get('status') == 'ok' and value.get('source') == 'LOCAL_2D_SIM'
                and value.get('runtime_version') == 'competition-v2-runtime-0.1')
    except (URLError, OSError, ValueError):
        return False


def open_when_ready(url):
    for _ in range(80):
        if service_health(url):
            webbrowser.open(url)
            return
        time.sleep(.25)
    print('浏览器尚未打开。请查看错误信息；服务正常时可手动打开：' + url, flush=True)


def main():
    parser = argparse.ArgumentParser(description='启动寒域智航本机演示')
    parser.add_argument('--check', action='store_true', help='只检查当前 Python 环境，不安装、不启动')
    parser.add_argument('--no-browser', action='store_true', help='启动服务但不自动打开浏览器')
    parser.add_argument('--port', type=int, default=8094)
    parser.add_argument('--db', type=Path, help='独立记录库，默认使用 v2 记录目录')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('端口需要在 1024—65535 之间')
    if args.check:
        report = environment_report()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ready'] else 1
    prepare_environment()
    sys.path.insert(0, str(PROJECT))
    from competition.v2.api import create_app
    from competition.core.curves import CurveLibrary
    import uvicorn

    library = CurveLibrary()
    if not library.available:
        raise RuntimeError('低温参考参数无法读取：' + str(library.reason))
    url = f'http://127.0.0.1:{args.port}'
    with socket.socket() as probe:
        # A bind probe can mistake recently closed connections (TIME_WAIT) for
        # an active service. Check for a listener; uvicorn owns the actual bind.
        probe.settimeout(1)
        if probe.connect_ex(('127.0.0.1', args.port)) == 0:
            if service_health(url):
                if args.db:
                    raise RuntimeError('该端口已有服务，不能确认其记录库；请指定其他 --port。')
                print('寒域智航已经启动，使用已有窗口：' + url, flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                return 0
            raise RuntimeError(f'端口 {args.port} 被其他程序占用；可加 --port 8097 换端口，不会关闭其他程序。')
    print(f'寒域智航已准备启动：{url}\n'
          '保持这个窗口打开。结束时按 Control+C；记录会保存，下次可查看和从头复演。\n'
          '这是本机二维参考仿真，不控制真实无人机。', flush=True)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    database = args.db
    if database is None and (PROJECT / 'PORTABLE_PACKAGE').is_file():
        database = PROJECT / 'runtime' / 'missions-v2.sqlite3'
    uvicorn.run(create_app(database), host='127.0.0.1', port=args.port, access_log=False)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print('\n启动未完成：' + str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)
