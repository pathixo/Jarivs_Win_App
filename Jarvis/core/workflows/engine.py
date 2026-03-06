"""
Workflow Engine — Replays recorded workflows with timing control.
==================================================================
Replays workflows using pyautogui with configurable timing variations,
interruption support, and step-by-step execution.
"""

import logging
import os
import time
import threading
from typing import Optional, Callable
from pathlib import Path

from Jarvis.core.workflows.recorder import Workflow, WorkflowAction, ActionKind

logger = logging.getLogger("jarvis.workflows.engine")

try:
    import pyautogui
    pyautogui.FAILSAFE = True       # Move mouse to corner to abort
    pyautogui.PAUSE = 0.05          # Small pause between actions
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


class PlaybackState:
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


class WorkflowEngine:
    """
    Replays recorded workflows with precise timing.

    Features:
      - Speed multiplier (0.5x = slow, 2.0x = fast)
      - Step-by-step mode
      - Interrupt/resume
      - Progress callbacks
      - Template loading from the templates directory
    """

    def __init__(self, templates_dir: Optional[str] = None):
        if templates_dir is None:
            templates_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "templates"
            )
        self._templates_dir = templates_dir
        os.makedirs(self._templates_dir, exist_ok=True)

        self._state = PlaybackState.IDLE
        self._current_workflow: Optional[Workflow] = None
        self._current_step: int = 0
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused by default
        self._thread: Optional[threading.Thread] = None
        self._speed = 1.0
        self._on_progress: Optional[Callable] = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def current_step(self) -> int:
        return self._current_step

    @property
    def total_steps(self) -> int:
        return len(self._current_workflow.actions) if self._current_workflow else 0

    def play(
        self,
        workflow: Workflow,
        speed: float = 1.0,
        on_progress: Optional[Callable] = None,
    ) -> None:
        """
        Start replaying a workflow in a background thread.

        Args:
            workflow: The workflow to replay
            speed: Playback speed multiplier (0.5 = half speed, 2.0 = double)
            on_progress: Optional callback(step_index, total_steps, action)
        """
        if not PYAUTOGUI_AVAILABLE:
            raise ImportError("pyautogui required for playback. pip install pyautogui")

        self._current_workflow = workflow
        self._current_step = 0
        self._speed = max(0.1, min(10.0, speed))
        self._on_progress = on_progress
        self._stop_event.clear()
        self._pause_event.set()
        self._state = PlaybackState.RUNNING

        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()
        logger.info("Playback started: %s (speed=%.1fx)", workflow.name, speed)

    def _playback_loop(self):
        """Main playback loop."""
        try:
            actions = self._current_workflow.actions
            prev_ts = 0

            for i, action in enumerate(actions):
                if self._stop_event.is_set():
                    self._state = PlaybackState.STOPPED
                    return

                # Wait for resume if paused
                self._pause_event.wait()

                # Timing: wait the delta between this action and the previous
                delta_ms = action.timestamp_ms - prev_ts
                if delta_ms > 0:
                    adjusted_delay = (delta_ms / 1000.0) / self._speed
                    # Cap maximum delay to 10 seconds (prevents huge waits)
                    adjusted_delay = min(adjusted_delay, 10.0)
                    time.sleep(adjusted_delay)

                prev_ts = action.timestamp_ms
                self._current_step = i

                # Execute the action
                self._execute_action(action)

                # Report progress
                if self._on_progress:
                    try:
                        self._on_progress(i, len(actions), action)
                    except Exception:
                        pass

            self._state = PlaybackState.COMPLETED
            logger.info("Playback completed: %s", self._current_workflow.name)

        except Exception as e:
            self._state = PlaybackState.ERROR
            logger.error("Playback error: %s", e)

    def _execute_action(self, action: WorkflowAction):
        """Execute a single workflow action via pyautogui."""
        try:
            if action.kind == ActionKind.CLICK:
                pyautogui.click(action.x, action.y)

            elif action.kind == ActionKind.DOUBLE_CLICK:
                pyautogui.doubleClick(action.x, action.y)

            elif action.kind == ActionKind.RIGHT_CLICK:
                pyautogui.rightClick(action.x, action.y)

            elif action.kind == ActionKind.KEY_PRESS:
                pyautogui.press(action.key)

            elif action.kind == ActionKind.KEY_COMBO:
                keys = action.key.split("+")
                pyautogui.hotkey(*keys)

            elif action.kind == ActionKind.TYPE_TEXT:
                pyautogui.write(action.text, interval=0.02 / self._speed)

            elif action.kind == ActionKind.SCROLL:
                pyautogui.scroll(action.scroll_amount, action.x, action.y)

            elif action.kind == ActionKind.WAIT:
                time.sleep(action.timestamp_ms / 1000.0 / self._speed)

        except Exception as e:
            logger.warning("Action failed (%s): %s", action.kind, e)

    def pause(self):
        """Pause the current playback."""
        self._pause_event.clear()
        self._state = PlaybackState.PAUSED

    def resume(self):
        """Resume a paused playback."""
        self._pause_event.set()
        self._state = PlaybackState.RUNNING

    def stop(self):
        """Stop playback entirely."""
        self._stop_event.set()
        self._pause_event.set()  # unblock if paused

    # ── Template Management ──────────────────────────────────────────────

    def save_template(self, workflow: Workflow) -> str:
        """Save a workflow as a reusable template."""
        return workflow.save(self._templates_dir)

    def list_templates(self) -> list[str]:
        """List available workflow template names."""
        templates = []
        if os.path.isdir(self._templates_dir):
            for f in os.listdir(self._templates_dir):
                if f.endswith(".json"):
                    templates.append(f[:-5])
        return templates

    def load_template(self, name: str) -> Workflow:
        """Load a workflow template by name."""
        filepath = os.path.join(self._templates_dir, f"{name}.json")
        return Workflow.load(filepath)


# ── Module singleton ────────────────────────────────────────────────────

_engine: Optional[WorkflowEngine] = None


def get_workflow_engine() -> WorkflowEngine:
    global _engine
    if _engine is None:
        _engine = WorkflowEngine()
    return _engine
