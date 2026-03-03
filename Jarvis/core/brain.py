"""
Brain Module — Multi-Provider LLM Interface Layer
===================================================
Provides a unified interface to multiple LLM backends:
  - Ollama  (local, default)
  - Gemini  (Google Cloud)
  - Groq    (Groq Cloud — fast inference)
  - Grok    (xAI Cloud)

Supports conversation memory, chain-of-thought reasoning, retry logic,
provider failover, latency-aware routing, and structured settings management.
"""

import logging
import json
import os
import queue
import re
import sqlite3
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from Jarvis.core.personas import PersonaManager
from Jarvis.core.context import ContextManager

import httpx

from Jarvis.config import (
    OLLAMA_URL,
    OLLAMA_MODEL,
    OLLAMA_FAST_MODEL,
    OLLAMA_LOGIC_MODEL,
    OLLAMA_CODE_MODEL,
    OLLAMA_AUTO_SELECT,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROK_API_KEY,
    GROK_MODEL,
    LLM_PROVIDER,
    DEFAULT_PERSONA,
    RESPONSE_STYLE,
)

logger = logging.getLogger("jarvis.brain")


# ─────────────────────────── Constants ──────────────────────────────────────

class Provider(str, Enum):
    OLLAMA = "ollama"
    GEMINI = "gemini"
    GROQ   = "groq"
    GROK   = "grok"


from Jarvis.sft.canonical_prompt import CANONICAL_SYSTEM_PROMPT

DEFAULT_SYSTEM_PROMPT = CANONICAL_SYSTEM_PROMPT


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
    """
    Sliding-window conversation buffer with SQLite persistence.

    Conversations survive restarts. The last `max_messages` turns are
    loaded back into memory on startup and written through on every add().
    The DB is stored at  <DATA_DIR>/conversation_history.db
    """

    def __init__(self, max_messages: int = 20, session_id: str = "default"):
        from Jarvis.config import DATA_DIR
        self._max = max_messages
        self._session_id = session_id
        self._messages: list[Message] = []
        self._lock = threading.Lock()

        db_path = os.path.join(DATA_DIR, "conversation_history.db")
        self._db_path = db_path
        self._init_db()
        self._load_recent()

    # ── DB setup ─────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Create the SQLite table if it doesn't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    session   TEXT    NOT NULL,
                    role      TEXT    NOT NULL,
                    content   TEXT    NOT NULL,
                    ts        REAL    NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_ts ON messages(session, ts)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_recent(self) -> None:
        """Load the most recent `max_messages` turns from DB into memory."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT role, content, ts FROM messages "
                    "WHERE session = ? ORDER BY ts ASC",
                    (self._session_id,),
                ).fetchall()
            # Keep only the tail to respect the window size
            tail = rows[-self._max:]
            self._messages = [Message(role=r["role"], content=r["content"], timestamp=r["ts"]) for r in tail]
        except Exception as e:
            logger.warning("Could not load conversation history: %s", e)

    # ── Public API (unchanged) ────────────────────────────────────────────

    def add(self, role: str, content: str) -> None:
        msg = Message(role=role, content=content)
        with self._lock:
            self._messages.append(msg)
            if len(self._messages) > self._max:
                self._messages = self._messages[-self._max:]

        # Persist asynchronously to avoid blocking the LLM pipeline
        threading.Thread(target=self._persist, args=(msg,), daemon=True).start()

    def get_history(self) -> list[dict]:
        """Return history in OpenAI-compatible format."""
        with self._lock:
            return [{"role": m.role, "content": m.content} for m in self._messages]

    def clear(self) -> None:
        """Clear in-memory buffer and delete this session's rows from DB."""
        with self._lock:
            self._messages.clear()
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM messages WHERE session = ?", (self._session_id,))
        except Exception as e:
            logger.warning("Could not clear persisted history: %s", e)

    @property
    def length(self) -> int:
        with self._lock:
            return len(self._messages)

    # ── Session management helpers ────────────────────────────────────────

    @staticmethod
    def list_sessions(data_dir: Optional[str] = None) -> list[str]:
        """Return all session IDs that have stored history."""
        from Jarvis.config import DATA_DIR as _DATA_DIR
        db_path = os.path.join(data_dir or _DATA_DIR, "conversation_history.db")
        if not os.path.exists(db_path):
            return []
        try:
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT DISTINCT session FROM messages ORDER BY session"
                ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    # ── Internal ──────────────────────────────────────────────────────────

    def _persist(self, msg: Message) -> None:
        """Write a single message to the DB (runs in background thread)."""
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO messages (session, role, content, ts) VALUES (?, ?, ?, ?)",
                    (self._session_id, msg.role, msg.content, msg.timestamp),
                )
                # Prune rows beyond 2× the window so the DB never grows unbounded
                conn.execute(
                    "DELETE FROM messages WHERE session = ? AND id NOT IN "
                    "(SELECT id FROM messages WHERE session = ? ORDER BY ts DESC LIMIT ?)",
                    (self._session_id, self._session_id, self._max * 2),
                )
        except Exception as e:
            logger.warning("Failed to persist message: %s", e)


# ──────────────────────── Shared HTTP Client ───────────────────────────────

# Persistent HTTP clients with connection pooling (reused across all backends)
_http_clients: dict[str, httpx.Client] = {}
_http_lock = threading.Lock()

def _get_http_client(base_url: str = "", timeout: float = 60.0) -> httpx.Client:
    """Get or create a persistent httpx client with connection pooling."""
    key = base_url or "default"
    with _http_lock:
        if key not in _http_clients:
            _http_clients[key] = httpx.Client(
                timeout=httpx.Timeout(timeout, connect=10.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                follow_redirects=True,
            )
    return _http_clients[key]


# ──────────────────────── Provider Backends ─────────────────────────────────

class _OllamaBackend:
    """Ollama local LLM via REST API (httpx with connection pooling)."""

    def __init__(self, base_url: str):
        self._url = base_url.rstrip("/")
        self._generate_url = f"{self._url}/api/generate"
        self._chat_url = f"{self._url}/api/chat"

    def generate(self, settings: BrainSettings, prompt: str, history: list[dict]) -> str:
        messages = [{"role": "system", "content": settings.system_prompt}]
        for msg in history[-8:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": settings.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": settings.temperature,
                "top_p": settings.top_p,
                "num_predict": settings.max_tokens,
            },
        }

        client = _get_http_client(self._url, settings.timeout)
        resp = client.post(self._chat_url, json=payload)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")

    def generate_stream(self, settings: BrainSettings, prompt: str, history: list[dict]):
        """Yield response tokens from Ollama's chat API."""
        messages = [{"role": "system", "content": settings.system_prompt}]
        for msg in history[-8:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": settings.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": settings.temperature,
                "top_p": settings.top_p,
                "num_predict": settings.max_tokens,
            },
        }

        client = _get_http_client(self._url, settings.timeout)
        with client.stream("POST", self._chat_url, json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break

    def health_check(self) -> bool:
        try:
            client = _get_http_client(self._url, 5.0)
            r = client.get(f"{self._url}/api/tags")
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> tuple[bool, list[str] | str]:
        try:
            client = _get_http_client(self._url, 5.0)
            r = client.get(f"{self._url}/api/tags")
            r.raise_for_status()
            models = r.json().get("models", [])
            names = [m.get("name") for m in models if m.get("name")]
            return True, names
        except Exception as e:
            return False, f"Could not fetch local models: {e}"


class _GeminiBackend:
    """Google Gemini via REST API (httpx with connection pooling)."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def generate(self, settings: BrainSettings, prompt: str, history: list[dict]) -> str:
        if not self._api_key:
            raise ValueError("Gemini API key not configured. Set GEMINI_API_KEY in .env")

        model = settings.model if settings.provider == "gemini" else GEMINI_MODEL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"

        contents = []
        contents.append({
            "role": "user",
            "parts": [{"text": f"[SYSTEM INSTRUCTION]\n{settings.system_prompt}"}]
        })
        contents.append({
            "role": "model",
            "parts": [{"text": "Understood. I am Jarvis, ready to assist."}]
        })
        for msg in history[-8:]:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": settings.temperature,
                "topP": settings.top_p,
                "maxOutputTokens": settings.max_tokens,
            },
        }

        client = _get_http_client("gemini", settings.timeout)
        resp = client.post(url, json=payload)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            logger.warning("Gemini rate limited, waiting %ds...", retry_after)
            time.sleep(min(retry_after, 10))
            resp = client.post(url, json=payload)

        resp.raise_for_status()

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            error_info = data.get("error", {})
            raise ValueError(f"Gemini returned no candidates: {error_info}")

        parts = candidates[0].get("content", {}).get("parts", [])
        return parts[0].get("text", "") if parts else ""

    def generate_stream(self, settings: BrainSettings, prompt: str, history: list[dict]):
        """Yield response tokens from Gemini's streaming SSE endpoint."""
        if not self._api_key:
            raise ValueError("Gemini API key not configured. Set GEMINI_API_KEY in .env")

        model = settings.model if settings.provider == "gemini" else GEMINI_MODEL
        url = f"{self.BASE_URL}/{model}:streamGenerateContent?key={self._api_key}&alt=sse"

        contents = []
        contents.append({
            "role": "user",
            "parts": [{"text": f"[SYSTEM INSTRUCTION]\n{settings.system_prompt}"}]
        })
        contents.append({
            "role": "model",
            "parts": [{"text": "Understood. I am Jarvis, ready to assist."}]
        })
        for msg in history[-8:]:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": settings.temperature,
                "topP": settings.top_p,
                "maxOutputTokens": settings.max_tokens,
            },
        }

        client = _get_http_client("gemini", settings.timeout)
        with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    chunk = line[6:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                        parts = (
                            data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [])
                        )
                        text = parts[0].get("text", "") if parts else ""
                        if text:
                            yield text
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue

    def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            url = f"{self.BASE_URL}?key={self._api_key}"
            client = _get_http_client("gemini", 10.0)
            r = client.get(url)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> tuple[bool, list[str] | str]:
        if not self._api_key:
            return False, "Gemini API key not configured."
        try:
            url = f"{self.BASE_URL}?key={self._api_key}"
            client = _get_http_client("gemini", 10.0)
            r = client.get(url)
            r.raise_for_status()
            models = r.json().get("models", [])
            names = [m.get("name", "").replace("models/", "") for m in models]
            return True, names
        except Exception as e:
            return False, f"Could not fetch Gemini models: {e}"


class _GroqBackend:
    """Groq Cloud via OpenAI-compatible REST API (httpx with connection pooling)."""

    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, settings: BrainSettings, prompt: str, history: list[dict]) -> str:
        if not self._api_key:
            raise ValueError("Groq API key not configured. Set GROQ_API_KEY in .env")

        model = settings.model if settings.provider == "groq" else GROQ_MODEL
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

        client = _get_http_client("groq", settings.timeout)
        resp = client.post(self.BASE_URL, json=payload, headers=self._headers)
        resp.raise_for_status()

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"Groq returned no choices: {data}")

        return choices[0].get("message", {}).get("content", "")

    def generate_stream(self, settings: BrainSettings, prompt: str, history: list[dict]):
        """Yield tokens from Groq's OpenAI-compatible SSE streaming endpoint."""
        if not self._api_key:
            raise ValueError("Groq API key not configured. Set GROQ_API_KEY in .env")

        model = settings.model if settings.provider == "groq" else GROQ_MODEL
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
            "stream": True,
        }

        client = _get_http_client("groq", settings.timeout)
        with client.stream("POST", self.BASE_URL, json=payload, headers=self._headers) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    chunk = line[6:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue

    def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            client = _get_http_client("groq", 10.0)
            r = client.get("https://api.groq.com/openai/v1/models", headers=self._headers)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> tuple[bool, list[str] | str]:
        if not self._api_key:
            return False, "Groq API key not configured."
        try:
            client = _get_http_client("groq", 10.0)
            r = client.get("https://api.groq.com/openai/v1/models", headers=self._headers)
            r.raise_for_status()
            models = r.json().get("data", [])
            names = [m.get("id", "") for m in models]
            return True, names
        except Exception as e:
            return False, f"Could not fetch Groq models: {e}"


class _GrokBackend:
    """xAI Grok via OpenAI-compatible REST API (httpx with connection pooling)."""

    BASE_URL = "https://api.x.ai/v1/chat/completions"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

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

        client = _get_http_client("grok", settings.timeout)
        resp = client.post(self.BASE_URL, json=payload, headers=self._headers)
        resp.raise_for_status()

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"Grok returned no choices: {data}")

        return choices[0].get("message", {}).get("content", "")

    def generate_stream(self, settings: BrainSettings, prompt: str, history: list[dict]):
        """Yield tokens from xAI Grok's OpenAI-compatible SSE streaming endpoint."""
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
            "stream": True,
        }

        client = _get_http_client("grok", settings.timeout)
        with client.stream("POST", self.BASE_URL, json=payload, headers=self._headers) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    chunk = line[6:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue

    def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            client = _get_http_client("grok", 10.0)
            r = client.get("https://api.x.ai/v1/models", headers=self._headers)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> tuple[bool, list[str] | str]:
        if not self._api_key:
            return False, "Grok API key not configured."
        try:
            client = _get_http_client("grok", 10.0)
            r = client.get("https://api.x.ai/v1/models", headers=self._headers)
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

    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds

    def __init__(self, provider: Optional[str] = None):
        # Persona system
        self.personas = PersonaManager(default=DEFAULT_PERSONA)
        active_persona = self.personas.get_active()

        self.settings = BrainSettings(
            provider=provider or LLM_PROVIDER,
            model=self._default_model_for(provider or LLM_PROVIDER),
            system_prompt=active_persona.system_prompt,
        )
        self.memory = ConversationMemory(max_messages=self.settings.max_history)
        self.context = ContextManager()

        # Initialize all backends (lazy — they only call APIs when used)
        self._backends = {
            Provider.OLLAMA: _OllamaBackend(OLLAMA_URL),
            Provider.GEMINI: _GeminiBackend(GEMINI_API_KEY),
            Provider.GROQ:   _GroqBackend(GROQ_API_KEY),
            Provider.GROK:   _GrokBackend(GROK_API_KEY),
        }

        # Initialize ProviderRouter for intelligent provider selection
        from Jarvis.core.provider_router import ProviderRouter
        self.provider_router = ProviderRouter(self)

        logger.info(
            "Brain initialized | provider=%s | model=%s | persona=%s",
            self.settings.provider, self.settings.model, active_persona.name,
        )
        print(f"Brain initialized | provider={self.settings.provider} | model={self.settings.model} | persona={active_persona.name}")

        # Warm up: Pre-load models and connections in background
        threading.Thread(target=self._warm_up, daemon=True).start()

    def _warm_up(self):
        """Pre-load models and establish connections for low first-query latency."""
        try:
            # Warm up Ollama if it's the default provider
            if self.settings.provider == Provider.OLLAMA:
                logger.info("Warming up Ollama model: %s", self.settings.model)
                try:
                    self.generate_response("hi", history=[])
                    logger.info("Ollama model warmed up.")
                except Exception as e:
                    logger.warning("Ollama warm-up failed: %s", e)

            # Pre-warm cloud connections (establishes TCP+TLS)
            for provider_name, backend in self._backends.items():
                if provider_name != Provider.OLLAMA:
                    try:
                        backend.health_check()
                        logger.info("Pre-warmed connection to %s", provider_name.value)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("Warm-up failed: %s", e)

    # ── Public API ──────────────────────────────────────────────────────────

    # Patterns for different task categories
    _CODE_PATTERNS = [
        r"\b(python|script|code|program|function|class|module|debug|fix|refactor|implement|syntax|error|traceback)\b",
        r"\b(write|create|develop|generate)\s+(a\s+)?(script|program|app|function)\b",
        r"\b(how\s+to)\s+(code|program|script)\b",
    ]

    _LOGIC_PATTERNS = [
        r"\b(explain|why\s+does|how\s+does|analyze|analyse|compare|architecture|pattern|design)\b",
        r"\b(step.{0,5}by.{0,5}step|in\s+detail|comprehensively|complex|reason)\b",
        r"\b(plan|summarize|evaluate|critique)\b",
    ]

    def generate_response_stream(
        self,
        text: str,
        history: list[dict] | None = None,
        provider_override: str | None = None,
        model_override: str | None = None,
        system_prompt_override: str | None = None,
        skip_memory: bool = False,
    ):
        """
        Yield LLM tokens as they arrive (streaming) with a 'Fast-Switch' mechanism.

        Smart Switch Architecture:
          1. Select primary provider (Ollama, Gemini, Groq, etc.)
          2. If primary is 'ollama' and it takes > 4s for the first token,
             transparently parallelize/failover to Groq or Gemini.
          3. This ensures zero 'bugging' or silence for the user.

        Override args let the Orchestrator force a specific provider/model
        for hybrid processing (e.g. local model for actions, cloud for chat).
        """
        if not text or not text.strip():
            return

        conv_history = history if history is not None else self.memory.get_history()
        augmented_settings = self._get_augmented_settings()

        # Apply overrides (hybrid orchestration)
        if provider_override:
            augmented_settings.provider = provider_override
            augmented_settings.model = model_override or self._default_model_for(provider_override)
        if model_override:
            augmented_settings.model = model_override
        if system_prompt_override:
            augmented_settings.system_prompt = system_prompt_override

        # 1. Select initial provider (skip if overridden)
        if not provider_override:
            selected_provider = self.provider_router.select_provider(
                text.strip(), preferred=augmented_settings.provider
            )
            if selected_provider != augmented_settings.provider:
                logger.info("ProviderRouter routed: %s → %s", augmented_settings.provider, selected_provider)
                augmented_settings.provider = selected_provider
                augmented_settings.model = self._default_model_for(selected_provider)

        # 2. Adaptive max_tokens
        augmented_settings.max_tokens = self.provider_router.get_max_tokens_for_query(
            text.strip(), augmented_settings.max_tokens
        )

        # 3. Model auto-selection for Ollama (skip if overridden)
        if not model_override and OLLAMA_AUTO_SELECT and augmented_settings.provider == "ollama":
            augmented_settings.model = self._select_model_for_query(text.strip())

        # 4. Execute stream with Smart Switch (Race/Timeout)
        provider_enum = Provider(augmented_settings.provider)
        backend = self._backends[provider_enum]
        full_response = ""
        t0 = time.time()
        first_token_time = None
        
        # Timeout for 'Fast-Switch' (Ollama can be slow, so we wait 4s then race)
        FAST_SWITCH_TIMEOUT = 4.0 if augmented_settings.provider == "ollama" else 15.0

        try:
            # We use a queue to handle tokens from potentially multiple sources (failover)
            token_queue = queue.Queue()
            stop_event = threading.Event()
            
            def run_primary():
                nonlocal first_token_time
                try:
                    for token in backend.generate_stream(augmented_settings, text.strip(), conv_history):
                        if stop_event.is_set(): break
                        if first_token_time is None: first_token_time = time.time()
                        token_queue.put(token)
                    token_queue.put(None) # End of stream
                except Exception as e:
                    logger.warning("Primary provider stream error: %s", e)
                    token_queue.put(e)

            primary_thread = threading.Thread(target=run_primary, daemon=True)
            primary_thread.start()

            # Wait for first token or timeout
            start_wait = time.time()
            while True:
                try:
                    # Short poll for token
                    chunk = token_queue.get(timeout=0.1)
                    if isinstance(chunk, Exception):
                        # Primary failed — trigger immediate failover
                        logger.info("Primary failed, triggering immediate failover")
                        break
                    if chunk is None: break # Done
                    
                    full_response += chunk
                    yield chunk
                    if first_token_time is None: first_token_time = time.time()
                except queue.Empty:
                    # Check timeout for Ollama -> Cloud switch
                    if first_token_time is None and (time.time() - start_wait) > FAST_SWITCH_TIMEOUT:
                        logger.warning("Primary (%s) timed out, triggering Fast-Switch to Cloud", augmented_settings.provider)
                        stop_event.set()
                        break
                    if not primary_thread.is_alive() and token_queue.empty():
                        break
                    continue

            # 5. Handle Failover / Fast-Switch if needed
            if first_token_time is None:
                # No token received yet — try Cloud failover
                fallback_stream = self._try_stream_failover(text.strip(), conv_history, augmented_settings)
                if fallback_stream:
                    print(f"  [Smart-Switch] Failing over to Cloud for faster response...")
                    for token in fallback_stream:
                        full_response += token
                        yield token
                else:
                    yield f"I'm sorry, sir, but I'm having trouble getting a response from my brain. Please try again in a moment."

        except Exception as e:
            logger.error("Global stream error: %s", e, exc_info=True)
            yield f"I'm afraid I encountered a technical error: {e}"

        if full_response and not skip_memory:
            self.memory.add("user", text.strip())
            self.memory.add("assistant", full_response)

    def _try_stream_failover(self, text: str, history: list[dict], settings: 'BrainSettings'):
        """Try streaming from another provider when the primary fails."""
        current = Provider(settings.provider)
        for provider in Provider:
            if provider == current:
                continue
            backend = self._backends[provider]
            try:
                if not backend.health_check():
                    continue
                temp_settings = BrainSettings(
                    provider=provider.value,
                    model=self._default_model_for(provider.value),
                    temperature=settings.temperature,
                    top_p=settings.top_p,
                    max_tokens=settings.max_tokens,
                    timeout=settings.timeout,
                    system_prompt=settings.system_prompt,
                )
                logger.info("Stream failover → %s", provider.value)
                return backend.generate_stream(temp_settings, text, history)
            except Exception as e:
                logger.warning("Stream failover to %s failed: %s", provider.value, e)
                continue
        return None

    def generate_response(
        self,
        text: str,
        history: list[dict] | None = None,
        provider_override: str | None = None,
        model_override: str | None = None,
        system_prompt_override: str | None = None,
        skip_memory: bool = False,
    ) -> str:
        """
        Generate an LLM response with retry + optional failover.
        Stores conversation in memory for multi-turn context.

        Override args let the Orchestrator force a specific provider/model
        for hybrid processing (e.g. local model for actions, cloud for chat).
        """
        if not text or not text.strip():
            return ""

        # Use internal memory if no external history supplied
        conv_history = history if history is not None else self.memory.get_history()
        augmented_settings = self._get_augmented_settings()

        # Apply overrides (hybrid orchestration)
        if provider_override:
            augmented_settings.provider = provider_override
            augmented_settings.model = model_override or self._default_model_for(provider_override)
        if model_override:
            augmented_settings.model = model_override
        if system_prompt_override:
            augmented_settings.system_prompt = system_prompt_override

        # Use ProviderRouter for intelligent provider selection (skip if overridden)
        if not provider_override:
            selected_provider = self.provider_router.select_provider(
                text.strip(), preferred=augmented_settings.provider
            )
            if selected_provider != augmented_settings.provider:
                logger.info("ProviderRouter routed: %s → %s", augmented_settings.provider, selected_provider)
                augmented_settings.provider = selected_provider
                augmented_settings.model = self._default_model_for(selected_provider)

        provider_enum = Provider(augmented_settings.provider)
        backend = self._backends[provider_enum]
        response = ""

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                t0 = time.time()
                response = backend.generate(augmented_settings, text.strip(), conv_history)
                elapsed = time.time() - t0
                self.provider_router.record_success(augmented_settings.provider, ttft_ms=elapsed * 1000)

                logger.info(
                    "LLM response | provider=%s | model=%s | time=%.2fs | len=%d",
                    augmented_settings.provider, augmented_settings.model, elapsed, len(response),
                )

                # Store in memory (skip for internal processing calls)
                if not skip_memory:
                    self.memory.add("user", text.strip())
                    self.memory.add("assistant", response)

                return response

            except httpx.ConnectError:
                logger.warning("Connection failed (attempt %d/%d)", attempt, self.MAX_RETRIES)
                self.provider_router.record_error(augmented_settings.provider)
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)  # exponential-ish backoff
                    continue
                # Try failover
                fallback = self._try_failover(text.strip(), conv_history)
                if fallback:
                    return fallback
                return f"I'm sorry, sir, but I couldn't connect to the {augmented_settings.provider} service. Please ensure it is running."

            except httpx.TimeoutException:
                logger.warning("Request timed out (attempt %d/%d)", attempt, self.MAX_RETRIES)
                self.provider_router.record_error(augmented_settings.provider)
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                    continue
                return f"I'm sorry, sir, but the {augmented_settings.provider} service timed out. You might want to try again in a moment."

            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else 0
                logger.error("HTTP error %d: %s", status, e)

                # Rate limit — retry with backoff
                if status == 429:
                    wait = min(self.RETRY_DELAY * (2 ** attempt), 15)
                    logger.warning("Rate limited (429), waiting %.1fs (attempt %d/%d)", wait, attempt, self.MAX_RETRIES)
                    if attempt < self.MAX_RETRIES:
                        time.sleep(wait)
                        continue
                    # Last resort: try failover to another provider
                    fallback = self._try_failover(text.strip(), conv_history)
                    if fallback:
                        return fallback
                    return f"I'm afraid the {augmented_settings.provider} service is currently rate limited. Please try again in a minute or switch providers."

                # Auth error
                if status in (401, 403):
                    return f"I'm sorry, sir, but the {augmented_settings.provider} API key appears to be invalid or expired. Please check your credentials."

                return f"I'm sorry, sir, but the {augmented_settings.provider} service returned an error. It might be having some technical issues."

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

    def _get_augmented_settings(self) -> BrainSettings:
        """
        Returns a copy of settings for this request.
        NOTE: Context injection is deliberately disabled — injecting OS/directory info
        into every prompt confuses small models and causes hallucinations.
        Context is only provided if explicitly requested by the user.
        """
        import copy
        return copy.copy(self.settings)

    def set_provider(self, provider_name: str) -> tuple[bool, str]:
        """Switch the active LLM provider."""
        provider_name = provider_name.strip().lower()
        try:
            provider = Provider(provider_name)
        except ValueError:
            valid = ", ".join(p.value for p in Provider)
            return False, f"Unknown provider '{provider_name}'. Valid: {valid}"

        # Validate API key for cloud providers
        key_map = {
            Provider.GEMINI: (GEMINI_API_KEY, "GEMINI_API_KEY"),
            Provider.GROQ:   (GROQ_API_KEY, "GROQ_API_KEY"),
            Provider.GROK:   (GROK_API_KEY, "GROK_API_KEY"),
        }
        if provider in key_map:
            api_key, env_name = key_map[provider]
            if not api_key:
                return False, f"Cannot switch to {provider.value}: {env_name} not set in .env"

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

    def set_persona(self, name: str) -> tuple[bool, str, str]:
        """Switch persona. Returns (ok, message, new_voice_id)."""
        ok, message = self.personas.set_active(name)
        if ok:
            profile = self.personas.get_active()
            self.settings.system_prompt = profile.system_prompt
            return True, message, profile.voice
        return False, message, ""

    def get_persona_name(self) -> str:
        """Return the active persona's display name."""
        return self.personas.get_active().display_name

    def reset_settings(self) -> str:
        self.personas.reset()
        active_persona = self.personas.get_active()
        self.settings = BrainSettings(
            provider=LLM_PROVIDER,
            model=self._default_model_for(LLM_PROVIDER),
            system_prompt=active_persona.system_prompt,
        )
        self.memory.clear()
        return "Brain settings, memory, and persona reset to defaults."

    def clear_memory(self) -> str:
        self.memory.clear()
        return "Conversation memory cleared."

    def get_status(self) -> dict:
        backend = self._get_backend()
        is_healthy = backend.health_check()
        return {
            "provider": self.settings.provider,
            "model": self.settings.model,
            "persona": self.personas.get_active().display_name,
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

    def _select_model_for_query(self, text: str) -> str:
        """Return the best Ollama model for the query: Fast, Logic, or Code."""
        # 1. Check for Code patterns
        for pat in self._CODE_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                logger.debug("Auto-select: code query → %s", OLLAMA_CODE_MODEL)
                return OLLAMA_CODE_MODEL

        # 2. Check for Logic patterns
        for pat in self._LOGIC_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                logger.debug("Auto-select: logic query → %s", OLLAMA_LOGIC_MODEL)
                return OLLAMA_LOGIC_MODEL

        # 3. Check for length-based complexity
        if len(text.split()) > 25:
            return OLLAMA_LOGIC_MODEL

        # 4. Default to Fast model
        logger.debug("Auto-select: fast query → %s", OLLAMA_FAST_MODEL)
        return OLLAMA_FAST_MODEL

    def _default_model_for(self, provider: str) -> str:
        defaults = {
            "ollama": OLLAMA_MODEL,
            "gemini": GEMINI_MODEL,
            "groq":   GROQ_MODEL,
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
