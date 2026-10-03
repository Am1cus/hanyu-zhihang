#!/usr/bin/env bash
set -euo pipefail
COMPETITION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPETITION_PARENT="$(dirname "$COMPETITION_DIR")"
COMPETITION_PYTHON=""
for candidate in "$COMPETITION_PARENT/.competition-venv/bin/python" "$COMPETITION_PARENT/.venv/bin/python" python3.12 python3.11 python3.10 python3; do
  if "$candidate" -c 'import sys; assert sys.version_info >= (3,10); import fastapi, uvicorn' >/dev/null 2>&1; then
    COMPETITION_PYTHON="$candidate"
    break
  fi
done
if [ -z "$COMPETITION_PYTHON" ]; then
  echo '需要 Python 3.10 或以上及 FastAPI/uvicorn。首次准备：'
  echo 'python3.11 -m venv .competition-venv'
  echo '.competition-venv/bin/python -m pip install -r competition/requirements-lock.txt'
  exit 1
fi
if [ ! -f "$COMPETITION_DIR/web/dist/index.html" ]; then
  echo '网页尚未构建。请在 competition/web 执行 npm ci 和 npm run build。'
  exit 1
fi
cd "$COMPETITION_PARENT"
echo '寒域智航比赛版：http://127.0.0.1:8091'
echo '仅本机运行。保留此终端；Ctrl+C 停止服务，不删除运行档案。'
exec "$COMPETITION_PYTHON" -m uvicorn competition.api:app --host 127.0.0.1 --port 8091
