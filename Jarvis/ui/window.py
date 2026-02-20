from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QGraphicsDropShadowEffect,
                             QSizePolicy)
from PyQt6.QtCore import Qt, QUrl, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from Jarvis.ui.terminal import Terminal
from Jarvis.output.visuals import ThinkingOrb


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS")
        self.setGeometry(100, 50, 1100, 850)
        self.terminal_visible = True

        # Media Player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        # Main container
        central = QWidget()
        self.setCentralWidget(central)
        central.setStyleSheet("background: #0a0e17;")
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 15, 20, 15)
        main_layout.setSpacing(0)

        # ===== TOP BAR =====
        top_bar = QWidget()
        top_bar.setFixedHeight(50)
        top_bar.setStyleSheet("background: transparent;")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(10, 0, 10, 0)

        # Logo / Title
        logo = QLabel("⚡ JARVIS")
        logo.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        logo.setStyleSheet("color: #00ff9f; letter-spacing: 3px; background: transparent;")
        top_bar_layout.addWidget(logo)

        top_bar_layout.addStretch()

        # Status Label
        self.status_label = QLabel("● READY")
        self.status_label.setFont(QFont("Cascadia Code", 10))
        self.status_label.setStyleSheet("color: #00ffff; background: transparent; padding: 4px 12px;")
        top_bar_layout.addWidget(self.status_label)

        # Terminal Toggle Button
        self.toggle_btn = QPushButton("⌨")
        self.toggle_btn.setFixedSize(40, 40)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background: #1a1a2e;
                color: #8892b0;
                border: 1px solid #233554;
                border-radius: 8px;
                font-size: 18px;
            }
            QPushButton:hover { background: #233554; color: #00ff9f; }
        """)
        self.toggle_btn.clicked.connect(self._toggle_terminal)
        top_bar_layout.addWidget(self.toggle_btn)

        main_layout.addWidget(top_bar)

        # ===== HERO SECTION (Orb + Status) =====
        hero = QWidget()
        hero.setStyleSheet("background: transparent;")
        hero.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Orb
        self.visuals = ThinkingOrb()
        self.visuals.setFixedSize(250, 250)

        # Glow shadow effect on orb
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(60)
        shadow.setColor(QColor(0, 255, 255, 80))
        shadow.setOffset(0, 0)
        self.visuals.setGraphicsEffect(shadow)

        hero_layout.addWidget(self.visuals, alignment=Qt.AlignmentFlag.AlignCenter)

        # State text below orb
        self.state_text = QLabel("How can I help you?")
        self.state_text.setFont(QFont("Segoe UI", 14))
        self.state_text.setStyleSheet("color: #8892b0; background: transparent; margin-top: 10px;")
        self.state_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(self.state_text)

        # Listening indicator (replaces mic button - system is fully autonomous)
        self.listen_indicator = QLabel("🔊 AUTONOMOUS MODE")
        self.listen_indicator.setFont(QFont("Cascadia Code", 9))
        self.listen_indicator.setStyleSheet("""
            color: #00ffff;
            background: rgba(0, 255, 255, 15);
            border: 1px solid rgba(0, 255, 255, 40);
            border-radius: 12px;
            padding: 6px 16px;
        """)
        self.listen_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(self.listen_indicator, alignment=Qt.AlignmentFlag.AlignCenter)

        main_layout.addWidget(hero, 1)

        # ===== TERMINAL DRAWER (Collapsible) =====
        self.terminal_container = QWidget()
        self.terminal_container.setMaximumHeight(300)
        self.terminal_container.setStyleSheet("""
            background: #0d1117;
            border: 1px solid #1a1a2e;
            border-radius: 10px;
        """)
        tc_layout = QVBoxLayout(self.terminal_container)
        tc_layout.setContentsMargins(4, 4, 4, 4)

        self.terminal = Terminal()
        tc_layout.addWidget(self.terminal)

        main_layout.addWidget(self.terminal_container)

    def _toggle_terminal(self):
        """Slide terminal drawer open/closed."""
        if self.terminal_visible:
            self.terminal_container.setMaximumHeight(0)
            self.terminal_container.hide()
            self.terminal_visible = False
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background: #233554;
                    color: #00ff9f;
                    border: 1px solid #00ff9f;
                    border-radius: 8px;
                    font-size: 18px;
                }
                QPushButton:hover { background: #1a1a2e; }
            """)
        else:
            self.terminal_container.show()
            self.terminal_container.setMaximumHeight(300)
            self.terminal_visible = True
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background: #1a1a2e;
                    color: #8892b0;
                    border: 1px solid #233554;
                    border-radius: 8px;
                    font-size: 18px;
                }
                QPushButton:hover { background: #233554; color: #00ff9f; }
            """)

    def update_status(self, state_name):
        """Update the status label and state text based on listener state."""
        if state_name == "listening":
            self.status_label.setText("● LISTENING")
            self.status_label.setStyleSheet("color: #00ff9f; background: transparent; padding: 4px 12px;")
            self.state_text.setText("I'm listening...")
        elif state_name == "processing":
            self.status_label.setText("● THINKING")
            self.status_label.setStyleSheet("color: #ff79c6; background: transparent; padding: 4px 12px;")
            self.state_text.setText("Processing your request...")
        else:
            self.status_label.setText("● READY")
            self.status_label.setStyleSheet("color: #00ffff; background: transparent; padding: 4px 12px;")
            self.state_text.setText("How can I help you?")

    def append_terminal_output(self, text):
        """Thread-safe terminal output (called via signal from main thread)."""
        self.terminal.append_output(text)

    def play_audio(self, file_path):
        """Plays audio from the given file path using QMediaPlayer."""
        try:
            url = QUrl.fromLocalFile(file_path)
            self.player.setSource(url)
            self.player.play()
        except Exception as e:
            self.terminal.append_output(f"Audio Error: {e}")
