@echo off
REM ============================================================
REM renshe-writer Web UI launcher (port 8003, runs on YOUR PC)
REM Double-click to start. To stop: double-click stop_service.bat
REM Deps: shared base venv (deps already installed there)
REM This script only RUNS on your machine; never in sandbox.
REM ============================================================
setlocal
cd /d "%~dp0"

REM Use the shared base venv python; fall back to PATH python
set "PY=%USERPROFILE%\.workbuddy\binaries\python/envs/base/Scripts/python.exe"
if not exist "%PY%" set "PY=python"

echo [renshe-writer] Starting Web UI at http://localhost:8003 ...
"%PY%" "%~dp0scripts\app.py" start
echo.
echo Done. Open http://localhost:8003 in your browser.
echo You can close this window; the service keeps running in the background.
pause
