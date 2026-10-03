@echo off
setlocal
cd /d "%~dp0.."
if exist ".competition-venv\Scripts\python.exe" (
  ".competition-venv\Scripts\python.exe" -m uvicorn competition.api:app --host 127.0.0.1 --port 8091
) else (
  echo First setup: py -3.11 -m venv .competition-venv
  echo .competition-venv\Scripts\python.exe -m pip install -r competition\requirements-lock.txt
  pause
)
