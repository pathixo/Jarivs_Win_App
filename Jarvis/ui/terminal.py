from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtGui import QTextCursor
from PyQt6.QtCore import Qt, pyqtSignal

class Terminal(QTextEdit):
    command_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(False) 
        self.setStyleSheet("background-color: #1e1e1e; color: #00FF00; font-family: 'Consolas', monospace; font-size: 14px; border: none;")
        self.append("Jarvis Terminal v1.0")
        self.insertPlainText("> ")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return:
            # Get the current line content
            full_text = self.toPlainText()
            lines = full_text.split('\n')
            last_line = lines[-1] if lines else ""
            
            if last_line.startswith("> "):
                command = last_line[2:].strip()
                if command:
                    self.command_signal.emit(command)
            
            # Start new line with prompt
            self.append("") 
            self.insertPlainText("> ")
        elif event.key() == Qt.Key.Key_Backspace:
            # Prevent deleting the prompt
            cursor = self.textCursor()
            if cursor.positionInBlock() > 2:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def append_output(self, text):
        self.moveCursor(QTextCursor.MoveOperation.End)
        # Ensure we are on a new line before appending output
        if not self.toPlainText().endswith('\n> '):
             self.insertPlainText("\n")
        
        # Remove the last prompt if it exists (since we are appending output)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine, QTextCursor.MoveMode.KeepAnchor)
        if cursor.selectedText() == "> ":
            cursor.removeSelectedText()
            
        self.insertPlainText(text + "\n> ")
        self.ensureCursorVisible()
