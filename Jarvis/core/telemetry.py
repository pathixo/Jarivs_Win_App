"""
Telemetry Module — Agent State & Pipeline Tracking
===================================================
Provides structured tracking of the agent's internal state,
model usage, and chain-of-thought reasoning.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional
import time

class AgentPhase(Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    ROUTING = "ROUTING"
    THINKING = "THINKING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"

class TelemetryType(Enum):
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    THOUGHT = "THOUGHT"  # Chain of Thought
    TOOL = "TOOL"        # Tool Execution

@dataclass
class TelemetryEvent:
    phase: AgentPhase
    message: str
    type: TelemetryType = TelemetryType.INFO
    provider: Optional[str] = None
    model: Optional[str] = None
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

class TelemetryManager:
    """
    Central manager for emitting telemetry events from the core logic.
    Delegates to the TerminalBridge (PyQt signals) for UI updates.
    """
    def __init__(self, bridge=None):
        self._bridge = bridge
        self.current_phase = AgentPhase.IDLE

    def set_bridge(self, bridge):
        self._bridge = bridge

    def emit(self, phase: AgentPhase, message: str, type: TelemetryType = TelemetryType.INFO, 
             provider: str = None, model: str = None):
        """Emit a telemetry event to the UI."""
        self.current_phase = phase
        if self._bridge:
            # Format: (phase_name, message, type_name, provider, model, timestamp)
            self._bridge.telemetry_event.emit(
                phase.value, 
                message, 
                type.value, 
                provider or "", 
                model or "", 
                time.time()
            )

    def thought(self, thought_text: str, provider: str = None, model: str = None):
        """Emit a thought log (Chain of Thought)."""
        self.emit(AgentPhase.THINKING, thought_text, TelemetryType.THOUGHT, provider, model)

    def tool_start(self, tool_name: str, command: str):
        """Log the start of a tool execution."""
        self.emit(AgentPhase.EXECUTING, f"Executing {tool_name}: {command}", TelemetryType.TOOL)

    def tool_end(self, tool_name: str, output: str, success: bool = True):
        """Log the completion of a tool execution."""
        msg = f"{tool_name} completed."
        t = TelemetryType.SUCCESS if success else TelemetryType.ERROR
        self.emit(AgentPhase.EXECUTING, msg, t)
        if output:
            truncated = output[:200] + "..." if len(output) > 200 else output
            self.emit(AgentPhase.EXECUTING, f"Result: {truncated}", TelemetryType.INFO)

# Global Telemetry Instance
_telemetry = None

def get_telemetry():
    global _telemetry
    if _telemetry is None:
        from Jarvis.core.terminal_bridge import get_terminal_bridge
        _telemetry = TelemetryManager(get_terminal_bridge())
    return _telemetry
