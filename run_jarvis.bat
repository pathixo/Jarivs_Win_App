@echo off
title Jarvis - Autonomous AI Assistant

:: Enable ANSI escape codes on Windows 10+
for /f "tokens=4-5 delims=. " %%i in ('ver') do set VERSION=%%i.%%j
if "%version%" == "10.0" (
    reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1
)

echo.
echo  [94m══════════════════════════════════════════════════[0m
echo  [96m[1m   JARVIS - Autonomous AI Assistant[0m
echo  [94m══════════════════════════════════════════════════[0m
echo.

:: ─── Locate project directory ──────────────────────
cd /d "%~dp0"

:: ─── Check for Python ──────────────────────────────
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [91m[ERROR][0m Python not found in PATH.
    echo  Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: ─── Check for .env ────────────────────────────────
if not exist ".env" (
    echo  [93m[WARN][0m No .env file found.
    echo  Copying .env.example to .env ...
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo  [94m[INFO][0m .env created. Edit it with your API keys.
        start notepad ".env"
        pause
        exit /b 0
    ) else (
        echo  [93m[WARN][0m No .env.example found. Continuing with defaults...
    )
)

:: ─── Activate venv if present ──────────────────────
if exist ".venv\Scripts\activate.bat" (
    echo  [94m[*][0m Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo  [93m[WARN][0m No .venv found. Running with system Python.
    echo  [90mTip: python -m venv .venv ^& .venv\Scripts\activate ^& pip install -r Jarvis\requirements.txt[0m
)

:: ─── Check dependencies ───────────────────────────
python -c "import PyQt6" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [94m[*][0m Installing dependencies...
    pip install -r Jarvis\requirements.txt
    if %errorlevel% neq 0 (
        echo  [91m[ERROR][0m Dependency installation failed.
        pause
        exit /b 1
    )
)

:: ─── Install colorama if missing ───────────────────
python -c "import colorama" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [94m[*][0m Installing colorama for colored output...
    pip install colorama >nul 2>&1
)

:: ─── Launch Jarvis ─────────────────────────────────
echo.
echo  [92m[*] Starting Jarvis...[0m
echo  [90m──────────────────────────────────────────────────[0m
echo.
python -m Jarvis.main

:: ─── Exit ──────────────────────────────────────────
if %errorlevel% neq 0 (
    echo.
    echo  [91m[ERROR][0m Jarvis exited with error code %errorlevel%
    echo  [90mCheck Jarvis\logs\crash.log for details.[0m
)
echo.
pause
