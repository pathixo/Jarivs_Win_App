@echo off
setlocal enabledelayedexpansion

REM =====================================================================
REM   JARVIS AI - SYSTEM INTEGRATION BOOTSTRAPPER (Developer-Friendly)
REM =====================================================================
echo ============================================================
echo   JARVIS AI - SYSTEM INTEGRATION BOOTSTRAPPER
echo ============================================================
echo.

REM Ensure we are running from the script directory
cd /d "%~dp0"

set "LOGFILE=%~dp0install_jarvis_bootstrap.log"
echo [%date% %time%] Bootstrap started. > "%LOGFILE%"

REM ---------------------------------------------------------------------
REM 1) Check for Python presence, version (>= 3.10) and 64-bit
REM ---------------------------------------------------------------------
echo [1/4] Checking Python environment...
python --version >nul 2>>"%LOGFILE%"
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Please install 64-bit Python 3.10 or higher from python.org.
    echo [ERROR] Missing Python runtime. >> "%LOGFILE%"
    pause
    exit /b 1
)

REM Check minimum Python version (3.10+)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>>"%LOGFILE%"
if %errorlevel% neq 0 (
    echo [ERROR] Detected Python is too old. Jarvis requires Python 3.10 or newer.
    echo [ERROR] Python version check failed. >> "%LOGFILE%"
    pause
    exit /b 1
)

REM Check 64-bit architecture
python -c "import struct; raise SystemExit(0 if struct.calcsize('P') * 8 == 64 else 1)" >nul 2>>"%LOGFILE%"
if %errorlevel% neq 0 (
    echo [ERROR] 32-bit Python detected. Jarvis requires a 64-bit Python installation.
    echo [ERROR] Python architecture check failed. >> "%LOGFILE%"
    pause
    exit /b 1
)

REM ---------------------------------------------------------------------
REM 2) Ensure GUI prerequisites (PyQt6, Pillow) are available
REM    These are installed into the active Python environment. The main
REM    application will later create its own isolated environment.
REM ---------------------------------------------------------------------
echo [2/4] Verifying GUI prerequisites (PyQt6, Pillow)...
echo Verifying PyQt6 and Pillow... >> "%LOGFILE%"

python -c "import PyQt6, PIL" >nul 2>>"%LOGFILE%"
if %errorlevel% neq 0 (
    echo [INFO] Installing GUI prerequisites into the current Python...
    python -m pip install --upgrade pip >>"%LOGFILE%" 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to upgrade pip. See %LOGFILE% for details.
        pause
        exit /b 1
    )

    python -m pip install PyQt6 Pillow >>"%LOGFILE%" 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install PyQt6/Pillow. See %LOGFILE% for details.
        pause
        exit /b 1
    )
)

REM ---------------------------------------------------------------------
REM 3) Sanity check: installer script presence
REM ---------------------------------------------------------------------
if not exist "install_jarvis.py" (
    echo [ERROR] Cannot find install_jarvis.py next to this bootstrapper.
    echo         Make sure you extracted the full Jarvis package.
    echo [ERROR] Missing install_jarvis.py. >> "%LOGFILE%"
    pause
    exit /b 1
)

REM ---------------------------------------------------------------------
REM 4) Launch Jarvis System Integration Wizard (GUI preferred)
REM ---------------------------------------------------------------------
echo [3/4] Launching Jarvis System Integration Wizard...
echo Launching install_jarvis.py via pythonw... >> "%LOGFILE%"

pythonw.exe install_jarvis.py >>"%LOGFILE%" 2>&1
if %errorlevel% neq 0 (
    echo [WARN] GUI launch failed or pythonw.exe is unavailable.
    echo [WARN] Falling back to console mode... >> "%LOGFILE%"
    echo [3/4] Launching console-based installer...
    python install_jarvis.py >>"%LOGFILE%" 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to launch Jarvis installer. See %LOGFILE% for details.
        pause
        exit /b 1
    )
)

echo.
echo [4/4] Integration wizard launched successfully.
echo A detailed bootstrap log is available at:
echo   %LOGFILE%
echo.
echo You can close this window once the wizard is visible.
timeout /t 5 >nul
exit /b 0
