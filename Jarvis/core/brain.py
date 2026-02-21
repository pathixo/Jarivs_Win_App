"""
Brain Module — Multi-Provider LLM Interface Layer
===================================================
Provides a unified interface to multiple LLM backends:
  - Ollama  (local, default)
  - Gemini  (Google Cloud)
  - Grok    (xAI Cloud)

Supports conversation memory, chain-of-thought reasoning, retry logic,
provider failover, and structured settings management.
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

import requests

from Jarvis.config import (
    OLLAMA_URL,
    OLLAMA_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROK_API_KEY,
    GROK_MODEL,
    LLM_PROVIDER,
)

logger = logging.getLogger("jarvis.brain")


# ─────────────────────────── Constants ──────────────────────────────────────

class Provider(str, Enum):
    OLLAMA = "ollama"
    GEMINI = "gemini"
    GROK   = "grok"


DEFAULT_SYSTEM_PROMPT = (
    "You are Jarvis, an autonomous AI assistant running on a Windows PC.\n\n"
    "## Core Behavior\n"
    "You EXECUTE tasks — you do not just describe them.\n"
    "When the user asks you to perform an actionable task (create files, folders, "
    "run programs, system commands, open apps, etc.), you MUST output the exact "
    "PowerShell command wrapped in [SHELL] and [/SHELL] tags.\n\n"
    "## Thinking Process\n"
    "Before answering, THINK step-by-step about what the user actually wants:\n"
    "1. What is the user's intent?\n"
    "2. Is this a conversational query or an actionable task?\n"
    "3. If actionable — what is the safest, most correct PowerShell command?\n"
    "4. Could this command be destructive? If so, be cautious.\n\n"
    "## Examples\n"
    "User: create a folder named Pokemon\n"
    "Response: Creating folder 'Pokemon' for you.\n[SHELL]New-Item -ItemType Directory -Name 'Pokemon' -Force[/SHELL]\n\n"
    "User: what time is it\n"
    "Response: Let me check.\n[SHELL]Get-Date -Format 'hh:mm:ss tt'[/SHELL]\n\n"
    "User: open notepad\n"
    "Response: Opening Notepad.\n[SHELL]Start-Process notepad[/SHELL]\n\n"
    "User: list files in Downloads\n"
    "Response: Here are your Downloads:\n"
    "[SHELL]Get-ChildItem $env:USERPROFILE\\Downloads | Format-Table Name, Length, LastWriteTime -AutoSize[/SHELL]\n\n"
    "User: hello / how are you / tell me a joke\n"
    "Response: (just chat naturally, no [SHELL] tags needed)\n\n"
    "## Rules\n"
    "- ALWAYS use [SHELL]...[/SHELL] for any actionable request.\n"
    "- Use PowerShell syntax (Windows). Prefer modern cmdlets over legacy aliases.\n"
    "- Keep responses SHORT and direct.\n"
    "- Do NOT ask for confirmation — just do it.\n"
    "- For conversational queries, respond naturally without [SHELL] tags.\n"
    "- If a task could be destructive (delete, format, etc.), warn the user first.\n"
    "- NEVER hallucinate file paths or commands. If unsure, say so.\n"
)


# ─────────────────────────── Settings ───────────────────────────────────────

@dataclass
class BrainSettings:
    """Immutable-ish config snapshot; centralizes all tuning knobs."""
    provider: str = "ollama"
    model: str = OLLAMA_MODEL
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 512
    timeout: int = 60
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_history: int = 20  # conversation memory window

    def validate_temperature(self, value: float) -> bool:
        return 0.0 <= value <= 2.0

    def validate_top_p(self, value: float) -> bool:
        return 0.0 < value <= 1.0

    def validate_max_tokens(self, value: int) -> bool:
        return value > 0

    def validate_timeout(self, value: int) -> bool:
        return value > 0


# ──────────────────────── Conversation Memory ───────────────────────────────

@dataclass
class Message:
    role: str       # "user" | "assistant" | "system"
    content: str
    timestamp: float = field(default_factory=time.time)


class ConversationMemory:
    """Sliding-window conversation buffer for multi-turn context."""

    def __init__(self, max_messages: int = 20):
        self._messages: list[Message] = []
        self._max = max_messages

    def add(self, role: str, content: str) -> None:
        self._messages.append(Message(role=role, content=content))
        # Trim oldest (keep system prompt if present)
        if len(self._messages) > self._max:
            self._messages = self._messages[-self._max:]

    def get_history(self) -> list[dict]:
        """Return history in OpenAI-compatible format."""
        return [{"role": m.role, "content": m.content} for m in self._messages]

    def clear(self) -> None:
        self._messages.clear()

    @property
    def length(self) -> int:
        return len(self._messages)


# ──────────────────────── Provider Backends ─────────────────────────────────

class _OllamaBackend:
    """Ollama local LLM via REST API."""

    def __init__(self, base_url: str):
        self._url = base_url

    def generate(self, settings: BrainSettings, prompt: str, history: list[dict]) -> str:
        payload = {
            "model": settings.model,
            "prompt": prompt,
            "system": settings.system_prompt,
            "stream": False,
            "options": {
                "temperature": settings.temperature,
                "top_p": settings.top_p,
                "num_predict": settings.max_tokens,
            },
        }
        # If we have history, add context via concatenation (Ollama /api/generate)
        if history:
            context_str = "\n".join(
                f"{m['role'].capitalize()}: {m['content']}" for m in history[-6:]
            )
            payload["prompt"] = f"Previous conversation:\n{context_str}\n\nUser: {prompt}"

        resp = requests.post(self._url, json=payload, timeout=settings.timeout)
        resp.raise_for_status()
        return resp.json().get("response", "")

    def health_check(self) -> bool:
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> tuple[bool, list[str] | str]:
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=5)
            r.raise_for_status()
            models = r.json().get("models", [])
            names = [m.get("name") for m in models if m.get("name")]
            return True, names
        except Exception as e:
            return False, f"Could not fetch local models: {e}"


class _GeminiBackend:
    """Google Gemini via REST API (no SDK dependency)."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def generate(self, settings: BrainSettings, prompt: str, history: list[dict]) -> str:
        if not self._api_key:
            raise ValueError("Gemini API key not configured. Set GEMINI_API_KEY in .env")

        model = settings.model if settings.provider == "gemini" else GEMINI_MODEL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"

        # Build messages
        contents = []

        # Add system instruction as first user/model exchange
        contents.append({
            "role": "user",
            "parts": [{"text": f"[SYSTEM INSTRUCTION]\n{settings.system_prompt}"}]
        })
        contents.append({
            "role": "model",
            "parts": [{"text": "Understood. I am Jarvis, ready to assist."}]
        })

        # Add conversation history
        for msg in history[-8:]:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        # Add current prompt
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": settings.temperature,
                "topP": settings.top_p,
                "maxOutputTokens": settings.max_tokens,
            },
        }

        resp = requests.post(url, json=payload, timeout=settings.timeout)
        resp.raise_for_status()

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            error_info = data.get("error", {})
            raise ValueError(f"Gemini returned no candidates: {error_info}")

        parts = candidates[0].get("content", {}).get("parts", [])
        return parts[0].get("text", "") if parts else ""

    def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            url = f"{self.BASE_URL}?key={self._api_key}"
            r = requests.get(url, timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> tuple[bool, list[str] | str]:
        if not self._api_key:
            return False, "Gemini API key not configured."
        try:
            url = f"{self.BASE_URL}?key={self._api_key}"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            models = r.json().get("models", [])
            names = [m.get("name", "").replace("models/", "") for m in models]
            return True, names
        except Exception as e:
            return False, f"Could not fetch Gemini models: {e}"


class _GrokBackend:
    """xAI Grok via OpenAI-compatible REST API."""

    BASE_URL = "https://api.x.ai/v1/chat/completions"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def generate(self, settings: BrainSettings, prompt: str, history: list[dict]) -> str:
        if not self._api_key:
            raise ValueError("Grok API key not configured. Set GROK_API_KEY in .env")

        model = settings.model if settings.provider == "grok" else GROK_MODEL

        messages = [{"role": "system", "content": settings.system_prompt}]

        for msg in history[-8:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "max_tokens": settings.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        resp = requests.post(self.BASE_URL, json=payload, headers=headers, timeout=settings.timeout)
        resp.raise_for_status()

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"Grok returned no choices: {data}")

        return choices[0].get("message", {}).get("content", "")

    def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            headers = {"Authorization": f"Bearer {self._api_key}"}
            r = requests.get("https://api.x.ai/v1/models", headers=headers, timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> tuple[bool, list[str] | str]:
        if not self._api_key:
            return False, "Grok API key not configured."
        try:
            headers = {"Authorization": f"Bearer {self._api_key}"}
            r = requests.get("https://api.x.ai/v1/models", headers=headers, timeout=10)
            r.raise_for_status()
            models = r.json().get("data", [])
            names = [m.get("id", "") for m in models]
            return True, names
        except Exception as e:
            return False, f"Could not fetch Grok models: {e}"


# ─────────────────────────── Brain ──────────────────────────────────────────

class Brain:
    """
    Industry-grade LLM interface with multi-provider support,
    conversation memory, retry logic, and provider failover.
    """

    MAX_RETRIES = 2
    RETRY_DELAY = 1.0  # seconds

    def __init__(self, provider: Optional[str] = None):
        self.settings = BrainSettings(
            provider=provider or LLM_PROVIDER,
            model=self._default_model_for(provider or LLM_PROVIDER),
        )
        self.memory = ConversationMemory(max_messages=self.settings.max_history)

        # Initialize all backends (lazy — they only call APIs when used)
        self._backends = {
            Provider.OLLAMA: _OllamaBackend(OLLAMA_URL),
            Provider.GEMINI: _GeminiBackend(GEMINI_API_KEY),
            Provider.GROK:   _GrokBackend(GROK_API_KEY),
        }

        logger.info(
            "Brain initialized | provider=%s | model=%s",
            self.settings.provider, self.settings.model,
        )
        print(f"Brain initialized | provider={self.settings.provider} | model={self.settings.model}")

    # ── Public API ──────────────────────────────────────────────────────────

    def generate_response(self, text: str, history: list[dict] | None = None) -> str:
        """
        Generate an LLM response with retry + optional failover.
        Stores conversation in memory for multi-turn context.
        """
        if not text or not text.strip():
            return ""

        # Use internal memory if no external history supplied
        conv_history = history if history is not None else self.memory.get_history()

        backend = self._get_backend()
        response = ""

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                t0 = time.time()
                response = backend.generate(self.settings, text.strip(), conv_history)
                elapsed = time.time() - t0

                logger.info(
                    "LLM response | provider=%s | model=%s | time=%.2fs | len=%d",
                    self.settings.provider, self.settings.model, elapsed, len(response),
                )

                # Store in memory
                self.memory.add("user", text.strip())
                self.memory.add("assistant", response)

                return response

            except requests.exceptions.ConnectionError:
                logger.warning("Connection failed (attempt %d/%d)", attempt, self.MAX_RETRIES)
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                    continue
                # Try failover
                fallback = self._try_failover(text.strip(), conv_history)
                if fallback:
                    return fallback
                return f"Error: Could not connect to {self.settings.provider} LLM. Is it running?"

            except requests.exceptions.Timeout:
                logger.warning("Request timed out (attempt %d/%d)", attempt, self.MAX_RETRIES)
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                    continue
                return f"Error: {self.settings.provider} LLM timed out after {self.settings.timeout}s."

            except requests.exceptions.HTTPError as e:
                logger.error("HTTP error: %s", e)
                return f"Error: LLM returned HTTP {e.response.status_code if e.response else 'unknown'}."

            except ValueError as e:
                logger.error("Value error: %s", e)
                return f"Error: {e}"

            except Exception as e:
                logger.error("Unexpected error: %s", e, exc_info=True)
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                    continue
                return f"Brain Error: {e}"

        return response or "Error: Failed to generate response."

    def set_provider(self, provider_name: str) -> tuple[bool, str]:
        """Switch the active LLM provider."""
        provider_name = provider_name.strip().lower()
        try:
            provider = Provider(provider_name)
        except ValueError:
            valid = ", ".join(p.value for p in Provider)
            return False, f"Unknown provider '{provider_name}'. Valid: {valid}"

        # Validate API key for cloud providers
        if provider == Provider.GEMINI and not GEMINI_API_KEY:
            return False, "Cannot switch to Gemini: GEMINI_API_KEY not set in .env"
        if provider == Provider.GROK and not GROK_API_KEY:
            return False, "Cannot switch to Grok: GROK_API_KEY not set in .env"

        old_provider = self.settings.provider
        self.settings.provider = provider.value
        self.settings.model = self._default_model_for(provider.value)

        logger.info("Provider switched: %s → %s", old_provider, provider.value)
        return True, f"Provider switched to '{provider.value}' (model: {self.settings.model})."

    def set_model(self, model_name: str) -> tuple[bool, str]:
        model_name = (model_name or "").strip()
        if not model_name:
            return False, "Model name cannot be empty."
        self.settings.model = model_name
        return True, f"Model set to '{self.settings.model}' (provider: {self.settings.provider})."

    def set_option(self, option_name: str, raw_value: str) -> tuple[bool, str]:
        name = option_name.lower().strip()
        try:
            if name == "temperature":
                value = float(raw_value)
                if not self.settings.validate_temperature(value):
                    return False, "temperature must be between 0 and 2."
                self.settings.temperature = value
                return True, f"temperature set to {value}."

            if name == "top_p":
                value = float(raw_value)
                if not self.settings.validate_top_p(value):
                    return False, "top_p must be > 0 and <= 1."
                self.settings.top_p = value
                return True, f"top_p set to {value}."

            if name == "max_tokens":
                value = int(raw_value)
                if not self.settings.validate_max_tokens(value):
                    return False, "max_tokens must be a positive integer."
                self.settings.max_tokens = value
                return True, f"max_tokens set to {value}."

            if name == "timeout":
                value = int(raw_value)
                if not self.settings.validate_timeout(value):
                    return False, "timeout must be a positive integer (seconds)."
                self.settings.timeout = value
                return True, f"timeout set to {value}s."

            return False, f"Unknown option '{option_name}'. Valid: temperature, top_p, max_tokens, timeout."
        except ValueError:
            return False, f"Invalid value '{raw_value}' for {option_name}."

    def set_system_prompt(self, prompt: str) -> tuple[bool, str]:
        prompt = (prompt or "").strip()
        if not prompt:
            return False, "System prompt cannot be empty."
        self.settings.system_prompt = prompt
        return True, "System prompt updated."

    def reset_settings(self) -> str:
        self.settings = BrainSettings(
            provider=LLM_PROVIDER,
            model=self._default_model_for(LLM_PROVIDER),
        )
        self.memory.clear()
        return "Brain settings and memory reset to defaults."

    def clear_memory(self) -> str:
        self.memory.clear()
        return "Conversation memory cleared."

    def get_status(self) -> dict:
        backend = self._get_backend()
        is_healthy = backend.health_check()
        return {
            "provider": self.settings.provider,
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            "max_tokens": self.settings.max_tokens,
            "timeout": self.settings.timeout,
            "system_prompt_preview": self.settings.system_prompt[:120],
            "memory_messages": self.memory.length,
            "health": "connected" if is_healthy else "disconnected",
        }

    def list_local_models(self) -> tuple[bool, list[str] | str]:
        backend = self._get_backend()
        return backend.list_models()

    def execute_tool(self, tool_call: dict) -> str:
        """Placeholder for future tool/function-calling support."""
        logger.warning("execute_tool called but not yet implemented: %s", tool_call)
        return "Tool execution not yet implemented."

    # ── Private Helpers ─────────────────────────────────────────────────────

    def _get_backend(self):
        provider = Provider(self.settings.provider)
        return self._backends[provider]

    def _default_model_for(self, provider: str) -> str:
        defaults = {
            "ollama": OLLAMA_MODEL,
            "gemini": GEMINI_MODEL,
            "grok":   GROK_MODEL,
        }
        return defaults.get(provider, OLLAMA_MODEL)

    def _try_failover(self, text: str, history: list[dict]) -> Optional[str]:
        """Attempt to use another provider if the primary is down."""
        current = Provider(self.settings.provider)
        fallback_order = [p for p in Provider if p != current]

        for fallback_provider in fallback_order:
            backend = self._backends[fallback_provider]
            if backend.health_check():
                logger.info("Failing over to %s", fallback_provider.value)
                try:
                    # Temporarily use fallback settings
                    temp_settings = BrainSettings(
                        provider=fallback_provider.value,
                        model=self._default_model_for(fallback_provider.value),
                        temperature=self.settings.temperature,
                        top_p=self.settings.top_p,
                        max_tokens=self.settings.max_tokens,
                        timeout=self.settings.timeout,
                        system_prompt=self.settings.system_prompt,
                    )
                    response = backend.generate(temp_settings, text, history)
                    return f"[Failover → {fallback_provider.value}] {response}"
                except Exception as e:
                    logger.warning("Failover to %s failed: %s", fallback_provider.value, e)
                    continue

        return None
