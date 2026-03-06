import os
import sys
import subprocess
import shutil
from pathlib import Path

def speak_ps(text):
    """Uses Windows built-in TTS via PowerShell."""
    safe_text = text.replace("'", "''")
    ps_script = f"Add-Type -AssemblyName System.Speech; $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; $synth.Speak('{safe_text}')"
    subprocess.run(["powershell", "-Command", ps_script], creationflags=subprocess.CREATE_NO_WINDOW)

def create_icon():
    print("Generating JARVIS icon...")
    try:
        import create_jarvis_icon
        create_jarvis_icon.create_jarvis_icon()
        return True
    except Exception as e:
        print(f"Failed to generate icon: {e}")
        return False

def create_desktop_shortcut():
    print("Creating Desktop shortcut...")
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        launcher_bat = os.path.join(base_dir, "run_jarvis.bat")
        icon_file = os.path.join(base_dir, "jarvis.ico")
        desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
        shortcut_path = os.path.join(desktop, "Jarvis AI.lnk")
        
        # Ensure paths are correct
        if not os.path.exists(launcher_bat):
            # Create a simple bat if missing
            with open(launcher_bat, "w") as f:
                f.write("@echo off\n")
                f.write("cd /d \"%~dp0\"\n")
                f.write("call .venv\\Scripts\\activate\n")
                f.write("python -m Jarvis.main\n")
                f.write("pause\n")

        ps_script = f"""
        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
        $Shortcut.TargetPath = '{launcher_bat}'
        $Shortcut.WorkingDirectory = '{base_dir}'
        $Shortcut.IconLocation = '{icon_file}'
        $Shortcut.Save()
        """
        subprocess.run(["powershell", "-Command", ps_script], capture_output=True, check=True)
        print(f"Shortcut created at: {shortcut_path}")
        return True
    except Exception as e:
        print(f"Failed to create shortcut: {e}")
        return False

def update_env():
    print("Updating .env configuration...")
    env_path = ".env"
    if not os.path.exists(env_path):
        if os.path.exists(".env.example"):
            shutil.copy(".env.example", env_path)
        else:
            with open(env_path, "w") as f:
                f.write("LLM_PROVIDER=ollama\n")
                f.write("STT_PROVIDER=gemini\n")
                f.write("TTS_ENGINE=gemini\n")
                f.write("GEMINI_API_KEY=\n")
                f.write("OLLAMA_MODEL=gemma:2b\n")
    
    with open(env_path, "r") as f:
        lines = f.readlines()
    
    new_lines = []
    keys_to_update = {
        "LLM_PROVIDER": "ollama",
        "STT_PROVIDER": "gemini",
        "TTS_ENGINE": "gemini"
    }
    
    seen_keys = set()
    for line in lines:
        updated = False
        for key, value in keys_to_update.items():
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                seen_keys.add(key)
                updated = True
                break
        if not updated:
            new_lines.append(line)
            
    for key, value in keys_to_update.items():
        if key not in seen_keys:
            new_lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)
    print("Configuration updated to: LLM=Ollama, STT=Gemini, TTS=Gemini")

def main():
    print("=== JARVIS SYSTEM FIX ===")
    
    # 1. Update Env
    update_env()
    
    # 2. Icon
    if not os.path.exists("jarvis.ico"):
        create_icon()
    
    # 3. Shortcut
    create_desktop_shortcut()
    
    print("\nSystem fix complete, sir.")
    speak_ps("System fix complete, sir. Your desktop access point is ready.")
    print("Please make sure to add your GEMINI_API_KEY in the .env file if you haven't already.")

if __name__ == "__main__":
    main()
