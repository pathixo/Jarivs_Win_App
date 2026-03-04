import sys
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

try:
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                 QHBoxLayout, QLabel, QPushButton, QProgressBar, 
                                 QFileDialog, QCheckBox, QLineEdit, QStackedWidget,
                                 QMessageBox, QFrame, QTextEdit)
    from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
    from PyQt6.QtGui import QIcon, QPixmap
except ImportError:
    print("PyQt6 is required for the GUI installer. Please install it with: pip install PyQt6")
    sys.exit(1)

def speak_async(text):
    """Uses Windows built-in TTS via PowerShell to speak asynchronously."""
    def _speak():
        safe_text = text.replace("'", "''")
        ps_script = f"Add-Type -AssemblyName System.Speech; $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; $synth.Speak('{safe_text}')"
        subprocess.run(["powershell", "-Command", ps_script], creationflags=subprocess.CREATE_NO_WINDOW)
    threading.Thread(target=_speak, daemon=True).start()


class InstallWorker(QObject):
    progress = pyqtSignal(int, str)
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, install_dir, add_desktop_icon, use_venv=True):
        super().__init__()
        self.install_dir = os.path.abspath(install_dir)
        self.add_desktop_icon = add_desktop_icon
        self.use_venv = use_venv
        self.source_dir = os.path.dirname(os.path.abspath(__file__))

    def _get_base_python(self):
        """Finds the base system python to avoid venv-in-venv issues."""
        if sys.platform == "win32":
            base = getattr(sys, 'base_prefix', sys.prefix)
            base_exe = os.path.join(base, "python.exe")
            if os.path.exists(base_exe):
                return base_exe
        return sys.executable

    def _run_with_log(self, cmd, base_pct, end_pct):
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=self.install_dir,
            creationflags=subprocess.CREATE_NO_WINDOW,
            bufsize=1
        )
        for line in proc.stdout:
            line = line.strip()
            if line:
                self.log_signal.emit(line)
        proc.wait()
        return proc.returncode

    def run(self):
        try:
            # ── Step 0: Kill existing Jarvis processes ──
            self.progress.emit(2, "Clearing existing processes...")
            self.log_signal.emit("Ensuring no Jarvis instances are running...")
            subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe", "/T"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/T", "/FI", f"WINDOWTITLE eq Jarvis*"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(1)

            # ── Step 1: Initialize ──
            self.progress.emit(5, "Initializing system architecture...")
            self.log_signal.emit(f"Source: {self.source_dir}")
            self.log_signal.emit(f"Target: {self.install_dir}")

            if not os.path.exists(self.install_dir):
                os.makedirs(self.install_dir, exist_ok=True)
            
            # ── Step 2: Copy files ──
            if os.path.normpath(self.source_dir) != os.path.normpath(self.install_dir):
                self.progress.emit(10, "Synchronizing core logic...")
                speak_async("Synchronizing core logic.")
                ignore_patterns = shutil.ignore_patterns('.venv', '.git', '__pycache__', '.pytest_cache', 'build', 'dist')
                items = os.listdir(self.source_dir)
                for idx, item in enumerate(items):
                    s = os.path.join(self.source_dir, item)
                    d = os.path.join(self.install_dir, item)
                    
                    if item in ('.venv', '.git', '__pycache__', '.pytest_cache', 'build', 'dist', 'install_jarvis.py'):
                        continue
                        
                    self.log_signal.emit(f"Syncing: {item}")
                    if os.path.isdir(s):
                        # Use dirs_exist_ok=True for robust copying in Python 3.8+
                        shutil.copytree(s, d, ignore=ignore_patterns, dirs_exist_ok=True)
                    else:
                        shutil.copy2(s, d)
                    self.progress.emit(10 + int(20 * (idx+1)/len(items)), f"Synchronizing: {item}")
            else:
                self.log_signal.emit("Running from source. Skipping copy phase.")
                self.progress.emit(30, "Source validated.")

            # ── Step 3: Environment Setup ──
            python_for_pip = sys.executable
            if self.use_venv:
                self.progress.emit(40, "Establishing environment...")
                speak_async("Establishing isolated environment.")
                
                venv_path = os.path.join(self.install_dir, ".venv")
                base_py = self._get_base_python()
                self.log_signal.emit(f"Using base python: {base_py}")
                
                # Try standard venv creation
                ret = self._run_with_log([base_py, "-m", "venv", ".venv"], 40, 55)
                if ret != 0:
                    self.log_signal.emit("Venv failed. Retrying with fallback...")
                    ret = self._run_with_log([base_py, "-m", "venv", ".venv", "--without-pip"], 40, 55)
                    if ret == 0:
                        self.log_signal.emit("Venv created without pip. Bootstrapping...")
                        ret = self._run_with_log([os.path.join(venv_path, "Scripts", "python.exe"), "-m", "ensurepip"], 55, 60)

                if ret != 0:
                    self.finished.emit(False, "Neural environment creation failed. Try disabling 'Isolated Environment' in settings.")
                    return
                python_for_pip = os.path.join(venv_path, "Scripts", "python.exe")
            else:
                self.log_signal.emit("Using system environment as requested.")
                self.progress.emit(50, "Environment ready.")

            # ── Step 4: Dependencies ──
            self.progress.emit(65, "Downloading neural weights...")
            speak_async("Downloading dependencies.")
            
            req_file = os.path.join(self.install_dir, "Jarvis", "requirements.txt")
            if not os.path.exists(req_file):
                req_file = os.path.join(self.install_dir, "requirements.txt")
            
            if os.path.exists(req_file):
                self.log_signal.emit("Updating package manager...")
                self._run_with_log([python_for_pip, "-m", "pip", "install", "--upgrade", "pip"], 65, 70)
                
                self.log_signal.emit("Installing dependencies...")
                ret = self._run_with_log([python_for_pip, "-m", "pip", "install", "-r", req_file], 70, 90)

            # ── Step 5: Finalize ──
            self.progress.emit(95, "Finalizing access points...")
            speak_async("Finalizing access points.")
            
            launcher_bat = os.path.join(self.install_dir, "run_jarvis.bat")
            icon_file = os.path.join(self.install_dir, "jarvis.ico")
            
            def create_shortcut(target, shortcut_path, working, icon):
                # Ensure path uses single backslashes for PowerShell or is properly escaped
                shortcut_path = os.path.normpath(shortcut_path)
                target = os.path.normpath(target)
                working = os.path.normpath(working)
                icon = os.path.normpath(icon)
                
                ps = f"""
                $WshShell = New-Object -ComObject WScript.Shell
                $Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
                $Shortcut.TargetPath = '{target}'
                $Shortcut.WorkingDirectory = '{working}'
                $Shortcut.IconLocation = '{icon}'
                $Shortcut.Save()
                """
                subprocess.run(["powershell", "-Command", ps], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if self.add_desktop_icon:
                desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
                shortcut_path = os.path.join(desktop, "Jarvis AI.lnk")
                self.log_signal.emit(f"Creating Desktop shortcut...")
                create_shortcut(launcher_bat, shortcut_path, self.install_dir, icon_file)

            start_menu = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs")
            start_shortcut = os.path.join(start_menu, "Jarvis AI.lnk")
            self.log_signal.emit(f"Adding to Start Menu...")
            create_shortcut(launcher_bat, start_shortcut, self.install_dir, icon_file)

            self.progress.emit(100, "Installation Complete.")
            self.finished.emit(True, "Success")

        except Exception as e:
            self.log_signal.emit(f"CRITICAL ERROR: {str(e)}")
            self.finished.emit(False, str(e))


class InstallerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis AI - System Integration")
        self.setFixedSize(650, 520)
        self.setStyleSheet("""
            QMainWindow { background-color: #0b0e14; }
            QLabel { color: #8892b0; font-family: 'Segoe UI'; font-size: 14px; }
            QPushButton { 
                background-color: #233554; 
                color: #00ffff; 
                border: 1px solid #00ffff;
                border-radius: 4px; 
                padding: 10px 20px; 
                font-weight: bold;
                font-family: 'Consolas';
            }
            QPushButton:hover { background-color: rgba(0, 255, 255, 0.1); }
            QPushButton:disabled { color: #495670; border-color: #495670; }
            QLineEdit { background-color: #1a1a2e; color: #ccd6f6; border: 1px solid #233554; padding: 8px; border-radius: 4px; }
            QProgressBar { border: 1px solid #233554; border-radius: 8px; text-align: center; background-color: #1a1a2e; color: #00ffff; font-weight: bold; }
            QProgressBar::chunk { background-color: #00ffff; border-radius: 7px; }
            QTextEdit { background-color: #010409; color: #8b949e; border: 1px solid #233554; font-family: 'Consolas'; font-size: 11px; border-radius: 4px; }
            QCheckBox { color: #8892b0; font-size: 12px; }
        """)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(30, 20, 30, 20)

        header = QFrame()
        hl = QHBoxLayout(header)
        self.icon_lbl = QLabel()
        if os.path.exists("jarvis.ico"):
            self.icon_lbl.setPixmap(QPixmap("jarvis.ico").scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio))
        hl.addWidget(self.icon_lbl)
        tv = QVBoxLayout()
        t = QLabel("JARVIS")
        t.setStyleSheet("font-size: 28px; font-weight: bold; color: #00ffff; font-family: 'Consolas';")
        tv.addWidget(t)
        st = QLabel("SYSTEM INTEGRATION WIZARD")
        st.setStyleSheet("font-size: 10px; color: #8892b0;")
        tv.addWidget(st)
        hl.addLayout(tv)
        hl.addStretch()
        self.layout.addWidget(header)

        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack)

        self.init_welcome_page()
        self.init_settings_page()
        self.init_progress_page()
        self.init_finish_page()

        QTimer.singleShot(1000, lambda: speak_async("Greetings, sir. Ready for system integration."))

    def init_welcome_page(self):
        p = QWidget(); l = QVBoxLayout(p)
        d = QLabel("Ready to initiate system synchronization?\n\nThis process will establish neural pathways and calibrate your execution environment.")
        d.setWordWrap(True); d.setStyleSheet("font-size: 16px; color: #ccd6f6;")
        l.addWidget(d); l.addStretch()
        bn = QPushButton("INITIATE")
        bn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        l.addWidget(bn, alignment=Qt.AlignmentFlag.AlignRight)
        self.stack.addWidget(p)

    def init_settings_page(self):
        p = QWidget(); l = QVBoxLayout(p)
        l.addWidget(QLabel("INSTALLATION VECTOR:"))
        self.path_input = QLineEdit()
        self.path_input.setText(os.path.join(os.environ["USERPROFILE"], "JarvisAI"))
        l.addWidget(self.path_input)
        
        self.desktop_chk = QCheckBox("CREATE DESKTOP ACCESS POINT")
        self.desktop_chk.setChecked(True)
        l.addWidget(self.desktop_chk)

        self.venv_chk = QCheckBox("USE ISOLATED ENVIRONMENT (RECOMMENDED)")
        self.venv_chk.setChecked(True)
        l.addWidget(self.venv_chk)
        
        l.addStretch()
        bi = QPushButton("SYNCHRONIZE")
        bi.clicked.connect(self.start_installation)
        l.addWidget(bi, alignment=Qt.AlignmentFlag.AlignRight)
        self.stack.addWidget(p)

    def init_progress_page(self):
        p = QWidget(); l = QVBoxLayout(p)
        self.lbl_status = QLabel("AWAITING INITIALIZATION...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(self.lbl_status)
        self.pb = QProgressBar(); self.pb.setFixedHeight(25); l.addWidget(self.pb)
        self.lv = QTextEdit(); self.lv.setReadOnly(True); l.addWidget(self.lv)
        self.stack.addWidget(p)

    def init_finish_page(self):
        p = QWidget(); l = QVBoxLayout(p)
        t = QLabel("SYNCHRONIZATION COMPLETE")
        t.setStyleSheet("font-size: 22px; font-weight: bold; color: #00ff00; font-family: 'Consolas';")
        l.addWidget(t, alignment=Qt.AlignmentFlag.AlignCenter)
        l.addStretch()
        br = QPushButton("READY")
        br.clicked.connect(self.finish_installation)
        l.addWidget(br, alignment=Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(p)

    def start_installation(self):
        self.stack.setCurrentIndex(2)
        self.worker = InstallWorker(self.path_input.text(), self.desktop_chk.isChecked(), self.venv_chk.isChecked())
        self.worker.progress.connect(self.update_progress)
        self.worker.log_signal.connect(self.lv.append)
        self.worker.finished.connect(self.installation_finished)
        threading.Thread(target=self.worker.run, daemon=True).start()

    def update_progress(self, val, text):
        self.pb.setValue(val); self.lbl_status.setText(text.upper())

    def installation_finished(self, success, message):
        if success:
            speak_async("Synchronization complete, sir.")
            self.stack.setCurrentIndex(3)
        else:
            speak_async("An error has occurred.")
            QMessageBox.critical(self, "Failed", f"Error: {message}\n\nTip: Try unchecking 'Isolated Environment' in the settings page.")
            self.stack.setCurrentIndex(1)

    def finish_installation(self):
        launcher = os.path.join(self.path_input.text(), "run_jarvis.bat")
        if os.path.exists(launcher):
            subprocess.Popen(["cmd.exe", "/c", "start", "/b", launcher], cwd=self.path_input.text(), creationflags=subprocess.CREATE_NO_WINDOW)
        self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv); w = InstallerGUI(); w.show(); sys.exit(app.exec())
