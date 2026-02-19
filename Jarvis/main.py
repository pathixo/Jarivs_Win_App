
import sys
import os

# Add parent directory to sys.path so 'Jarvis' package can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from PyQt6.QtWidgets import QApplication
from Jarvis.ui.window import MainWindow
from Jarvis.core.orchestrator import Orchestrator
from Jarvis.output.tts import TTS
from Jarvis.input.listener import Listener
import threading

def main():
    app = QApplication(sys.argv)
    
    # Initialize Core Components
    orchestrator = Orchestrator()
    tts = TTS()
    
    # Initialize UI
    window = MainWindow()
    window.show()

    # Connect UI signals to Logic
    def on_command_input(command_text):
        window.append_terminal_output(f"Processing: {command_text}")
        
        # Run orchestrator in separate thread to keep UI responsive
        def process():
            response = orchestrator.process_command(command_text)
            window.append_terminal_output(f"Response: {response}")
            tts.speak(response)
        
        threading.Thread(target=process).start()

    window.terminal.command_signal.connect(on_command_input)
    
    # Connect TTS signal to UI Audio Player
    tts.audio_generated.connect(window.play_audio)

    # Initialize Voice Listener (Optional)
    def on_wake_word():
        window.append_terminal_output("Wake Word Detected! Listening...")
        tts.speak("Yes?")

    listener = Listener(on_wake_word=on_wake_word)
    listener.start()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
