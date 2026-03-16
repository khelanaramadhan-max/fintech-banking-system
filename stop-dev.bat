@echo off
REM ============================================================
REM Fintech — Stop Development Server (Windows)
REM Kills uvicorn and any python processes on port 8000
REM ============================================================

echo.
echo  ============================================
echo   Fintech ^|^| Stop Development Server
echo  ============================================
echo.

REM ── Kill uvicorn processes ────────────────────────────────
echo  [INFO] Looking for uvicorn processes...
taskkill /F /IM uvicorn.exe /T >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] Killed uvicorn.exe
) else (
    echo  [INFO] No uvicorn.exe found
)

REM ── Kill Python processes using port 8000 ─────────────────
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo  [INFO] Killing PID %%a on port 8000...
    taskkill /F /PID %%a >nul 2>&1
    if !errorlevel! equ 0 (
        echo  [OK] Killed PID %%a
    )
)

REM ── Kill Docker containers (optional) ────────────────────
docker ps -q --filter "name=fintech" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [INFO] Stopping Docker containers...
    docker compose stop >nul 2>&1
    echo  [OK] Docker containers stopped
)

echo.
echo  [OK] All Fintech processes stopped.
echo.
pause
