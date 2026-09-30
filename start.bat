@echo off
REM ============================================================
REM  AIOS-0X one-click starter (DEV mode)
REM  Double-click this file to run backend + frontend together.
REM
REM  Backend  : python -m aios serve --port 8787  (API + ui/dist)
REM  Frontend : npm run dev in frontend\           (Vite on :3000,
REM             proxies /api to the backend)
REM ============================================================
setlocal
cd /d "%~dp0"

REM ---- Config (edit if needed) ----
set PORT=8787
REM Backend args. 'serve' always runs a replay first; a single symbol keeps
REM the wait to a few minutes. Empty = app default (BTC/USD,ETH/USD, slower).
set EXTRA_ARGS=--symbols SPY
REM Set to 1 to skip the boot gate for a faster start:
REM   set SKIP_BOOT=1
if not defined SKIP_BOOT set SKIP_BOOT=0

echo === AIOS-0X starting (dev mode) ===

REM ---- Sanity checks ----
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

REM ---- Python env: prefer .venv, fall back to .venv-fresh, else system ----
if exist ".venv\Scripts\activate.bat" (
  echo Using .venv...
  call ".venv\Scripts\activate.bat"
) else if exist ".venv-fresh\Scripts\activate.bat" (
  echo Using .venv-fresh...
  call ".venv-fresh\Scripts\activate.bat"
) else (
  echo No .venv found, using system Python.
)

REM ---- .env bootstrap (never overwrite an existing .env) ----
if not exist ".env" (
  if exist ".env.example" (
    echo Creating .env from .env.example ...
    copy /y ".env.example" ".env" >nul
  ) else (
    echo [WARN] No .env and no .env.example found. Continuing in deterministic mode.
  )
)

REM ---- Optional boot gate: constitution hash + kernel inventory ----
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

REM ---- Frontend deps (only if node_modules is missing) ----
if not exist "frontend\node_modules" (
  echo Installing frontend dependencies - one time only...
  pushd frontend
  npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed.
    popd
    pause
    exit /b 1
  )
  popd
)

REM ---- Launch backend in its own window ----
echo Starting backend on http://127.0.0.1:%PORT% ...
start "AIOS Backend" cmd /k cd /d "%~dp0" ^& python -m aios serve --port %PORT% %EXTRA_ARGS%

REM ---- Launch frontend in its own window ----
echo Starting frontend on http://localhost:3000 ...
start "AIOS Frontend" cmd /k cd /d "%~dp0frontend" ^& npm run dev

REM ---- Wait for backend (replay takes minutes) then open browser ----
echo Waiting for backend to come up (replay takes a few minutes)...
echo NOTE: 'Numeric hallucination detected' lines in the Backend window
echo are normal progress output, not errors.
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
start "" "http://localhost:3000"
:skipbrowser

echo.
echo === AIOS-0X is starting ===
echo   Frontend (dev) : http://localhost:3000
echo   Backend        : http://127.0.0.1:%PORT%
echo   Backend health : http://127.0.0.1:%PORT%/api/v1/health
echo.
echo Two new windows opened (AIOS Backend + AIOS Frontend).
echo Press Ctrl+C inside them to stop. Closing them stops everything.
echo.
pause
