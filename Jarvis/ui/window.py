import sys
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect, 
                             QSizePolicy, QApplication)
from PyQt6.QtCore import Qt, QTimer, QUrl, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QRadialGradient
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from Jarvis.output.visuals import ThinkingOrb

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis AI")
        self.resize(400, 600)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Center window
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

        # Central Widget
        self.central_widget = QWidget()
        self.central_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a1a2e, stop:1 #0f0f1a);
                border-radius: 20px;
                border: 1px solid #233554;
            }
        """)
        self.setCentralWidget(self.central_widget)

        # Main layout
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header / Status Bar
        self.header = QFrame()
        self.header.setFixedHeight(40)
        self.header.setStyleSheet("background: rgba(10, 14, 23, 0.95); border-bottom: 1px solid #233554; border-top-left-radius: 20px; border-top-right-radius: 20px;")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(15, 0, 15, 0)
        
        self.status_label = QLabel("● INITIALIZING")
        self.status_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.status_label.setStyleSheet("color: #8892b0; background: transparent;")
        
        self.mode_label = QLabel("🔊 AUTONOMOUS MODE")
        self.mode_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.mode_label.setStyleSheet("color: #00ff9f; background: rgba(0, 255, 159, 0.1); border-radius: 4px; padding: 2px 6px;")

        header_layout.addWidget(self.status_label)
        header_layout.addStretch()
        header_layout.addWidget(self.mode_label)

        # 2. Orb Container
        self.orb_container = QFrame()
        self.orb_container.setStyleSheet("background: transparent; border: none;")
        orb_layout = QVBoxLayout(self.orb_container)
        orb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # The Thinking Orb
        self.orb = ThinkingOrb()
        self.orb.setFixedSize(200, 200)
        
        # State Text
        self.state_text = QLabel("Initializing systems...")
        self.state_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_text.setFont(QFont("Segoe UI", 12))
        self.state_text.setStyleSheet("color: #a8b2d1; background: transparent; margin-top: 20px; border: none;")
        
        orb_layout.addWidget(self.orb)
        orb_layout.addWidget(self.state_text)

        # Add to main layout
        main_layout.addWidget(self.header)
        main_layout.addWidget(self.orb_container)

        # Audio Player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)

        # Dragging variables
        self.old_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def update_status(self, state_name):
        """Update the status label and state text based on listener state."""
        if state_name == "listening":
            self.status_label.setText("● LISTENING")
            self.status_label.setStyleSheet("color: #00ff9f; background: transparent;")
            self.state_text.setText("I'm listening...")
            self.orb.set_state("listening")
        elif state_name == "processing":
            self.status_label.setText("● THINKING")
            self.status_label.setStyleSheet("color: #ff79c6; background: transparent;")
            self.state_text.setText("Processing...")
            self.orb.set_state("processing")
        else:  # waiting
            self.status_label.setText("● READY")
            self.status_label.setStyleSheet("color: #00ffff; background: transparent;")
            self.state_text.setText("Standing by...")
            self.orb.set_state("idle")

    def play_audio(self, file_path):
        """Play TTS audio file."""
        try:
            url = QUrl.fromLocalFile(file_path)
            self.player.setSource(url)
            self.player.play()
        except Exception as e:
            print(f"Audio Play Error: {e}")

    def append_terminal_output(self, text, type="info"):
        """Legacy method for compatibility - logs to console instead."""
        print(f"[{type.upper()}] {text}")

    def closeEvent(self, event):
        """Minimize to tray instead of quitting."""
        event.ignore()
        self.hide()
        
    def force_quit(self):
        """Actually quit the application."""
        QApplication.instance().quit()
