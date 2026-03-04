@echo off
chcp 65001 >nul 2>&1
title Jarvis - Autonomous AI Assistant

echo.
echo  ======================================================
echo     JARVIS - Autonomous AI Assistant
echo  ======================================================
echo.

:: ─── Locate project directory ──────────────────────
cd /d "%~dp0"

:: ─── Parse command-line arguments ──────────────────
set "SKIP_DEPS=0"
set "FORCE_INSTALL=0"
set "VERBOSE=0"
set "HEADLESS=0"
set "CUSTOM_ENV="
set "PYTHON_CMD=python"

:parse_args
if "%~1"=="" goto end_parse
if /i "%~1"=="--skip-deps"     ( set "SKIP_DEPS=1"     & shift & goto parse_args )
if /i "%~1"=="--force-install" ( set "FORCE_INSTALL=1"  & shift & goto parse_args )
if /i "%~1"=="--verbose"       ( set "VERBOSE=1"        & shift & goto parse_args )
if /i "%~1"=="--headless"      ( set "HEADLESS=1"       & shift & goto parse_args )
if /i "%~1"=="--env"           ( set "CUSTOM_ENV=%~2"   & shift & shift & goto parse_args )
if /i "%~1"=="--python"        ( set "PYTHON_CMD=%~2"   & shift & shift & goto parse_args )
if /i "%~1"=="--help" goto show_help
if /i "%~1"=="-h"     goto show_help
echo  [WARN] Unknown argument: %~1
shift
goto parse_args 
:end_parse 

:: ─── Timestamp & session info ──────────────────────
for /f "tokens=1-4 delims=/ " %%a in ('date /t') do set "TODAY=%%a-%%b-%%c"
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set "NOW=%%a:%%b"
echo  [*] Session started: %TODAY% %NOW%
echo.

:: ─── Ensure logs directory exists ──────────────────
if not exist "Jarvis\logs" (
    echo  [*] Creating logs directory...
    mkdir "Jarvis\logs"
)

:: ─── Set log file path ────────────────────────────
set "SESSION_LOG=Jarvis\logs\session_%TODAY: =_%_%NOW::=%.log"

:: ─── Check for Python ──────────────────────────────
where %PYTHON_CMD% >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found in PATH.
    echo  Please install Python 3.10+ from https://python.org
    echo  Or specify a custom Python path with --python "C:\path\to\python.exe"
    pause
    exit /b 1
)

:: ─── Validate Python version ──────────────────────
for /f "tokens=*" %%v in ('%PYTHON_CMD% -c "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")"') do set "PYVER=%%v"
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set "PY_MAJOR=%%a"
    set "PY_MINOR=%%b"
)

if %PY_MAJOR% lss 3 (
    echo  [ERROR] Python 3.10+ required. Found Python %PYVER%.
    pause
    exit /b 1
)
if %PY_MAJOR% equ 3 if %PY_MINOR% lss 10 (
    echo  [ERROR] Python 3.10+ required. Found Python %PYVER%.
    pause
    exit /b 1
)
echo  [OK] Python %PYVER% detected.

:: ─── Check for pip ─────────────────────────────────
%PYTHON_CMD% -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] pip not found. Installing pip...
    %PYTHON_CMD% -m ensurepip --upgrade >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [ERROR] Could not install pip. Please install it manually.
        pause
        exit /b 1
    )
)

:: ─── Check for .env ────────────────────────────────
if defined CUSTOM_ENV (
    if exist "%CUSTOM_ENV%" (
        echo  [*] Using custom env file: %CUSTOM_ENV%
        copy /y "%CUSTOM_ENV%" ".env" >nul
    ) else (
        echo  [ERROR] Custom env file not found: %CUSTOM_ENV%
        pause
        exit /b 1
    )
)

if not exist ".env" (
    echo  [WARN] No .env file found.
    echo  Copying .env.example to .env ...
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo  [INFO] .env created. Edit it with your API keys.
        start notepad ".env"
        pause
        exit /b 0
    ) else (
        echo  [WARN] No .env.example found. Continuing with defaults...
    )
)

:: ─── Validate .env has required keys ──────────────
if exist ".env" (
    findstr /i "API_KEY" ".env" >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [WARN] .env file may be missing API_KEY entries.
        echo  Please verify your .env file contains the required keys.
    )
)

:: ─── Create venv if not present ───────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo  [WARN] No .venv found.

    set /p "CREATE_VENV=  Create virtual environment now? (Y/N): "
    if /i "!CREATE_VENV!"=="Y" (
        echo  [*] Creating virtual environment...
        %PYTHON_CMD% -m venv .venv
        if %errorlevel% neq 0 (
            echo  [ERROR] Failed to create virtual environment.
            echo  Running with system Python instead.
        ) else (
            echo  [OK] Virtual environment created.
            set "FORCE_INSTALL=1"
        )
    ) else (
        echo  [INFO] Running with system Python.
        echo  Tip: python -m venv .venv ^& .venv\Scripts\activate ^& pip install -r Jarvis\requirements.txt
    )
)

:: ─── Activate venv if present ──────────────────────
if exist ".venv\Scripts\activate.bat" (
    echo  [*] Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo  [WARN] No .venv found. Running with system Python.
    echo  Tip: python -m venv .venv ^& .venv\Scripts\activate ^& pip install -r Jarvis\requirements.txt
)

:: ─── Check requirements.txt exists ────────────────
if not exist "Jarvis\requirements.txt" (
    echo  [ERROR] Jarvis\requirements.txt not found.
    echo  Cannot verify or install dependencies.
    pause
    exit /b 1
)

:: ─── Check dependencies ───────────────────────────
if "%SKIP_DEPS%"=="1" (
    echo  [*] Skipping dependency check (--skip-deps).
    goto deps_done
)

if "%FORCE_INSTALL%"=="1" (
    echo  [*] Force-installing all dependencies...
    goto install_deps
)

python -c "import PyQt6" >nul 2>&1
if %errorlevel% neq 0 (
    goto install_deps
) else (
    echo  [OK] Core dependencies verified.
    goto deps_after_core
)

:install_deps
echo  [*] Installing dependencies...
if "%VERBOSE%"=="1" (
    pip install -r Jarvis\requirements.txt
) else (
    pip install -r Jarvis\requirements.txt >nul 2>&1
)
if %errorlevel% neq 0 (
    echo  [ERROR] Dependency installation failed.
    echo  Try running: pip install -r Jarvis\requirements.txt
    echo  Check %SESSION_LOG% for details.
    pause
    exit /b 1
)
echo  [OK] Dependencies installed successfully.

:deps_after_core

:: ─── Install colorama if missing ───────────────────
python -c "import colorama" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [*] Installing colorama for colored output...
    pip install colorama >nul 2>&1
)

:: ─── Install optional quality-of-life packages ────
python -c "import rich" >nul 2>&1
if %errorlevel% neq 0 (
    if "%VERBOSE%"=="1" echo  [*] Installing rich for enhanced formatting...
    pip install rich >nul 2>&1
)

python -c "import dotenv" >nul 2>&1
if %errorlevel% neq 0 (
    if "%VERBOSE%"=="1" echo  [*] Installing python-dotenv...
    pip install python-dotenv >nul 2>&1
)

:deps_done

:: ─── Upgrade pip if outdated ──────────────────────
if "%FORCE_INSTALL%"=="1" (
    echo  [*] Upgrading pip...
    python -m pip install --upgrade pip >nul 2>&1
)

:: ─── Pre-flight system checks ─────────────────────
echo.
echo  [*] Running pre-flight checks...

:: Check available disk space (warn if low)
for /f "tokens=3" %%a in ('dir /-c "%~dp0" ^| findstr /i "bytes free"') do set "FREE_BYTES=%%a"
if defined FREE_BYTES (
    if "%VERBOSE%"=="1" echo  [INFO] Free disk space: %FREE_BYTES% bytes
)

:: Check network connectivity (non-blocking)
if "%VERBOSE%"=="1" (
    ping -n 1 -w 1000 8.8.8.8 >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [WARN] No internet connection detected. Offline features only.
    ) else (
        echo  [OK] Network connectivity verified.
    )
)

:: ─── Check for updates (optional) ─────────────────
if exist ".git" (
    where git >nul 2>&1
    if %errorlevel% equ 0 (
        if "%VERBOSE%"=="1" (
            echo  [*] Checking for updates...
            git fetch --dry-run >nul 2>&1
            if %errorlevel% equ 0 (
                for /f %%i in ('git rev-list HEAD..@{u} --count 2^>nul') do (
                    if %%i gtr 0 (
                        echo  [INFO] %i update(s) available. Run 'git pull' to update.
                    ) else (
                        echo  [OK] You are up to date.
                    )
                )
            )
        )
    )
)

:: ─── Validate Jarvis module structure ─────────────
if not exist "Jarvis\main.py" (
    if not exist "Jarvis\__main__.py" (
        echo  [ERROR] Jarvis module entry point not found.
        echo  Expected: Jarvis\main.py or Jarvis\__main__.py
        pause
        exit /b 1
    )
)

if not exist "Jarvis\__init__.py" (
    echo  [WARN] Jarvis\__init__.py not found. Module may not import correctly.
)

:: ─── Set environment variables ────────────────────
set "JARVIS_ROOT=%~dp0"
set "JARVIS_SESSION=%TODAY%_%NOW::=%"
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
set "PYTHONUNBUFFERED=1"

if "%HEADLESS%"=="1" (
    set "JARVIS_HEADLESS=1"
    echo  [*] Running in headless mode (no GUI).
)

:: ─── Launch Jarvis ─────────────────────────────────
echo.
echo  [*] Starting Jarvis...
echo  --------------------------------------------------
echo.

if "%HEADLESS%"=="1" (
    python -m Jarvis.main --headless
) else (
    python -m Jarvis.main
)

:: ─── Capture exit code immediately ────────────────
set "EXIT_CODE=%errorlevel%"

:: ─── Exit ──────────────────────────────────────────
if %EXIT_CODE% neq 0 (
    echo.
    echo  [ERROR] Jarvis exited with error code %EXIT_CODE%
    echo  Check Jarvis\logs\crash.log for details.

    :: ─── Offer crash recovery options ─────────────
    echo.
    echo  ======================================================
    echo     Recovery Options
    echo  ======================================================
    echo    1. Restart Jarvis
    echo    2. Restart with --verbose
    echo    3. Open crash log
    echo    4. Reinstall dependencies
    echo    5. Exit
    echo  ======================================================
    echo.
    set /p "RECOVERY=  Select option (1-5): "
    if "!RECOVERY!"=="1" goto launch_jarvis
    if "!RECOVERY!"=="2" (
        set "VERBOSE=1"
        goto launch_jarvis
    )
    if "!RECOVERY!"=="3" (
        if exist "Jarvis\logs\crash.log" (
            start notepad "Jarvis\logs\crash.log"
        ) else (
            echo  [WARN] No crash.log found.
        )
    )
    if "!RECOVERY!"=="4" (
        set "FORCE_INSTALL=1"
        goto install_deps
    )
) else (
    echo.
    echo  [OK] Jarvis exited gracefully.
)

:: ─── Session duration ─────────────────────────────
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set "END_NOW=%%a:%%b"
echo  [*] Session ended: %TODAY% %END_NOW%

echo.
pause
exit /b %EXIT_CODE%

:: ─── Help text ────────────────────────────────────
:show_help
echo.
echo  Usage: run_jarvis.bat [OPTIONS]
echo.
echo  Options:
echo    --skip-deps       Skip dependency verification
echo    --force-install   Force reinstall all dependencies
echo    --verbose         Enable verbose output and diagnostics
echo    --headless        Run without GUI (CLI mode only)
echo    --env "path"      Use a custom .env file
echo    --python "path"   Use a custom Python executable
echo    -h, --help        Show this help message
echo.
echo  Examples:
echo    run_jarvis.bat
echo    run_jarvis.bat --verbose
echo    run_jarvis.bat --headless --skip-deps
echo    run_jarvis.bat --python "C:\Python312\python.exe"
echo    run_jarvis.bat --env "configs\production.env"
echo.
exit /b 0

:launch_jarvis
echo.
echo  [*] Restarting Jarvis...
echo  --------------------------------------------------
echo.
if "%HEADLESS%"=="1" (
    python -m Jarvis.main --headless
) else (
    python -m Jarvis.main
)
set "EXIT_CODE=%errorlevel%"
goto eof

:eof
echo.
pause
exit /b %EXIT_CODE%
