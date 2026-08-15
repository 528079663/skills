@echo off
cd /d "%~dp0"
"%USERPROFILE%\.workbuddy\binaries\python/envs/base/Scripts/python.exe" serve.py --open
pause
