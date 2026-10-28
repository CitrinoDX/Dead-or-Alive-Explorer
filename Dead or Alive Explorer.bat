@echo off
rem Dead or Alive Explorer launcher.
rem  - Double-click: starts the viewer with the game folders remembered in config.json.
rem  - Drag a game folder or Xbox disc image onto this file: adds it (and remembers it).
rem  - Extra options pass through, e.g.  "Dead or Alive Explorer.bat" --port 9000
setlocal
cd /d "%~dp0"
title Dead or Alive Explorer

rem Already running? Just open it instead of starting a second copy.
if "%~1"=="" (
  curl -s -o nul -m 2 http://127.0.0.1:8765/api/games >nul 2>&1 && (
    echo The viewer is already running - opening it in your browser.
    start "" http://127.0.0.1:8765/
    exit /b 0
  )
)

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python 3 was not found. Install it from https://www.python.org/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

%PY% -c "import numpy" >nul 2>&1 || (
  echo numpy is not installed. Install it with:
  echo     %PY% -m pip install numpy
  pause
  exit /b 1
)

echo Starting Dead or Alive Explorer - close this window or press Ctrl+C to stop it.
%PY% run_explorer.py %*
if errorlevel 1 pause
