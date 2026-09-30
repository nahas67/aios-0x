@echo off
REM ============================================================
REM  AIOS-0X one-click starter (PROD mode, single window)
REM  Double-click this file to build the frontend once and serve
REM  everything from the Python backend alone.
REM
REM  Frontend build : npm run build in frontend\  (emits ui\dist)
REM  Server         : python -m aios serve --port 8787
REM  UI             : http://127.0.0.1:8787
REM ============================================================
setlocal
cd /d "%~dp0"

REM ---- Config (edit if needed) ----
set PORT=8787
REM Backend args. 'serve' always runs a replay first; a single symbol keeps
REM the wait to a few minutes. Empty = app default (BTC/USD,ETH/USD, slower).
set EXTRA_ARGS=--symbols SPY
if not defined SKIP_BOOT set SKIP_BOOT=0

echo === AIOS-0X starting (prod mode) ===

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 'python' not found on PATH. Install Python 3.11+ and retry.
  pause
  exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 'node' not found on PATH. Install Node 22+ and retry.
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 'npm' not found on PATH. Install Node 22+ and retry.
  pause
  exit /b 1
)

if exist ".venv\Scripts\activate.bat" (
  echo Using .venv...
  call ".venv\Scripts\activate.bat"
) else if exist ".venv-fresh\Scripts\activate.bat" (
  echo Using .venv-fresh...
  call ".venv-fresh\Scripts\activate.bat"
) else (
  echo No .venv found, using system Python.
)

if not exist ".env" (
  if exist ".env.example" (
    echo Creating .env from .env.example ...
    copy /y ".env.example" ".env" >nul
  ) else (
    echo [WARN] No .env and no .env.example found. Continuing in deterministic mode.
  )
)

if not "%SKIP_BOOT%"=="1" (
  echo Running boot gate...
  python -m aios boot
  if errorlevel 1 (
    echo [ERROR] Boot gate failed. Fix the error above and retry.
    pause
    exit /b 1
  )
) else (
  echo Skipping boot gate - SKIP_BOOT=1.
)

echo Building frontend (npm run build)...
pushd frontend
if not exist "node_modules" (
  echo Installing frontend dependencies - one time only...
  npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed.
    popd
    pause
    exit /b 1
  )
)
call npm run build
if errorlevel 1 (
  echo [ERROR] Frontend build failed.
  popd
  pause
  exit /b 1
)
popd

echo Starting command center on http://127.0.0.1:%PORT% ...
echo NOTE: the backend runs a replay first (a few minutes). 'Numeric
echo hallucination detected' lines are normal progress output, not errors.
start "AIOS Backend" cmd /k cd /d "%~dp0" ^& python -m aios serve --port %PORT% %EXTRA_ARGS%
set /a TRIES=0
:waitloop
curl.exe --fail --silent --max-time 2 http://127.0.0.1:%PORT%/api/v1/health >nul 2>nul
if not errorlevel 1 goto backendup
set /a TRIES+=1
if %TRIES% GEQ 90 (
  echo [WARN] Backend not up after ~15 minutes. Check the "AIOS Backend" window.
  goto skipbrowser
)
timeout /t 10 /nobreak >nul
goto waitloop
:backendup
echo Backend is up!
start "" "http://127.0.0.1:%PORT%"
:skipbrowser
echo.
echo Backend runs in the "AIOS Backend" window. Press Ctrl+C there to stop.
echo.
pause
