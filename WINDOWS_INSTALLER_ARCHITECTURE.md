## Jarvis Windows Installer Architecture

This document describes how Jarvis should be delivered as a polished Windows application on par with commercial software. It complements the lightweight `Setup.bat` bootstrapper and the `install_jarvis.py` GUI wizard.

### Chosen Installer Technology

For first-class Windows UX with relatively low complexity, we will use **Inno Setup** as the primary packaging technology:

- **Pros**
  - Mature, well-documented, widely used for Python applications.
  - Native Windows UI, progress bars, EULA pages, and customization.
  - Easy to create **Start Menu entries**, **desktop shortcuts**, and **uninstall entries**.
  - Scriptable: can call helper executables or `python.exe` to run `install_jarvis.py`.
  - Simple integration with code-signing tools for trusted distribution.
- **Cons**
  - Not MSI-native; for strict enterprise requirements an MSI/WiX track can be evaluated later.

### High-Level Responsibilities

- **Inno Setup Installer (JarvisSetup.exe)**
  - Presents the user with a standard Windows install wizard.
  - Lets the user choose:
    - Install scope (per-user vs. per-machine, where permitted).
    - Installation directory (default: `%ProgramFiles%\Antigravity\Jarvis` for machine installs or `%LocalAppData%\Antigravity\Jarvis` for per-user).
  - Copies the Jarvis application files into the chosen directory.
  - Optionally deploys a private/embedded Python runtime if we decide not to rely on system Python.
  - Invokes `install_jarvis.py` **silently or in GUI mode**, passing the selected install directory.
  - Registers:
    - Start Menu shortcuts (e.g., `Jarvis AI`).
    - Optional desktop shortcut.
    - An uninstall entry under \"Apps & Features\".
  - Optionally runs a first-launch task (e.g., show a welcome screen or configuration wizard).

- **`install_jarvis.py` (GUI Integration Wizard)**
  - Already:
    - Creates an **isolated `.venv`** by default at the target install path.
    - Installs dependencies from `Jarvis/requirements.txt` (or `requirements.txt` fallback).
    - Copies source files from the extraction directory to the final install directory.
    - Creates Start Menu and Desktop shortcuts using PowerShell.
  - Additional responsibilities (planned/ensured by this work):
    - Always write an **installer log file** inside the target install directory (e.g., `Jarvis_install.log`) so users can send it with bug reports.
    - Ensure that configuration files (such as `.env`) are created/updated to point to the correct cloud endpoints and service URLs.
    - Be callable in two modes:
      - **Wizard/interactive mode** (current PyQt6 GUI).
      - **Silent/configured mode**, where Inno Setup can supply parameters like `--install-dir` and `--no-gui` for unattended installs (for future extension).

- **`Setup.bat` (Developer Bootstrapper)**
  - For developers and power users who run Jarvis directly from the extracted folder.
  - Verifies system Python (presence, version ≥ 3.10, and 64‑bit).
  - Ensures minimal GUI prerequisites (`PyQt6`, `Pillow`) are available in the active Python environment.
  - Launches `install_jarvis.py` (GUI preferred, console fallback) and logs bootstrap activity to `install_jarvis_bootstrap.log`.
  - Not intended as the primary installer for users downloading from the website once `JarvisSetup.exe` is in place.

### Uninstall and Repair Strategy

- **Uninstall (Inno Setup)**
  - The Inno Setup uninstaller will:
    - Remove installed files under the application directory (except optional user data/config if desired).
    - Remove Start Menu and desktop shortcuts.
    - Remove registry entries created by the installer.
  - For data preservation:
    - App data (logs, conversation history, avatars, etc.) lives under:
      - `%AppData%\Antigravity\Jarvis` for logs/config/data (as used by `Jarvis/config.py`).
    - The uninstaller can be configured to:
      - Either prompt the user to remove these directories.
      - Or leave them behind for re-install / troubleshooting.

- **Repair / Modify**
  - Running the `JarvisSetup.exe` again can expose:
    - **Repair**: re-run `install_jarvis.py` over the existing installation, re-creating the `.venv`, re-installing dependencies, and restoring default shortcuts.
    - **Modify**: toggle optional components (e.g., desktop shortcut, extra tools) using installer components.
  - Inside `install_jarvis.py`:
    - If the target install directory already contains `.venv` and Jarvis files, the wizard should treat this as a **repair/upgrade** path instead of a fresh install:
      - Validate dependencies.
      - Optionally re-run `pip install -r requirements.txt` with `--upgrade`.
      - Preserve existing `.env` and user data by default.

### Cloud / Backend Integration

- **Configuration file location**
  - `Jarvis/config.py` already loads environment variables from a `.env` file located alongside the `Jarvis` package.
  - `install_jarvis.py` will:
    - Ensure that a `.env` file exists in the `Jarvis` package directory at the install path.
    - Populate it with sane defaults and placeholders for:
      - `LLM_PROVIDER`
      - Cloud API base URLs (e.g., `GEMINI_API_KEY`, `GROQ_API_KEY`, `GROK_API_KEY`).
      - Any internal company API endpoints (e.g., `JARVIS_API_URL`, `JARVIS_DB_URL`) as needed by your backend.

- **Installer / Wizard Flow**
  - For simple public distribution:
    - The `.env` written during install uses your **production** cloud endpoints and leaves secret API keys empty (or expects them from environment variables).
  - For company-internal deployment:
    - The GUI wizard can include an advanced page (future work) where admins enter:
      - Environment (Production / Staging / Development).
      - Overrides for API/DB endpoints.
      - Whether to enable or disable optional cloud features (e.g., Groq/Grok).
    - These values are written into `.env` and consumed at runtime by `Jarvis/config.py`.

### Summary

- End users should primarily download and run **`JarvisSetup.exe`** (Inno Setup) from your website.
- `JarvisSetup.exe` wraps:
  - File placement.
  - Registry/shortcut/uninstall integration.
  - Optional embedded Python runtime.
  - Invocation of the Python-based integration wizard.
- `install_jarvis.py` handles:
  - Virtual environment creation and dependency installation.
  - Writing configuration (`.env`) that connects the client to your hosted APIs, database, and cloud LLMs.
  - Shortcut creation at the application layer.
- `Setup.bat` is now a **developer-centric bootstrapper**, offering robust checks and logging, but not the main distribution mechanism for non-technical users.

