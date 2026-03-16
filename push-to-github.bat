@echo off
REM ============================================================
REM Fintech — Push to GitHub
REM Double-click to stage, commit with timestamp, and push
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo  ============================================
echo   Fintech ^|^| Push to GitHub
echo  ============================================
echo.

REM Check we're in a git repo
git rev-parse --git-dir >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Not a git repository.
    echo  Run: git init ^&^& git remote add origin ^<url^>
    pause
    exit /b 1
)

REM Show current status
echo  [STATUS] Current branch:
git branch --show-current
echo.
echo  [STATUS] Changed files:
git status --short
echo.

REM Ask for commit message
set /p MSG="  Enter commit message (or press Enter for auto): "
if "!MSG!"=="" (
    for /f "tokens=*" %%i in ('powershell -command "Get-Date -Format \"yyyy-MM-dd HH:mm\""') do set DT=%%i
    set MSG=Update: !DT!
)

echo.
echo  [GIT] Staging all changes...
git add -A

echo  [GIT] Committing: "!MSG!"
git commit -m "!MSG!"

if %errorlevel% neq 0 (
    echo  [WARN] Nothing to commit or commit failed.
    pause
    exit /b 0
)

echo  [GIT] Pushing to origin...
git push origin HEAD

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Push failed. Try:
    echo    git push --set-upstream origin main
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   [OK] Successfully pushed to GitHub!
echo  ============================================
echo.

REM Show latest commits
echo  [LOG] Latest commits:
git log --oneline -5
echo.
pause
