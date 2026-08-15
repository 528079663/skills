@echo off
REM Install renshe-writer deps into the shared base venv (run once)
setlocal
cd /d "%~dp0"
set "PY=%USERPROFILE%\.workbuddy\binaries\python/envs/base/Scripts/python.exe"
if not exist "%PY%" (
    echo [ERROR] base venv python not found: %PY%
    pause
    exit /b 1
)
echo [renshe-writer] Installing dependencies from requirements.txt into base venv ...
"%PY%" -m pip install -r "%~dp0requirements.txt"
echo Done. Now double-click start_service.bat to launch.
pause
