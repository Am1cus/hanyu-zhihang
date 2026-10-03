"""Package only competition sources, evidence and reviewed deliverables.

Excludes runtime DBs, original project databases/models, dependencies and private
build intermediates. The web dist and licensed font are intentionally included.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


EXCLUDED = {"node_modules", "__pycache__", ".DS_Store", ".pytest_cache",
            ".git", ".venv", ".competition-venv", "venv"}


def copy_tree(source, destination):
    for p in sorted(source.rglob("*")):
        if (not p.is_file() or p.is_symlink()
                or any(part in EXCLUDED for part in p.relative_to(source).parts)
                or p.name.endswith((".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".pyc"))):
            continue
        target = destination / p.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--stage-only", action="store_true",
                        help="Prepare the directory for independent verification without producing a ZIP.")
    args = parser.parse_args()
    root = args.workspace.resolve()
    out = root / "output/4C"
    destination = out / ".build/delivery/寒域智航4C"
    if destination.exists():
        # This directory is exclusively a generated package staging directory.
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    # api.py resolves its project root with parents[2]. Preserve that depth so
    # runtime output stays inside the package rather than next to the package.
    copy_tree(root / "learn/competition", destination / "learn/competition")
    copy_tree(out / "evidence", destination / "evidence")
    copy_tree(out / "media", destination / "media")
    for path in (args.pptx.resolve(), args.pdf.resolve(), out / "presentation/9分钟讲稿.md", out / "presentation/talk.json"):
        assert path.is_file(), path
        target = destination / "presentation" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    copy_tree(out / "presentation/slides", destination / "presentation/slides")
    copy_tree(out / "docs", destination / "docs")
    font_dir = destination / "fonts"
    font_dir.mkdir()
    for name in ("SourceHanSansSC-Regular.otf", "LICENSE.txt"):
        shutil.copy2(out / ".build/fonts" / name, font_dir / name)
    welcome = r"""# 寒域智航 4C 首版交付包

先阅读 learn/competition/OPERATION_MANUAL.md。源码与构建网页位于 learn/competition/，
PowerPoint/PDF/逐页讲稿位于 presentation/，实际备用录屏和合成练习视频位于 media/。
完整实验和复算证据位于 evidence/，学生任务与学术优化分析位于 learn/competition/。

本包可独立运行，不包含旧 Java/AirSim/LSTM 服务或其数据库。
已包含构建好的网页，运行不需要 Node.js；请在目标电脑安装 Python 3.12。
首次安装 Python 锁定依赖需要网络；之后本机演示无需网络。不能复制别的电脑的虚拟环境。

## 首次准备与启动

先打开终端并进入本包的 learn 目录（不是 learn/competition）：

Mac / Linux：
```bash
cd "解压后的交付包路径/learn"
python3.12 -m venv .competition-venv
.competition-venv/bin/python -m pip install -r competition/requirements-lock.txt
```

Windows：
```bat
cd /d "解压后的交付包路径\learn"
py -3.12 -m venv .competition-venv
.competition-venv\Scripts\python.exe -m pip install -r competition\requirements-lock.txt
```

准备后双击包根的“启动Mac.command”或“启动Windows.bat”。也可以在 learn 目录执行
`.competition-venv/bin/python -m uvicorn competition.api:app --host 127.0.0.1 --port 8091`。
打开 http://127.0.0.1:8091，保留服务终端，结束时按 Ctrl+C。
新运行档案保存在本包 output/4C/runtime/；原始项目数据库没有装入交付包。
presentation/ 已提供可编辑成品；附带的演示文稿及媒体制作脚本需另外配置其工具与运行时，
这些制作工具不属于比赛网页的启动依赖。

安装 fonts/ 中的思源黑体后，在实际 PowerPoint/WPS 上检查版式与视频。

作品为给定参考模型下的本机软件仿真；不是实飞、真实低温试验或景区合作证据。
实际运行备用录屏只证明软件操作；合成旁白练习视频不是学生真人答辩录像。
学生真人答辩录制、真实调研、需求核对、试用、身份登记和真人演练尚未完成。
2027 届规则和提交要求须在正式发布后复核。计划封版日为 2026-11-29。
"""
    (destination / "先读我.md").write_text(welcome, encoding="utf-8")
    mac_launcher = '''#!/usr/bin/env bash
set -euo pipefail
COMPETITION_PACKAGE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$COMPETITION_PACKAGE_DIR/learn"
unset PYTHONPATH PYTHONHOME COMPETITION_DB_PATH COMPETITION_CURVES_PATH
if [ ! -x .competition-venv/bin/python ]; then
  echo '请先按包根“先读我.md”在 learn 目录建立 Python 3.12 环境：'
  echo 'python3.12 -m venv .competition-venv'
  echo '.competition-venv/bin/python -m pip install -r competition/requirements-lock.txt'
  exit 1
fi
if ! .competition-venv/bin/python -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  echo '锁定依赖尚未安装；请在 learn 目录执行：'
  echo '.competition-venv/bin/python -m pip install -r competition/requirements-lock.txt'
  exit 1
fi
if [ ! -f competition/web/dist/index.html ]; then
  echo '交付网页缺失，请重新完整解压交付包。'
  exit 1
fi
COMPETITION_LAUNCH_PORT="${COMPETITION_PORT:-8091}"
echo "寒域智航比赛版：http://127.0.0.1:$COMPETITION_LAUNCH_PORT"
echo '保留此终端，Ctrl+C 停止服务。'
exec .competition-venv/bin/python -m uvicorn competition.api:app --host 127.0.0.1 --port "$COMPETITION_LAUNCH_PORT"
'''
    mac_path = destination / "启动Mac.command"
    mac_path.write_text(mac_launcher, encoding="utf-8")
    mac_path.chmod(0o755)
    windows_launcher = r'''@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0learn"
set "PYTHONPATH="
set "PYTHONHOME="
set "COMPETITION_DB_PATH="
set "COMPETITION_CURVES_PATH="
if not exist ".competition-venv\Scripts\python.exe" (
  echo 请先按包根“先读我.md”在 learn 目录建立 Python 3.12 环境：
  echo py -3.12 -m venv .competition-venv
  echo .competition-venv\Scripts\python.exe -m pip install -r competition\requirements-lock.txt
  pause
  exit /b 1
)
if not exist "competition\web\dist\index.html" (
  echo 交付网页缺失，请重新完整解压交付包。
  pause
  exit /b 1
)
if not defined COMPETITION_PORT set "COMPETITION_PORT=8091"
echo 寒域智航比赛版：http://127.0.0.1:%COMPETITION_PORT%
echo 保留此终端，Ctrl+C 停止服务。
".competition-venv\Scripts\python.exe" -m uvicorn competition.api:app --host 127.0.0.1 --port %COMPETITION_PORT%
pause
'''
    (destination / "启动Windows.bat").write_bytes(windows_launcher.replace("\n", "\r\n").encode("utf-8"))
    files = [{"path": p.relative_to(destination).as_posix(), "bytes": p.stat().st_size,
              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(destination.rglob("*")) if p.is_file()]
    manifest = {"package_version": "4c-local-sim-first-delivery-1.1", "prepared_date": "2026-10-03",
                "source_root": "learn/competition", "runtime_root": "output/4C/runtime",
                "python_environment_included": False, "web_build_included": True,
                "files": files, "file_count": len(files), "no_real_flight_claim": True}
    (destination / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.stage_only:
        print(json.dumps({"staging_directory": str(destination), "archive_created": False,
                          "files": len(files)}, ensure_ascii=False))
        return
    package = out / "寒域智航_4C_首版交付包.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for p in sorted(destination.rglob("*")):
            if p.is_file():
                archive.write(p, Path(destination.name) / p.relative_to(destination))
    print(json.dumps({"package": str(package), "bytes": package.stat().st_size,
                      "sha256": hashlib.sha256(package.read_bytes()).hexdigest(), "files": len(files)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
