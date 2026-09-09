#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LSTM_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AI_DIR="$LSTM_ROOT/learn"
if [[ -f "$LSTM_ROOT/Phase3/inference_api.py" ]]; then
  AI_DIR="$LSTM_ROOT"
fi
PYTHON_BIN="$AI_DIR/.venv/bin/python"
REPLAY_SCRIPT="$AI_DIR/Phase4/replay_airsim.py"
DEFAULT_SOURCE="${AIRSIM_DATA_SOURCE:-$SCRIPT_DIR/data/collected_phase2_data.zip}"
DEFAULT_FLIGHT="${AIRSIM_FLIGHT_ID:-flight_036}"
DEFAULT_SPEED="${DEMO_REPLAY_SPEED:-2}"
BACKEND_URL="${DEMO_BACKEND_URL:-http://127.0.0.1:8080}"
COUNTDOWN_SECONDS="${DEMO_COUNTDOWN_SECONDS:-3}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "未找到Python环境，请先运行：$SCRIPT_DIR/start_demo.sh" >&2
  exit 1
fi

if [[ "${1:-}" == "--list" ]]; then
  DATA_SOURCE="${2:-$DEFAULT_SOURCE}"
  if [[ ! -e "$DATA_SOURCE" ]]; then
    echo "AirSim数据源不存在：$DATA_SOURCE" >&2
    exit 1
  fi
  DATA_SOURCE="$(cd "$(dirname "$DATA_SOURCE")" && pwd)/$(basename "$DATA_SOURCE")"
  (cd "$AI_DIR" && "$PYTHON_BIN" "$REPLAY_SCRIPT" "$DATA_SOURCE" --list)
  exit 0
fi

DATA_SOURCE="${1:-$DEFAULT_SOURCE}"
FLIGHT_ID="${2:-$DEFAULT_FLIGHT}"
REPLAY_SPEED="${3:-$DEFAULT_SPEED}"

if [[ ! -e "$DATA_SOURCE" ]]; then
  echo "AirSim数据源不存在：$DATA_SOURCE" >&2
  echo "请把最新数据包放到 ${DEFAULT_SOURCE}，或把数据路径作为第一个参数传入。" >&2
  exit 1
fi
DATA_SOURCE="$(cd "$(dirname "$DATA_SOURCE")" && pwd)/$(basename "$DATA_SOURCE")"

VALIDATE_COMMAND=(
  "$PYTHON_BIN" "$REPLAY_SCRIPT" "$DATA_SOURCE"
  --flight-id "$FLIGHT_ID" --speed "$REPLAY_SPEED"
  --backend-url "$BACKEND_URL"
)
REPLAY_COMMAND=(
  "$PYTHON_BIN" "$REPLAY_SCRIPT" "$DATA_SOURCE"
  --flight-id "$FLIGHT_ID" --speed "$REPLAY_SPEED"
  --backend-url "$BACKEND_URL"
)
if [[ $# -gt 3 ]]; then
  VALIDATE_COMMAND+=("${@:4}")
  REPLAY_COMMAND+=("${@:4}")
fi
VALIDATE_COMMAND+=(--validate-only)

if ! curl -fsS "$BACKEND_URL/api/dashboard/overview" >/dev/null 2>&1; then
  echo "演示后台未启动，请先运行：$SCRIPT_DIR/start_demo.sh" >&2
  exit 1
fi

echo "[1/3] 校验数据源和架次……"
(cd "$AI_DIR" && "${VALIDATE_COMMAND[@]}")

# Creating a new run broadcasts run-started, which clears only the live view.
# A resumed run must not reset the view: identical retries deliberately do not broadcast.
echo "[2/3] 确认后台支持持久档案；已有记录全部保留……"
if ! ARCHIVE_RESPONSE="$(curl -fsS "$BACKEND_URL/api/runs?size=1")"; then
  echo "后台尚未支持持久实验档案，请先重启新版后台；未执行重置。" >&2
  exit 1
fi
printf '%s' "$ARCHIVE_RESPONSE" | "$PYTHON_BIN" -c '
import json, sys
response = json.load(sys.stdin)
if response.get("code") != 200 or not isinstance(response.get("data", {}).get("records"), list):
    raise SystemExit("实验档案接口校验失败，未执行回放")
print("新回放将创建独立实验；使用 --run-id 时继续原实验并跳过重复记录。")
'

if [[ "$COUNTDOWN_SECONDS" =~ ^[0-9]+$ ]] && [[ "$COUNTDOWN_SECONDS" -gt 0 ]]; then
  echo "浏览器准备时间：${COUNTDOWN_SECONDS} 秒，请切换到监控看板……"
  for ((countdown = COUNTDOWN_SECONDS; countdown >= 1; countdown--)); do
    echo "  ${countdown}……"
    sleep 1
  done
fi

echo "[3/3] 开始回放所选AirSim架次……"
(cd "$AI_DIR" && "${REPLAY_COMMAND[@]}")
