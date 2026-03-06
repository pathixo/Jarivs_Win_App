"""
Workflow Recorder — Records user UI interactions into replayable workflows.
============================================================================
Captures mouse clicks, keyboard input, and window focus changes using pynput.
Stores workflows as JSON sequences with timing information.

Features:
  - Record mouse clicks (position, button)
  - Record keyboard input (key sequences, hotkeys)
  - Timestamp each action relative to workflow start
  - Save/load workflows as JSON
  - Interrupt/resume recording
"""

import json
import logging
import os
import time
import threading
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from pathlib import Path

logger = logging.getLogger("jarvis.workflows.recorder")


class ActionKind(str, Enum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    KEY_PRESS = "key_press"
    KEY_COMBO = "key_combo"
    TYPE_TEXT = "type_text"
    SCROLL = "scroll"
    WAIT = "wait"


@dataclass
class WorkflowAction:
    """A single recorded action."""
    kind: ActionKind
    timestamp_ms: float           # ms since workflow start
    x: int = 0
    y: int = 0
    key: str = ""                 # single key or combo like "ctrl+s"
    text: str = ""                # for TYPE_TEXT
    scroll_amount: int = 0        # for SCROLL
    metadata: dict = field(default_factory=dict)


@dataclass
class Workflow:
    """A recorded sequence of UI actions."""
    name: str
    description: str = ""
    actions: list[WorkflowAction] = field(default_factory=list)
    created_at: float = 0.0
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "total_duration_ms": self.total_duration_ms,
            "actions": [asdict(a) for a in self.actions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Workflow":
        actions = [
            WorkflowAction(
                kind=ActionKind(a["kind"]),
                timestamp_ms=a["timestamp_ms"],
                x=a.get("x", 0),
                y=a.get("y", 0),
                key=a.get("key", ""),
                text=a.get("text", ""),
                scroll_amount=a.get("scroll_amount", 0),
                metadata=a.get("metadata", {}),
            )
            for a in data.get("actions", [])
        ]
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            actions=actions,
            created_at=data.get("created_at", 0),
            total_duration_ms=data.get("total_duration_ms", 0),
        )

    def save(self, directory: str) -> str:
        """Save workflow to a JSON file. Returns the file path."""
        os.makedirs(directory, exist_ok=True)
        safe_name = self.name.replace(" ", "_").lower()
        filepath = os.path.join(directory, f"{safe_name}.json")
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return filepath

    @classmethod
    def load(cls, filepath: str) -> "Workflow":
        """Load a workflow from a JSON file."""
        with open(filepath) as f:
            return cls.from_dict(json.load(f))


class WorkflowRecorder:
    """
    Records user interactions via pynput.

    Usage:
        recorder = WorkflowRecorder("my_workflow")
        recorder.start()
        # ... user performs actions ...
        recorder.stop()
        workflow = recorder.get_workflow()
        workflow.save("workflows/")
    """

    def __init__(self, name: str = "untitled", description: str = ""):
        self._name = name
        self._description = description
        self._actions: list[WorkflowAction] = []
        self._start_time: float = 0
        self._recording = False
        self._paused = False
        self._mouse_listener = None
        self._keyboard_listener = None
        self._text_buffer = ""
        self._text_timer = None
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def is_paused(self) -> bool:
        return self._paused

    def start(self) -> None:
        """Start recording user interactions."""
        try:
            from pynput import mouse, keyboard
        except ImportError:
            raise ImportError("pynput required for recording. pip install pynput")

        self._actions = []
        self._start_time = time.time()
        self._recording = True
        self._paused = False

        # Mouse listener
        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._mouse_listener.start()

        # Keyboard listener
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
        )
        self._keyboard_listener.start()

        logger.info("Recording started: %s", self._name)

    def stop(self) -> Workflow:
        """Stop recording and return the workflow."""
        self._recording = False
        self._flush_text_buffer()

        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()

        duration = (time.time() - self._start_time) * 1000
        logger.info("Recording stopped: %s (%d actions, %.0fms)",
                     self._name, len(self._actions), duration)

        return Workflow(
            name=self._name,
            description=self._description,
            actions=self._actions,
            created_at=self._start_time,
            total_duration_ms=duration,
        )

    def pause(self) -> None:
        """Pause recording (actions are ignored until resume)."""
        self._paused = True

    def resume(self) -> None:
        """Resume a paused recording."""
        self._paused = False

    def _elapsed_ms(self) -> float:
        return (time.time() - self._start_time) * 1000

    def _on_click(self, x, y, button, pressed):
        if not self._recording or self._paused or not pressed:
            return

        self._flush_text_buffer()
        kind = ActionKind.CLICK
        if hasattr(button, "name") and button.name == "right":
            kind = ActionKind.RIGHT_CLICK

        with self._lock:
            self._actions.append(WorkflowAction(
                kind=kind,
                timestamp_ms=self._elapsed_ms(),
                x=int(x),
                y=int(y),
            ))

    def _on_scroll(self, x, y, dx, dy):
        if not self._recording or self._paused:
            return

        self._flush_text_buffer()
        with self._lock:
            self._actions.append(WorkflowAction(
                kind=ActionKind.SCROLL,
                timestamp_ms=self._elapsed_ms(),
                x=int(x),
                y=int(y),
                scroll_amount=int(dy),
            ))

    def _on_key_press(self, key):
        if not self._recording or self._paused:
            return

        try:
            char = key.char
            if char:
                self._text_buffer += char
                return
        except AttributeError:
            pass

        # Special key — flush any pending text, then record the key
        self._flush_text_buffer()

        key_name = str(key).replace("Key.", "")
        with self._lock:
            self._actions.append(WorkflowAction(
                kind=ActionKind.KEY_PRESS,
                timestamp_ms=self._elapsed_ms(),
                key=key_name,
            ))

    def _flush_text_buffer(self):
        if self._text_buffer:
            with self._lock:
                self._actions.append(WorkflowAction(
                    kind=ActionKind.TYPE_TEXT,
                    timestamp_ms=self._elapsed_ms(),
                    text=self._text_buffer,
                ))
            self._text_buffer = ""

    def get_workflow(self) -> Workflow:
        """Return the current workflow (even while recording)."""
        return Workflow(
            name=self._name,
            description=self._description,
            actions=list(self._actions),
            created_at=self._start_time,
            total_duration_ms=self._elapsed_ms() if self._recording else 0,
        )
