"""
Terminal Window Module
=======================
Separate PyQt6 window for displaying Jarvis command execution and output.
Refined world-class aesthetic matching the new dashboard.
"""

import sys
from datetime import datetime
from collections import deque
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTextEdit, QLabel, QFrame, QApplication)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QTextCursor, QTextCharFormat, QFontDatabase

from Jarvis.ui import design_tokens as dt
from Jarvis.ui.terminal_branding import (
    get_startup_header, get_ready_message, get_divider, 
    create_command_block, create_output_block, get_jarvis_banner,
    colorize_text, StatusColor, Colors
)


class TerminalWindow(QMainWindow):
    """
    Separate terminal window displaying command execution and output.
    Refined world-class aesthetic.
    """
    
    command_executed = pyqtSignal(str, str)
    status_changed = pyqtSignal(str, str)
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis Terminal")
        self.resize(1000, 700)
        
        self.command_history = deque(maxlen=500)
        self.display_count = 0
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.central_widget.setStyleSheet(f"background: {dt.BG_BASE};")
        
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ─── Header Frame ───────────────────────────────────────────────
        self.header = QFrame()
        self.header.setFixedHeight(64)
        self.header.setStyleSheet(f"""
            QFrame {{
                background: rgba(2, 6, 23, 0.8);
                border-bottom: 1px solid {dt.BORDER_DEFAULT};
            }}
        """)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 0, 20, 0)
        
        # Title/Logo
        self.title_label = QLabel("󰆍  JARVIS TERMINAL")
        self.title_label.setFont(QFont(dt.FONT_FAMILY, 11, QFont.Weight.Black))
        self.title_label.setStyleSheet(f"color: {dt.TEXT_PRIMARY}; letter-spacing: 2px; border: none;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        # Status bar
        self.status_label = QLabel("●  SYSTEM READY")
        self.status_label.setFont(QFont(dt.FONT_FAMILY, 9, QFont.Weight.Bold))
        self.status_label.setStyleSheet(f"color: {dt.SUCCESS}; border: none;")
        header_layout.addWidget(self.status_label)
        
        main_layout.addWidget(self.header)
        
        # ─── Output Display Area ────────────────────────────────────────
        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setStyleSheet(f"""
            QTextEdit {{
                background: {dt.BG_BASE};
                color: {dt.TEXT_SECONDARY};
                border: none;
                padding: 24px;
                line-height: 1.6;
            }}
            QTextEdit::vertical-scrollbar {{
                background: transparent;
                width: 8px;
            }}
            QTextEdit::vertical-scrollbar:handle {{
                background: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }}
        """)
        
        # Use monospace font for terminal
        font = QFont()
        font.setFamily(dt.FONT_FAMILY_MONO)
        font.setPointSize(10)
        self.output_display.setFont(font)
        
        main_layout.addWidget(self.output_display, 1)
        
        # ─── Info Footer ────────────────────────────────────────────────
        self.footer = QFrame()
        self.footer.setFixedHeight(36)
        self.footer.setStyleSheet(f"""
            QFrame {{
                background: rgba(2, 6, 23, 0.8);
                border-top: 1px solid {dt.BORDER_DEFAULT};
            }}
        """)
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(20, 0, 20, 0)
        
        self.command_count_label = QLabel("COMMANDS: 0")
        self.command_count_label.setFont(QFont(dt.FONT_FAMILY, 8, QFont.Weight.Bold))
        self.command_count_label.setStyleSheet(f"color: {dt.TEXT_MUTED}; letter-spacing: 1px;")
        footer_layout.addWidget(self.command_count_label)
        
        footer_layout.addStretch()
        
        self.info_label = QLabel("IDLE")
        self.info_label.setFont(QFont(dt.FONT_FAMILY, 8, QFont.Weight.Bold))
        self.info_label.setStyleSheet(f"color: {dt.ACCENT}; letter-spacing: 1px;")
        footer_layout.addWidget(self.info_label)
        
        main_layout.addWidget(self.footer)
        
        # ─── Display initial header ─────────────────────────────────────
        self._init_display()
    
    def _init_display(self):
        """Initialize the terminal display with header."""
        self.output_display.clear()
        self._append_text("JARVIS CORE v2.2 - SECURE COMMAND INTERFACE\n", color=dt.ACCENT, bold=True)
        self._append_text("Session initialized. All systems nominal.\n", color=dt.TEXT_MUTED)
        self._append_text("─" * 60 + "\n\n", color=dt.BORDER_DEFAULT)
    
    def append_command(self, command_text, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now().strftime("%H:%M:%S")
        
        self.display_count += 1
        
        self._append_text(f"[{timestamp}] ", color=dt.TEXT_MUTED)
        self._append_text("󰅩  EXEC  ", color=dt.INFO, bold=True)
        self._append_text(f"{command_text}\n", color=dt.TEXT_PRIMARY)
        
        self.command_history.append({'command': command_text, 'timestamp': timestamp})
        self.command_count_label.setText(f"COMMANDS: {self.display_count}")
        self._scroll_to_bottom()
    
    def append_output(self, output_text, is_error=False):
        if not output_text:
            return
        
        color = dt.ERROR if is_error else dt.TEXT_SECONDARY
        prefix = "󰅚  ERROR " if is_error else "󰄬  INFO  "
        
        self._append_text(f"      {prefix}", color=color, bold=True)
        
        # Indent output lines
        first = True
        for line in output_text.split('\n'):
            if not first:
                self._append_text("              ", color=color)
            self._append_text(f"{line}\n", color=color)
            first = False
        
        self._append_text("\n", color=color)
        self._scroll_to_bottom()
    
    def update_status(self, status_text, status_type="normal"):
        status_colors = {
            "listening": dt.SUCCESS,
            "processing": dt.WARNING,
            "error": dt.ERROR,
            "normal": dt.SUCCESS
        }
        
        color = status_colors.get(status_type, dt.SUCCESS)
        icons = {
            "listening": "󰍬",
            "processing": "󰚩",
            "error": "󰅚",
            "normal": "●"
        }
        icon = icons.get(status_type, "●")
        
        self.status_label.setText(f"{icon}  {status_text.upper()}")
        self.status_label.setStyleSheet(f"color: {color}; border: none;")
        self.info_label.setText(status_type.upper())
    
    def _append_text(self, text, color=None, bold=False):
        cursor = self.output_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(700)
        
        cursor.setCharFormat(fmt)
        cursor.insertText(text)
        self.output_display.setTextCursor(cursor)
    
    def _scroll_to_bottom(self):
        cursor = self.output_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_display.setTextCursor(cursor)
    
    def clear_output(self):
        self.output_display.clear()
        self.display_count = 0
        self.command_history.clear()
        self._init_display()
        self.command_count_label.setText("COMMANDS: 0")
    
    def closeEvent(self, event):
        event.ignore()
        self.hide()


def create_terminal_window():
    return TerminalWindow()
