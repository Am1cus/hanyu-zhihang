#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LSTM_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$LSTM_ROOT/Phase3/inference_api.py" ]]; then
  AI_DIR="$LSTM_ROOT"
  PROJECT_ROOT="$LSTM_ROOT/platform"
else
  AI_DIR="$LSTM_ROOT/learn"
  PROJECT_ROOT="$(cd "$LSTM_ROOT/../project" && pwd)"
fi
BACKEND_DIR="$PROJECT_ROOT/cold-region-aviation-backend"
FRONTEND_DIR="$PROJECT_ROOT/cold-region-aviation-frontend"
RUNTIME_DIR="$LSTM_ROOT/.demo-runtime"
LOG_DIR="$RUNTIME_DIR/logs"
TOOLS_DIR="$RUNTIME_DIR/tools"
PID_FILE="$RUNTIME_DIR/demo.pids"
OPEN_BROWSER=1

if [[ "${1:-}" == "--no-open" ]]; then
  OPEN_BROWSER=0
elif [[ $# -gt 0 ]]; then
  echo "用法：$0 [--no-open]" >&2
  exit 2
fi

mkdir -p "$LOG_DIR" "$TOOLS_DIR" "$RUNTIME_DIR/data"
export DEMO_DATABASE_PATH="${DEMO_DATABASE_PATH:-$RUNTIME_DIR/data/cold-aviation}"

for required_command in curl java npm; do
  if ! command -v "$required_command" >/dev/null 2>&1; then
    echo "缺少命令：$required_command" >&2
    exit 1
  fi
done

for required_dir in "$AI_DIR" "$BACKEND_DIR" "$FRONTEND_DIR"; do
  if [[ ! -d "$required_dir" ]]; then
    echo "项目目录不存在：$required_dir" >&2
    exit 1
  fi
done

if command -v lsof >/dev/null 2>&1; then
  for demo_port in 5173 8000 8080; do
    if lsof -nP -iTCP:"$demo_port" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "端口 $demo_port 已被占用，请先关闭对应程序后重试。" >&2
      exit 1
    fi
  done
fi

PYTHON_BIN="$AI_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "未找到Python虚拟环境，也未安装python3。" >&2
    exit 1
  fi
  echo "首次运行：正在创建Python虚拟环境并安装依赖……"
  python3 -m venv "$AI_DIR/.venv"
  "$AI_DIR/.venv/bin/python" -m pip install -r "$AI_DIR/requirements.txt"
fi

if ! "$PYTHON_BIN" -c "import uvicorn, torch, fastapi" >/dev/null 2>&1; then
  echo "Python依赖不完整，正在安装……"
  "$PYTHON_BIN" -m pip install -r "$AI_DIR/requirements.txt"
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "首次运行：正在安装前端依赖……"
  (cd "$FRONTEND_DIR" && npm install)
fi

MAVEN_BIN=""
if command -v mvn >/dev/null 2>&1; then
  MAVEN_BIN="$(command -v mvn)"
else
  MAVEN_VERSION="3.9.16"
  MAVEN_HOME_DIR="$TOOLS_DIR/apache-maven-$MAVEN_VERSION"
  MAVEN_BIN="$MAVEN_HOME_DIR/bin/mvn"
  if [[ ! -x "$MAVEN_BIN" ]]; then
    MAVEN_ARCHIVE="$TOOLS_DIR/apache-maven-$MAVEN_VERSION-bin.tar.gz"
    MAVEN_CHECKSUM="$MAVEN_ARCHIVE.sha512"
    MAVEN_BASE_URL="https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/$MAVEN_VERSION"
    echo "本机未安装Maven，正在下载演示专用 Maven ${MAVEN_VERSION}……"
    curl -fsSL "$MAVEN_BASE_URL/apache-maven-$MAVEN_VERSION-bin.tar.gz" -o "$MAVEN_ARCHIVE"
    curl -fsSL "$MAVEN_BASE_URL/apache-maven-$MAVEN_VERSION-bin.tar.gz.sha512" -o "$MAVEN_CHECKSUM"
    expected_checksum="$(tr -d '[:space:]' < "$MAVEN_CHECKSUM")"
    actual_checksum="$(shasum -a 512 "$MAVEN_ARCHIVE" | awk '{print $1}')"
    if [[ "$expected_checksum" != "$actual_checksum" ]]; then
      echo "Maven安装包校验失败，已停止启动。" >&2
      exit 1
    fi
    tar -xzf "$MAVEN_ARCHIVE" -C "$TOOLS_DIR"
  fi
fi

AI_LOG="$LOG_DIR/ai.log"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

AI_PID=""
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  trap - EXIT INT TERM
  echo
  echo "正在关闭演示服务……"
  for demo_pid in "$FRONTEND_PID" "$BACKEND_PID" "$AI_PID"; do
    if [[ -n "$demo_pid" ]] && kill -0 "$demo_pid" >/dev/null 2>&1; then
      pkill -TERM -P "$demo_pid" >/dev/null 2>&1 || true
      kill -TERM "$demo_pid" >/dev/null 2>&1 || true
    fi
  done
  sleep 1
  for demo_pid in "$FRONTEND_PID" "$BACKEND_PID" "$AI_PID"; do
    if [[ -n "$demo_pid" ]] && kill -0 "$demo_pid" >/dev/null 2>&1; then
      pkill -KILL -P "$demo_pid" >/dev/null 2>&1 || true
      kill -KILL "$demo_pid" >/dev/null 2>&1 || true
    fi
  done
  rm -f "$PID_FILE"
  echo "演示服务已关闭。"
}

trap cleanup EXIT
trap 'exit 130' INT TERM

echo "[1/3] 启动AI推理服务……"
(cd "$AI_DIR" && "$PYTHON_BIN" -m uvicorn Phase3.inference_api:app --host 127.0.0.1 --port 8000) >"$AI_LOG" 2>&1 &
AI_PID=$!

echo "[2/3] 启动Spring Boot演示后台……"
(cd "$BACKEND_DIR" && "$MAVEN_BIN" spring-boot:run -Dspring-boot.run.profiles=demo) >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

echo "[3/3] 启动Vue看板……"
(cd "$FRONTEND_DIR" && npm run dev -- --host 127.0.0.1) >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

printf 'AI_PID=%s\nBACKEND_PID=%s\nFRONTEND_PID=%s\n' "$AI_PID" "$BACKEND_PID" "$FRONTEND_PID" > "$PID_FILE"

wait_for_url() {
  local service_name="$1"
  local service_url="$2"
  local service_pid="$3"
  local service_log="$4"
  local attempts=0

  until curl -fsS "$service_url" >/dev/null 2>&1; do
    if ! kill -0 "$service_pid" >/dev/null 2>&1; then
      echo "$service_name 启动失败，日志如下：" >&2
      tail -n 40 "$service_log" >&2 || true
      exit 1
    fi
    attempts=$((attempts + 1))
    if [[ $attempts -ge 120 ]]; then
      echo "$service_name 在120秒内未就绪，日志如下：" >&2
      tail -n 40 "$service_log" >&2 || true
      exit 1
    fi
    sleep 1
  done
  echo "✓ $service_name 已就绪"
}

wait_for_url "AI推理服务" "http://127.0.0.1:8000/health" "$AI_PID" "$AI_LOG"
wait_for_url "Spring Boot后台" "http://127.0.0.1:8080/api/dashboard/overview" "$BACKEND_PID" "$BACKEND_LOG"
wait_for_url "Vue看板" "http://127.0.0.1:5173/" "$FRONTEND_PID" "$FRONTEND_LOG"

echo
echo "=============================================="
echo "  寒域智航视频演示环境已启动"
echo "  看板：http://127.0.0.1:5173/"
echo "  日志：$LOG_DIR"
echo "  按 Ctrl+C 可一次关闭全部服务"
echo "=============================================="

if [[ $OPEN_BROWSER -eq 1 ]] && command -v open >/dev/null 2>&1; then
  open "http://127.0.0.1:5173/"
fi

while true; do
  for service_pair in "AI:$AI_PID" "后台:$BACKEND_PID" "前端:$FRONTEND_PID"; do
    service_name="${service_pair%%:*}"
    service_pid="${service_pair##*:}"
    if ! kill -0 "$service_pid" >/dev/null 2>&1; then
      echo "$service_name 服务意外退出，请查看 ${LOG_DIR}。" >&2
      exit 1
    fi
  done
  sleep 1
done
