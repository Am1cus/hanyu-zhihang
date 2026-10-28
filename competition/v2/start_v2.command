#!/bin/zsh
hyzh_v2_directory="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$hyzh_v2_directory/../.."
if [[ -x .competition-venv/bin/python ]]; then
  hyzh_python="$PWD/.competition-venv/bin/python"
elif command -v python3.12 >/dev/null 2>&1; then
  hyzh_python="$(command -v python3.12)"
elif command -v python3 >/dev/null 2>&1; then
  hyzh_python="$(command -v python3)"
else
  printf '请先安装 Python 3.12，再双击启动。\n'
  read -r '?按回车关闭窗口…'
  exit 1
fi
"$hyzh_python" competition/v2/launch.py "$@"
hyzh_result=$?
if [[ $hyzh_result -ne 0 && -t 0 ]]; then
  read -r '?启动未完成。请保留以上错误信息，按回车关闭窗口…'
fi
exit $hyzh_result
