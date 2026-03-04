"""
Terminal Window Module
=======================
Separate PyQt6 window for displaying Jarvis command execution and output.
Inspired by Gemini CLI with a read-only terminal interface.
"""

import sys
from datetime import datetime
from collections import deque
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTextEdit, QLabel, QFrame, QApplication)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QTextCursor, QTextCharFormat, QFontDatabase

from Jarvis.ui.terminal_branding import (
    get_startup_header, get_ready_message, get_divider, 
    create_command_block, create_output_block, get_jarvis_banner,
    colorize_text, StatusColor, Colors
)


class TerminalWindow(QMainWindow):
    """
    Separate terminal window displaying command execution and output.
    - Read-only display
    - Real-time command/output updates
    - Gemini-style theming
    - Auto-scrolling
    """
    
    # Signals to receive command execution events
    command_executed = pyqtSignal(str, str)  # command, output
    status_changed = pyqtSignal(str, str)    # status_type, message
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis Terminal")
        self.resize(900, 600)
        
        # Command history for display
        self.command_history = deque(maxlen=500)  # Store last 500 commands
        self.display_count = 0
        
        # ─── Setup UI ───────────────────────────────────────────────────
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ─── Header Frame ───────────────────────────────────────────────
        self.header = QFrame()
        self.header.setFixedHeight(140)
        self.header.setStyleSheet("""
            QFrame {
                background: #0a0e17;
                border-bottom: 1px solid #1a2940;
            }
        """)
        header_layout = QVBoxLayout(self.header)
        header_layout.setContentsMargins(0, 5, 0, 5)
        header_layout.setSpacing(2)
        
        # Logo/Title (using text instead of rendering)
        self.logo_label = QLabel()
        self.logo_label.setFont(QFont("Courier New", 9))
        self.logo_label.setStyleSheet("""
            QLabel {
                color: #00ff9f;
                background: transparent;
                border: none;
            }
        """)
        self.logo_label.setText(self._get_header_text())
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.logo_label)
        
        # Status bar
        self.status_label = QLabel("● Ready")
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setStyleSheet("""
            QLabel {
                color: #00ff9f;
                background: transparent;
                border: none;
                padding: 0px 10px;
            }
        """)
        header_layout.addWidget(self.status_label)
        
        main_layout.addWidget(self.header)
        
        # ─── Output Display Area ────────────────────────────────────────
        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setStyleSheet("""
            QTextEdit {
                background: #0f0f1a;
                color: #8892b0;
                border: none;
                border-left: 1px solid #233554;
                padding: 10px;
                margin: 0px;
            }
            QTextEdit::vertical-scrollbar {
                background: #1a1a2e;
                width: 12px;
                border-radius: 6px;
            }
            QTextEdit::vertical-scrollbar:handle {
                background: #233554;
                border-radius: 6px;
            }
            QTextEdit::vertical-scrollbar:handle:hover {
                background: #2a4070;
            }
        """)
        
        # Use monospace font for terminal
        font = QFont()
        font.setFamily("Consolas" if sys.platform == "win32" else "Courier New")
        font.setPointSize(9)
        self.output_display.setFont(font)
        
        main_layout.addWidget(self.output_display, 1)
        
        # ─── Info Footer ────────────────────────────────────────────────
        self.footer = QFrame()
        self.footer.setFixedHeight(30)
        self.footer.setStyleSheet("""
            QFrame {
                background: #0a0e17;
                border-top: 1px solid #1a2940;
            }
        """)
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(10, 0, 10, 0)
        
        self.command_count_label = QLabel("Commands: 0")
        self.command_count_label.setFont(QFont("Segoe UI", 8))
        self.command_count_label.setStyleSheet("""
            QLabel {
                color: #5a6f7d;
                background: transparent;
                border: none;
            }
        """)
        footer_layout.addWidget(self.command_count_label)
        
        footer_layout.addStretch()
        
        self.info_label = QLabel("Ready")
        self.info_label.setFont(QFont("Segoe UI", 8))
        self.info_label.setStyleSheet("""
            QLabel {
                color: #00ff9f;
                background: transparent;
                border: none;
            }
        """)
        footer_layout.addWidget(self.info_label)
        
        main_layout.addWidget(self.footer)
        
        # ─── Display initial header ─────────────────────────────────────
        self._init_display()
    
    def _get_header_text(self):
        """Get the header text (simplified for rich text display)."""
        return "JARVIS - Autonomous AI Command Terminal"
    
    def _init_display(self):
        """Initialize the terminal display with header."""
        self.output_display.clear()
        self._append_text(self._get_header_text(), color="#00ff9f", bold=True)
        self._append_text("\n")
        divider = get_divider(width=80)
        self._append_text(divider, color="#1a2940")
        self._append_text("\n")
        self._append_text("Terminal ready for command execution", color="#00ff9f")
        self._append_text("\n\n")
    
    def append_command(self, command_text, timestamp=None):
        """
        Append a command to the display.
        
        Args:
            command_text: The command being executed
            timestamp: Optional timestamp (auto-generated if not provided)
        """
        if timestamp is None:
            timestamp = datetime.now().strftime("%H:%M:%S")
        
        self.display_count += 1
        
        # Command line
        prompt = f"  [{timestamp}]"
        self._append_text(prompt, color="#5a6f7d")
        self._append_text(" [EXEC] ", color="#00ffff", bold=True)
        self._append_text(f"{command_text}\n", color="#00ffff")
        
        # Store in history
        self.command_history.append({
            'command': command_text,
            'timestamp': timestamp
        })
        
        # Update footer
        self.command_count_label.setText(f"Commands: {self.display_count}")
        
        # Auto-scroll to bottom
        self._scroll_to_bottom()
    
    def append_output(self, output_text, is_error=False):
        """
        Append command output to the display.
        
        Args:
            output_text: The output from the command
            is_error: Whether this is error output (red) or normal output (white)
        """
        if not output_text:
            return
        
        color = "#ff6b6b" if is_error else "#e8e8e8"
        
        # Split output into lines and display each
        for line in output_text.split('\n'):
            if line.strip():
                self._append_text(f"  {line}\n", color=color)
        
        # Add divider after output
        divider = get_divider(width=80)
        self._append_text(f"\n{divider}\n\n", color="#1a2940")
        
        # Auto-scroll to bottom
        self._scroll_to_bottom()
    
    def update_status(self, status_text, status_type="normal"):
        """
        Update the status label.
        
        Args:
            status_text: The status message
            status_type: Type of status (listening, processing, error, normal)
        """
        status_colors = {
            "listening": "#00ff9f",
            "processing": "#ffff00",
            "error": "#ff6b6b",
            "normal": "#00ff9f"
        }
        
        color = status_colors.get(status_type, "#00ff9f")
        
        # Icon based on status
        icons = {
            "listening": "●",
            "processing": "⟳",
            "error": "✗",
            "normal": "●"
        }
        icon = icons.get(status_type, "●")
        
        self.status_label.setText(f"{icon} {status_text}")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background: transparent;
                border: none;
                padding: 0px 10px;
            }}
        """)
        
        self.info_label.setText(f"Status: {status_type}")
    
    def _append_text(self, text, color=None, bold=False):
        """
        Append text to the output display with optional formatting.
        
        Args:
            text: Text to append
            color: Hex color code (e.g., "#00ff9f")
            bold: Whether to make text bold
        """
        cursor = self.output_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Create text format
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(700)
        
        cursor.setCharFormat(fmt)
        cursor.insertText(text)
        
        self.output_display.setTextCursor(cursor)
    
    def _scroll_to_bottom(self):
        """Scroll the output display to the bottom."""
        cursor = self.output_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_display.setTextCursor(cursor)
    
    def clear_output(self):
        """Clear all output and reset display."""
        self.output_display.clear()
        self.display_count = 0
        self.command_history.clear()
        self._init_display()
        self.command_count_label.setText("Commands: 0")
    
    def closeEvent(self, event):
        """Hide instead of destroying so it can be re-shown."""
        event.ignore()
        self.hide()


def create_terminal_window():
    """Factory function to create and return a terminal window instance."""
    return TerminalWindow()


if __name__ == "__main__":
    # Test/demo code
    app = QApplication(sys.argv)
    term = TerminalWindow()
    term.show()
    
    # Simulate some commands
    term.append_command("Get-Process | Where-Object {$_.Name -eq 'notepad'}")
    term.append_output("""Handles  NPM(K)    PM(M)      WS(M)  CPU(s)     Id  SI ProcessName
─────  ──────    ─────      ─────  ──────     ──  ── ───────────
   247      12    45.23      89.56   1.23   5432   1  notepad""")
    
    term.update_status("Processing command", "processing")
    
    sys.exit(app.exec())
