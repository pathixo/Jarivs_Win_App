import sys
import os
import threading
import logging
import traceback
from datetime import datetime

# Setup Logging
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")
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
    print("CRITICAL ERROR: See crash.log for details")
    traceback.print_exception(exc_type, exc_value, exc_traceback)

sys.excepthook = handle_exception

# Add parent directory to sys.path so 'Jarvis' package can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal
from Jarvis.ui.window import MainWindow
from Jarvis.core.orchestrator import Orchestrator
from Jarvis.output.tts import TTS
from Jarvis.input.listener import Listener


class Worker(QObject):
    """
    Thread-safe bridge for sending text to the UI.
    Qt widgets MUST only be modified from the main thread.
    This worker emits signals (which are thread-safe) instead of
    calling widget methods directly from background threads.
    """
    output_ready = pyqtSignal(str)
    error_ready = pyqtSignal(str)


def main():
    try:
        app = QApplication(sys.argv)
        
        # Initialize Core Components
        orchestrator = Orchestrator()
        tts = TTS()
        
        # Thread-safe worker for UI updates
        worker = Worker()
        
        # Initialize UI
        window = MainWindow()
        window.show()

        # Connect worker signals -> UI (runs on main thread)
        worker.output_ready.connect(window.append_terminal_output)
        worker.error_ready.connect(window.append_terminal_output)

        # Connect UI signals to Logic
        def on_command_input(command_text):
            # This runs on main thread (from signal), safe to touch UI here
            window.append_terminal_output(f"Processing: {command_text}")
            
            # Run orchestrator in separate thread to keep UI responsive
            def process():
                try:
                    response = orchestrator.process_command(command_text)
                    # USE SIGNAL instead of direct widget call
                    worker.output_ready.emit(f"Response: {response}")
                    tts.speak(response)
                except Exception as e:
                    logging.error(f"Orchestrator Process Error: {e}")
                    worker.error_ready.emit(f"Error: {e}")
            
            threading.Thread(target=process, daemon=True).start()

        window.terminal.command_signal.connect(on_command_input)
        
        # Connect TTS signal to UI Audio Player
        tts.audio_generated.connect(window.play_audio)

        # Connect Voice Listener signals
        listener = Listener()
        
        # Update UI based on listener state
        listener.state_changed.connect(window.visuals.set_color)
        
        # Process voice commands
        listener.command_received.connect(on_command_input)
        
        # Connect manual trigger (Mic Button)
        window.mic_button.clicked.connect(listener.start_listening)
        
        listener.start()

        sys.exit(app.exec())
        
    except Exception as e:
        logging.error("Main Loop Crash", exc_info=True)
        print(f"App Crashed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
