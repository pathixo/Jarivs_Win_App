"""
Compute Protocol — WebSocket message format for distributed compute.
======================================================================
Defines the message types and serialization for communication between
compute nodes and the dispatcher.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any


class MessageType(str, Enum):
    # Node → Dispatcher
    REGISTER = "register"          # Node announces itself
    HEARTBEAT = "heartbeat"        # Periodic alive signal
    TASK_RESULT = "task_result"    # Completed task result
    TASK_ERROR = "task_error"      # Task failed

    # Dispatcher → Node
    TASK_ASSIGN = "task_assign"    # Assign a task to a node
    TASK_CANCEL = "task_cancel"    # Cancel a running task
    STATUS_REQUEST = "status_request"
    ACK = "ack"


@dataclass
class NodeInfo:
    """Information about a compute node."""
    node_id: str
    hostname: str
    ip: str
    port: int
    capabilities: list[str] = field(default_factory=list)  # e.g. ["ollama", "gpu", "tts"]
    max_concurrent: int = 2
    vram_mb: int = 0
    status: str = "idle"  # idle, busy, offline


@dataclass
class TaskMessage:
    """A compute task to be distributed."""
    task_id: str
    task_type: str              # "llm_inference", "tts", "ocr", "image_gen"
    payload: dict = field(default_factory=dict)
    priority: int = 0           # Higher = more urgent
    timeout_s: float = 30.0
    assigned_node: str = ""
    created_at: float = 0.0
    completed_at: float = 0.0
    result: Any = None
    error: Optional[str] = None


@dataclass
class ProtocolMessage:
    """Wire-format message for WebSocket communication."""
    msg_type: MessageType
    sender_id: str
    timestamp: float = 0.0
    data: dict = field(default_factory=dict)

    def serialize(self) -> str:
        return json.dumps({
            "type": self.msg_type.value,
            "sender": self.sender_id,
            "ts": self.timestamp or time.time(),
            "data": self.data,
        })

    @classmethod
    def deserialize(cls, raw: str) -> "ProtocolMessage":
        parsed = json.loads(raw)
        return cls(
            msg_type=MessageType(parsed["type"]),
            sender_id=parsed["sender"],
            timestamp=parsed.get("ts", 0),
            data=parsed.get("data", {}),
        )
