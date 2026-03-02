"""
Terminal Bridge Module
======================
Inter-process communication bridge between the main Jarvis app and the terminal window.
Handles signals for command execution, output relay, and status updates.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class TerminalBridge(QObject):
    """
    Thread-safe signal bridge for communication between Jarvis orchestrator and terminal window.
    
    Signals:
    - command_to_execute: Emitted when orchestrator executes a shell command
    - output_ready: Emitted when command produces output
    - status_update: Emitted when execution status changes
    """
    
    # Signal: command_text -> relay to terminal
    command_to_execute = pyqtSignal(str)  # command text
    
    # Signal: (command_text, output_text, is_error)
    output_ready = pyqtSignal(str, str, bool)
    
    # Signal: (status_text, status_type)  status_type in [listening, processing, error, normal]
    status_update = pyqtSignal(str, str)
    
    # Signal: (timestamp, command, output)
    command_executed = pyqtSignal(str, str, str)
    
    def __init__(self):
        super().__init__()
    
    def on_command_started(self, command_text):
        """Called when orchestrator starts executing a command."""
        self.command_to_execute.emit(command_text)
        self.status_update.emit("Executing command...", "processing")
    
    def on_command_output(self, command_text, output_text, is_error=False):
        """Called when orchestrator receives command output."""
        self.output_ready.emit(command_text, output_text, is_error)
    
    def on_command_completed(self, command_text, output_text, is_error=False):
        """Called when orchestrator completes command execution."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.command_executed.emit(timestamp, command_text, output_text)
        
        status = "Command completed" if not is_error else "Command failed"
        status_type = "error" if is_error else "normal"
        self.status_update.emit(status, status_type)
    
    def on_status_changed(self, status_text, status_type="normal"):
        """Called when Jarvis status changes (listening, thinking, etc.)."""
        self.status_update.emit(status_text, status_type)
    
    def on_listener_state_changed(self, state):
        """Called when listener state changes (from listener module)."""
        state_map = {
            "initialized": ("Initializing...", "processing"),
            "listening": ("● Ready to listen", "listening"),
            "recording": ("🔴 Recording audio", "processing"),
            "processing": ("⟳ Processing audio", "processing"),
            "paused": ("⏸ Paused", "normal"),
            "error": ("✗ Listener error", "error"),
        }
        
        status_text, status_type = state_map.get(state, (f"State: {state}", "normal"))
        self.status_update.emit(status_text, status_type)


# Global terminal bridge instance
_terminal_bridge = None


def get_terminal_bridge():
    """Get or create the global terminal bridge instance."""
    global _terminal_bridge
    if _terminal_bridge is None:
        _terminal_bridge = TerminalBridge()
    return _terminal_bridge


def set_terminal_bridge(bridge):
    """Set the global terminal bridge instance."""
    global _terminal_bridge
    _terminal_bridge = bridge
