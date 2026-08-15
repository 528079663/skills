@echo off
REM Stop the renshe-writer Web UI (port 8003)
setlocal
cd /d "%~dp0"
set "PY=%USERPROFILE%\.workbuddy\binaries\python/envs/base/Scripts/python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0scripts\app.py" stop
pause
