@echo off
REM quake2midi launcher for Windows. Double-click to run the bridge.
REM Mirrors quake2midi.command: checks the venv and the MIDI ports, then
REM runs scripts\run.py in a console you can watch.

setlocal
set ROOT=%~dp0
cd /d "%ROOT%"

set VPY=%ROOT%.venv\Scripts\python.exe
if not exist "%VPY%" (
  echo  [fail] missing .venv. Run: python scripts\setup.py
  echo.
  pause
  exit /b 1
)

echo  Repo: %ROOT%
echo.

echo  MIDI destinations:
"%VPY%" "%ROOT%scripts\run.py" --list-ports
if errorlevel 1 (
  echo.
  echo  [fail] no MIDI destination. Install loopMIDI and create a port,
  echo         or see AGENTS.md under "Before you start".
  echo.
  pause
  exit /b 1
)
echo.

echo  Starting the bridge. Ctrl+C to stop.
echo  Status page: http://127.0.0.1:5446/
echo.

"%VPY%" "%ROOT%scripts\run.py" %*
set ERR=%ERRORLEVEL%

echo.
if not "%ERR%"=="0" echo  Bridge exited with code %ERR%. Scroll up.
pause
exit /b %ERR%