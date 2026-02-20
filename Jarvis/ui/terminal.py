from PyQt6.QtWidgets import QTextEdit, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtGui import QTextCursor, QFont, QColor, QTextCharFormat
from PyQt6.QtCore import Qt, pyqtSignal, QTimer


class Terminal(QWidget):
    """
    Premium terminal widget with real terminal aesthetics,
    command history, and AI write access.
    """
    command_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.command_history = []
        self.history_index = -1
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Terminal header bar
        header = QWidget()
        header.setFixedHeight(32)
        header.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #1a1a2e, stop:1 #16213e);
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)

        # Terminal dots (macOS style)
        for color in ["#ff5f57", "#febc2e", "#28c840"]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 10px; background: transparent;")
            header_layout.addWidget(dot)

        title = QLabel("  JARVIS TERMINAL")
        title.setStyleSheet("""
            color: #8892b0;
            font-family: 'Cascadia Code', 'Consolas', monospace;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 2px;
            background: transparent;
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()

        layout.addWidget(header)

        # Terminal body
        self.output = QTextEdit()
        self.output.setReadOnly(False)
        self.output.setFont(QFont("Cascadia Code", 12))
        self.output.setStyleSheet("""
            QTextEdit {
                background-color: #0a0e17;
                color: #a8b2d1;
                border: 1px solid #1a1a2e;
                border-top: none;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                padding: 8px 12px;
                selection-background-color: #233554;
            }
            QScrollBar:vertical {
                background: #0a0e17;
                width: 8px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #233554;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Welcome message
        self.output.setTextColor(QColor("#00ff9f"))
        self.output.append("╔══════════════════════════════════════════╗")
        self.output.append("║         JARVIS TERMINAL v2.0             ║")
        self.output.append("║   Type 'help' for available commands     ║")
        self.output.append("╚══════════════════════════════════════════╝")
        self.output.setTextColor(QColor("#a8b2d1"))
        self.output.append("")
        self._insert_prompt()

        layout.addWidget(self.output)

        # Override key events on the QTextEdit
        self.output.keyPressEvent = self._handle_key

    def _insert_prompt(self):
        """Insert the command prompt."""
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output.setTextCursor(cursor)

        # Prompt with color
        fmt_user = QTextCharFormat()
        fmt_user.setForeground(QColor("#00ff9f"))
        cursor.insertText("jarvis", fmt_user)

        fmt_arrow = QTextCharFormat()
        fmt_arrow.setForeground(QColor("#ff79c6"))
        cursor.insertText(" ❯ ", fmt_arrow)

        fmt_default = QTextCharFormat()
        fmt_default.setForeground(QColor("#e6e6e6"))
        cursor.insertText("", fmt_default)

        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def _get_current_command(self):
        """Extract the current command text from the last line."""
        full_text = self.output.toPlainText()
        lines = full_text.split('\n')
        last_line = lines[-1] if lines else ""
        # Find the prompt marker
        if " ❯ " in last_line:
            return last_line.split(" ❯ ", 1)[1]
        return ""

    def _handle_key(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            command = self._get_current_command().strip()
            if command:
                self.command_history.append(command)
                self.history_index = len(self.command_history)
                self.output.append("")  # New line
                self.command_signal.emit(command)
            else:
                self.output.append("")
                self._insert_prompt()

        elif event.key() == Qt.Key.Key_Up:
            # Navigate command history (up)
            if self.command_history and self.history_index > 0:
                self.history_index -= 1
                self._replace_current_command(self.command_history[self.history_index])

        elif event.key() == Qt.Key.Key_Down:
            # Navigate command history (down)
            if self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                self._replace_current_command(self.command_history[self.history_index])
            else:
                self.history_index = len(self.command_history)
                self._replace_current_command("")

        elif event.key() == Qt.Key.Key_Backspace:
            # Don't delete past the prompt
            cursor = self.output.textCursor()
            full_text = self.output.toPlainText()
            lines = full_text.split('\n')
            last_line = lines[-1] if lines else ""
            if " ❯ " in last_line:
                prompt_end = last_line.index(" ❯ ") + 3
                if cursor.positionInBlock() > prompt_end:
                    QTextEdit.keyPressEvent(self.output, event)
        else:
            QTextEdit.keyPressEvent(self.output, event)

    def _replace_current_command(self, text):
        """Replace the current command text with history item."""
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine, QTextCursor.MoveMode.KeepAnchor)
        selected = cursor.selectedText()
        if " ❯ " in selected:
            # Only replace after the prompt
            cursor.movePosition(QTextCursor.MoveOperation.End)
            block_text = cursor.block().text()
            prompt_pos = block_text.index(" ❯ ") + 3
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, prompt_pos)
            cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()

            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#e6e6e6"))
            cursor.insertText(text, fmt)
            self.output.setTextCursor(cursor)

    def append_output(self, text):
        """Append output text to the terminal (thread-safe when called via signal)."""
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output.setTextCursor(cursor)

        # Format based on content
        fmt = QTextCharFormat()
        if text.startswith("Error"):
            fmt.setForeground(QColor("#ff5555"))
        elif text.startswith("Response:"):
            fmt.setForeground(QColor("#8be9fd"))
            text = text.replace("Response: ", "")
        elif text.startswith("Processing:"):
            fmt.setForeground(QColor("#ffb86c"))
        elif text.startswith("Executed:"):
            fmt.setForeground(QColor("#50fa7b"))
        else:
            fmt.setForeground(QColor("#a8b2d1"))

        cursor.insertText(text + "\n", fmt)
        self.output.setTextCursor(cursor)
        self._insert_prompt()
        self.output.ensureCursorVisible()

    def execute_and_display(self, command, output_text):
        """Display a command execution result in the terminal."""
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output.setTextCursor(cursor)

        # Command line
        fmt_cmd = QTextCharFormat()
        fmt_cmd.setForeground(QColor("#50fa7b"))
        cursor.insertText(f"$ {command}\n", fmt_cmd)

        # Output
        fmt_out = QTextCharFormat()
        fmt_out.setForeground(QColor("#a8b2d1"))
        cursor.insertText(output_text + "\n", fmt_out)

        self._insert_prompt()
        self.output.ensureCursorVisible()
