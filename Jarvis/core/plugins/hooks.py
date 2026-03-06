"""
Plugin Hooks — Convenience decorators for lightweight hook registration.
=========================================================================
Alternative to full JarvisPlugin subclass for simple hook functions.

Usage:
    from Jarvis.core.plugins.hooks import on_command, on_response

    @on_command(priority=10)
    def my_handler(command: str) -> Optional[str]:
        if "hello" in command.lower():
            return "Hi from my plugin!"
        return None
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("jarvis.plugins.hooks")


@dataclass
class _HookEntry:
    func: Callable
    priority: int = 0
    name: str = ""


class HookManager:
    """Manages lightweight function-based hooks (alternative to full plugin classes)."""

    def __init__(self):
        self._command_hooks: list[_HookEntry] = []
        self._response_hooks: list[_HookEntry] = []
        self._tts_hooks: list[_HookEntry] = []
        self._stt_hooks: list[_HookEntry] = []

    def register_command_hook(self, func: Callable, priority: int = 0, name: str = "") -> None:
        self._command_hooks.append(_HookEntry(func=func, priority=priority, name=name or func.__name__))
        self._command_hooks.sort(key=lambda h: -h.priority)

    def register_response_hook(self, func: Callable, priority: int = 0, name: str = "") -> None:
        self._response_hooks.append(_HookEntry(func=func, priority=priority, name=name or func.__name__))
        self._response_hooks.sort(key=lambda h: -h.priority)

    def dispatch_command(self, command: str) -> Optional[str]:
        for hook in self._command_hooks:
            try:
                result = hook.func(command)
                if result is not None:
                    return result
            except Exception as e:
                logger.error("Command hook [%s] failed: %s", hook.name, e)
        return None

    def dispatch_response(self, command: str, response: str) -> str:
        for hook in self._response_hooks:
            try:
                response = hook.func(command, response)
            except Exception as e:
                logger.error("Response hook [%s] failed: %s", hook.name, e)
        return response

    def dispatch_tts(self, text: str) -> str:
        for hook in self._tts_hooks:
            try:
                text = hook.func(text)
            except Exception as e:
                logger.error("TTS hook [%s] failed: %s", hook.name, e)
        return text

    def dispatch_stt(self, transcript: str) -> str:
        for hook in self._stt_hooks:
            try:
                transcript = hook.func(transcript)
            except Exception as e:
                logger.error("STT hook [%s] failed: %s", hook.name, e)
        return transcript


# ── Global singleton ────────────────────────────────────────────────────

_manager = HookManager()


def on_command(priority: int = 0, name: str = ""):
    """Decorator to register a command hook function."""
    def decorator(func):
        _manager.register_command_hook(func, priority, name)
        return func
    return decorator


def on_response(priority: int = 0, name: str = ""):
    """Decorator to register a response hook function."""
    def decorator(func):
        _manager.register_response_hook(func, priority, name)
        return func
    return decorator


def get_hook_manager() -> HookManager:
    return _manager
