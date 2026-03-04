
import os
import sys
import shutil
import subprocess
import ctypes
from pathlib import Path

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def print_jarvis(text):
    print(f"
[JARVIS] {text}")

def run_command(cmd, cwd=None):
    return subprocess.call(cmd, shell=True, cwd=cwd)

def create_shortcut(target_path, shortcut_path, working_dir, icon_path):
    """Creates a Windows shortcut using PowerShell."""
    ps_script = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
    $Shortcut.TargetPath = "{target_path}"
    $Shortcut.WorkingDirectory = "{working_dir}"
    $Shortcut.IconLocation = "{icon_path}"
    $Shortcut.Save()
    """
    subprocess.run(["powershell", "-Command", ps_script], capture_output=True)

def install():
    print("======================================================")
    print("           JARVIS SYSTEM INSTALLATION                ")
    print("======================================================")
    
    print_jarvis("Greetings, sir. Preparing to integrate my core systems into your environment.")
    
    # 1. Choose Installation Directory
    default_install_dir = os.path.join(os.environ["USERPROFILE"], "JarvisAI")
    install_dir = input(f"
[?] Enter installation directory (Default: {default_install_dir}): ").strip()
    if not install_dir:
        install_dir = default_install_dir
    
    install_path = Path(install_dir)
    
    # 2. Confirm Installation
    confirm = input(f"
[!] Proceed with installation to {install_dir}? (y/n): ").lower()
    if confirm != 'y':
        print_jarvis("Installation aborted. I shall remain in my current state.")
        return

    # 3. Ask for Desktop Icon
    add_desktop_icon = input("
[?] Would you like to add a shortcut to your Desktop? (y/n): ").lower() == 'y'
    
    # 4. Copying Files
    print_jarvis("Copying core logic and sub-routines...")
    if install_path.exists():
        print_jarvis("Target directory already exists. Updating files...")
    else:
        install_path.mkdir(parents=True, exist_ok=True)

    # Exclude certain directories like .venv, .git, etc.
    ignore_patterns = shutil.ignore_patterns('.venv', '.git', '__pycache__', '.pytest_cache', 'build', 'dist')
    
    source_dir = os.path.dirname(os.path.abspath(__file__))
    for item in os.listdir(source_dir):
        s = os.path.join(source_dir, item)
        d = os.path.join(install_dir, item)
        if os.path.isdir(s):
            if item not in ('.venv', '.git', '__pycache__', '.pytest_cache', 'build', 'dist'):
                if os.path.exists(d):
                    shutil.rmtree(d)
                shutil.copytree(s, d, ignore=ignore_patterns)
        else:
            shutil.copy2(s, d)

    # 5. Setup Virtual Environment
    print_jarvis("Establishing an isolated virtual environment...")
    run_command(f"python -m venv .venv", cwd=install_dir)
    
    # 6. Install Dependencies
    print_jarvis("Downloading necessary libraries and dependencies...")
    # Update pip first
    run_command(f".venv\Scripts\python.exe -m pip install --upgrade pip", cwd=install_dir)
    # Install from requirements.txt (Checking multiple locations)
    req_file = os.path.join(install_dir, "Jarvis", "requirements.txt")
    if not os.path.exists(req_file):
        req_file = os.path.join(install_dir, "requirements.txt")
        
    if os.path.exists(req_file):
        run_command(f".venv\Scripts\pip.exe install -r "{req_file}"", cwd=install_dir)
    else:
        print_jarvis("Warning: requirements.txt not found. Some features may be limited.")

    # 7. Create Shortcuts
    launcher_bat = os.path.join(install_dir, "run_jarvis.bat")
    icon_file = os.path.join(install_dir, "jarvis.ico")
    
    if add_desktop_icon:
        print_jarvis("Adding icon to the desktop...")
        desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
        create_shortcut(launcher_bat, os.path.join(desktop, "Jarvis.lnk"), install_dir, icon_file)

    # Start Menu Shortcut
    print_jarvis("Adding to Start Menu...")
    start_menu = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs")
    create_shortcut(launcher_bat, os.path.join(start_menu, "Jarvis AI.lnk"), install_dir, icon_file)

    print("
" + "="*54)
    print_jarvis("Installation complete, sir. I am fully integrated.")
    print_jarvis(f"You can find me at: {install_dir}")
    print_jarvis("You can now launch me from the Desktop, Start Menu, or by saying 'Hello' to your computer.")
    print("="*54)

    launch = input("
[?] Would you like to launch Jarvis now? (y/n): ").lower()
    if launch == 'y':
        subprocess.Popen([launcher_bat], cwd=install_dir, shell=True)

if __name__ == "__main__":
    try:
        install()
    except Exception as e:
        print(f"
[ERROR] An unexpected error occurred during installation: {e}")
        input("
Press Enter to exit...")
