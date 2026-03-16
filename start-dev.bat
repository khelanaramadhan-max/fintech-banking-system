@echo off
REM ============================================================
REM Fintech — Start Development Server (Windows)
REM Starts the FastAPI backend and opens the frontend in browser
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo  ============================================
echo   Fintech ^|^| Development Server
echo  ============================================
echo.

REM ── Check Python ─────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

REM ── Check .env ────────────────────────────────────────────
if not exist ".env" (
    echo  [WARN] .env file not found. Copying from .env.example...
    if exist ".env.example" (
        copy .env.example .env >nul
        echo  [OK] Created .env — please edit JWT_SECRET and ADMIN_PASSWORD
    ) else (
        echo  [ERROR] .env.example not found. Cannot start.
        pause
        exit /b 1
    )
)

REM ── Check dependencies ────────────────────────────────────
if not exist "backend\venv" (
    echo  [SETUP] Creating virtual environment...
    python -m venv backend\venv
    echo  [SETUP] Installing dependencies...
    backend\venv\Scripts\pip install -r backend\requirements.txt -q
    echo  [OK] Dependencies installed
)

REM ── Load env vars ─────────────────────────────────────────
for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    if not "%%a"=="" if not "%%a:~0,1%"=="#" (
        set "%%a=%%b"
    )
)

set PORT=8000
if defined APP_PORT set PORT=!APP_PORT!

echo  [INFO] Starting backend on http://localhost:!PORT!
echo  [INFO] Swagger UI: http://localhost:!PORT!/docs
echo  [INFO] Press Ctrl+C to stop
echo.

REM ── Open browser after 2 second delay ────────────────────
start "" cmd /c "timeout /t 2 >nul && start http://localhost:!PORT!/docs && start frontend/fintech.html"

REM ── Start backend ─────────────────────────────────────────
cd backend
..\backend\venv\Scripts\uvicorn main:app --reload --port !PORT! --host 0.0.0.0 --log-level info

echo.
echo  [INFO] Server stopped.
pause
