@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Jarvis - Autonomous AI Assistant

:: ─── Locate project directory ──────────────────────
cd /d "%~dp0"

:: ─── Check for Virtual Environment ─────────────────
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

:: ─── Check for Python ──────────────────────────────
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

:: ─── Launch Jarvis ─────────────────────────────────
:: We use pythonw.exe to avoid the black console window for the GUI.
:: If there's an error, it will be logged to Jarvis\logs\crash.log.

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m Jarvis.main
) else (
    start "" pythonw -m Jarvis.main
)

exit /b 0
