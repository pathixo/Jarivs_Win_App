import sys
import os
import threading
import logging
import traceback

# Setup Logging
from Jarvis.config import LOGS_DIR
log_file = os.path.join(LOGS_DIR, "crash.log")
logging.basicConfig(
    filename=log_file,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    traceback.print_exception(exc_type, exc_value, exc_traceback)

sys.excepthook = handle_exception

# Add parent directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtMultimedia import QMediaPlayer
from Jarvis.ui.window import MainWindow
from Jarvis.ui.tray import JarvisTrayIcon
from Jarvis.core.orchestrator import Orchestrator
from Jarvis.output.tts import TTS
from Jarvis.input.listener import Listener


class Worker(QObject):
    """Thread-safe bridge for UI updates from background threads."""
    output_ready = pyqtSignal(str)
    execute_ready = pyqtSignal(str, str)  # command, output


def main():
    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)  # Keep running when window hides

        orchestrator = Orchestrator()
        tts = TTS()
        worker = Worker()

        window = MainWindow()
        # Don't show immediately if we want silent start, but generally show on launch
        window.show()

        # Listener (fully autonomous)
        listener = Listener()

        # System Tray
        tray = JarvisTrayIcon()
        
        # Connect Tray Signals
        tray.on_show_window.connect(window.show)
        tray.on_show_window.connect(window.activateWindow)
        tray.on_quit_app.connect(app.quit)
        
        def toggle_listening():
            is_paused = listener.toggle_pause()
            # Loop handled in listener, state emitted automatically
            
        tray.on_toggle_listening.connect(toggle_listening)
        
        # Connect Listener state to Tray Icon
        listener.state_changed.connect(tray.update_icon, Qt.ConnectionType.QueuedConnection)

        # Thread-safe UI connections
        worker.output_ready.connect(window.append_terminal_output, Qt.ConnectionType.QueuedConnection)
        
        # Listener signals -> UI (crash-safe)
        listener.state_changed.connect(window.orb.set_state, Qt.ConnectionType.QueuedConnection)
        listener.state_changed.connect(window.update_status, Qt.ConnectionType.QueuedConnection)

        # Pause listener while TTS is speaking so it doesn't hear itself
        def on_tts_start():
            listener.set_processing(True)

        def on_tts_done(status):
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                listener.set_processing(False)

        window.player.playbackStateChanged.connect(
            lambda state: listener.set_processing(state == QMediaPlayer.PlaybackState.PlayingState)
        )

        def on_command_input(command_text):
            """Handle commands from terminal or voice."""
            window.append_terminal_output(f"Processing: {command_text}")

            def process():
                try:
                    response = orchestrator.process_command(command_text)
                    # Show in terminal
                    worker.output_ready.emit(f"Response: {response}")
                    # Only TTS the actual AI response — NOT terminal echoes
                    if response and not response.startswith("Error"):
                        # Pause listener before speaking
                        listener.set_processing(True)
                        tts.speak(response)
                except Exception as e:
                    logging.error(f"Process Error: {e}", exc_info=True)
                    worker.output_ready.emit(f"Error: {e}")

            threading.Thread(target=process, daemon=True).start()

        # Connect voice commands (no visual terminal input anymore)
        listener.command_received.connect(on_command_input, Qt.ConnectionType.QueuedConnection)

        # Connect voice commands
        listener.command_received.connect(on_command_input, Qt.ConnectionType.QueuedConnection)

        # TTS audio playback
        tts.audio_generated.connect(window.play_audio, Qt.ConnectionType.QueuedConnection)

        # Start autonomous listening
        listener.start()

        sys.exit(app.exec())

    except Exception as e:
        logging.error("Main Loop Crash", exc_info=True)
        traceback.print_exc()


if __name__ == "__main__":
    main()
