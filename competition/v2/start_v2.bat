@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0\..\.."
if exist ".competition-venv\Scripts\python.exe" (
  ".competition-venv\Scripts\python.exe" "competition\v2\launch.py" %*
) else (
  py -3.12 "competition\v2\launch.py" %*
)
if errorlevel 1 (
  echo.
  echo 启动未完成。首次使用请安装 Python 3.12 和 Python Launcher。
  echo 请保留上面的错误信息。
  pause
  exit /b 1
)
