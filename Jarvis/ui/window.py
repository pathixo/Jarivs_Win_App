from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from Jarvis.ui.terminal import Terminal
# from Jarvis.ui.web_view import WebView # Defer WebView for now to avoid complexity if not ready
from Jarvis.output.visuals import ThinkingOrb

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis Hybrid Brain")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet("background-color: #121212; color: white;")

        # Media Player Setup
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top Section: Thinking Orb & Status
        top_layout = QHBoxLayout()
        self.visuals = ThinkingOrb()
        self.visuals.setFixedSize(150, 150)
        top_layout.addWidget(self.visuals, alignment=Qt.AlignmentFlag.AlignCenter)
        
        main_layout.addLayout(top_layout)

        # Middle Section: Terminal (and WebView placeholder)
        middle_layout = QHBoxLayout()
        
        # Placeholder for WebView (uncomment when ready)
        # self.web_view = WebView()
        # middle_layout.addWidget(self.web_view, 2) 
        
        self.terminal = Terminal()
        middle_layout.addWidget(self.terminal, 1) 
        
        main_layout.addLayout(middle_layout)

    def append_terminal_output(self, text):
        self.terminal.append_output(text)

    def play_audio(self, file_path):
        """
        Plays audio from the given file path using QMediaPlayer.
        """
        try:
            url = QUrl.fromLocalFile(file_path)
            self.player.setSource(url)
            self.player.play()
        except Exception as e:
            self.terminal.append_output(f"Audio Error: {e}")
