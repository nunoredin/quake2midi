@echo off
REM quake2midi launcher for Windows. Double-click to run the bridge.
REM Checks the venv, then runs scripts\run.py in a console you can watch.

setlocal
set ROOT=%~dp0
cd /d "%ROOT%"

set VPY=%ROOT%.venv\Scripts\python.exe
if not exist "%VPY%" (
  echo  [fail] missing .venv. Run: python scripts\setup.py
  pause
  exit /b 1
)

"%VPY%" "%ROOT%scripts\run.py"
echo.
pause