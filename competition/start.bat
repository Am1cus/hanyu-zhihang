@echo off
setlocal
cd /d "%~dp0.."
if not defined COMPETITION_PORT set "COMPETITION_PORT=8091"
if exist ".competition-venv\Scripts\python.exe" (
  ".competition-venv\Scripts\python.exe" -m uvicorn competition.api:app --host 127.0.0.1 --port %COMPETITION_PORT%
) else (
  echo First setup: py -3.12 -m venv .competition-venv
  echo .competition-venv\Scripts\python.exe -m pip install -r competition\requirements-lock.txt
  pause
)
