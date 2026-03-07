"""
Intent Engine — Groq-Powered Deep Thinking & Intent Analysis
=============================================================
Runs a fast, structured reasoning pass on every user query BEFORE
the main LLM responds. Uses Groq's low-latency inference to:

  1. Classify the user's true intent (category + action)
  2. Extract key entities (app names, file paths, queries, values)
  3. Score confidence and flag ambiguous commands
  4. Rewrite garbled or unclear voice input into clean text
  5. Inject a structured intent context into the Brain's system note

Runs concurrently with the main pipeline — adds zero net latency on fast
connections. Gracefully degrades to a pass-through if Groq is unavailable.

Intent Categories:
  conversation    — casual chat, questions, general knowledge
  system_control  — volume, mute, screenshot, lock, time/date
  media           — Spotify, YouTube, music playback
  web_search      — Google search, open URLs
  app_launch      — open/launch/start an application
  shell_command   — direct terminal execution
  file_operation  — read, write, list files
  code            — write, debug, explain code
  memory          — "what did I say earlier", "forget that"
  settings        — change voice, model, persona, mode
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
import time, httpx

logger = logging.getLogger("jarvis.intent_engine")

def post_with_retry(url, payload, headers, max_attempts=3):
    client = httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0))
    for attempt in range(1, max_attempts+1):
        try:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            if attempt == max_attempts:
                raise  # agar max attempts ho gaye toh error throw karo
            sleep_time = 2 ** attempt  # exponential backoff (2s, 4s, 8s)
            print(f"Retrying in {sleep_time} seconds... (Attempt {attempt})")
            time.sleep(sleep_time)
# ─────────────────────── Intent Result ──────────────────────────────────────

INTENT_CATEGORIES = [
    "conversation",
    "system_control",
    "media",
    "web_search",
    "app_launch",
    "shell_command",
    "file_operation",
    "code",
    "memory",
    "settings",
]


@dataclass
class IntentResult:
    """Structured result from the IntentEngine analysis pass."""

    # Core classification
    category: str = "conversation"         # One of INTENT_CATEGORIES
    action: str = ""                       # Specific action verb (e.g. "set_volume", "launch_app")
    entities: dict = field(default_factory=dict)  # Extracted entities: {app, query, value, path, ...}

    # Confidence & clarity
    confidence: float = 1.0               # 0.0–1.0  (< 0.6 = uncertain)
    is_ambiguous: bool = False            # True if multiple interpretations are plausible
    ambiguity_note: str = ""             # Human-readable note about the ambiguity

    # Rewritten / enriched query
    rewritten_query: str = ""             # Clean version of the user's query (e.g. corrects STT errors)
    reasoning: str = ""                  # Brief chain-of-thought (for logs/debug)

    # Meta
    latency_ms: float = 0.0              # Time taken for this analysis call
    from_cache: bool = False             # True if this was a very recent duplicate query
    error: Optional[str] = None         # Set if analysis failed (fallback mode)

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.65 and not self.is_ambiguous

    @property
    def effective_query(self) -> str:
        """Return the best query to send to the main LLM."""
        return self.rewritten_query if self.rewritten_query else ""

    def to_system_note(self) -> str:
        """
        Format the intent analysis as a concise system-level context note
        to inject into the LLM's system prompt.
        """
        if self.error:
            return ""  # Don't inject on analysis failure

        lines = [
            "[INTENT ANALYSIS]",
            f"Category   : {self.category}",
        ]
        if self.action:
            lines.append(f"Action     : {self.action}")
        if self.entities:
            entities_str = ", ".join(f"{k}={v}" for k, v in self.entities.items())
            lines.append(f"Entities   : {entities_str}")
        lines.append(f"Confidence : {self.confidence:.0%}")
        if self.is_ambiguous:
            lines.append(f"Ambiguous  : {self.ambiguity_note}")
        if self.reasoning:
            lines.append(f"Reasoning  : {self.reasoning}")
        lines.append("[/INTENT ANALYSIS]")
        return "\n".join(lines)


# ─────────────────────── Prompt Template ────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a precision intent classifier for an AI desktop assistant.
Your ONLY job is to analyze the user's input and return a JSON object.
Do NOT respond conversationally. Return ONLY valid JSON, nothing else.

JSON schema:
{
  "category": "<one of: conversation|system_control|media|web_search|app_launch|shell_command|file_operation|code|memory|settings>",
  "action": "<concise snake_case action, e.g. set_volume, launch_app, play_music, take_screenshot>",
  "entities": {
    "<key>": "<value>"
  },
  "confidence": <float 0.0–1.0>,
  "is_ambiguous": <bool>,
  "ambiguity_note": "<string or empty>",
  "rewritten_query": "<clean, corrected version of the original query — fix STT errors, expand contractions, remove filler words>",
  "reasoning": "<one sentence explaining your classification>"
}

Guidelines:
- Be strict with confidence: 0.9+ = crystal clear, 0.5–0.7 = probable, <0.5 = unclear.
- If the command could plausibly mean two different things, set is_ambiguous=true.
- Always populate rewritten_query, even if no changes are needed.
- Keep reasoning to ONE short sentence.
- entities keys: app, song, artist, query, url, path, value, command, topic (use only what's relevant).
"""

_USER_PROMPT_TEMPLATE = """\
Classify this user input: "{query}"

Conversation history summary (last 2 turns):
{history_summary}
"""


# ─────────────────────── Cache ───────────────────────────────────────────────

class _IntentCache:
    """Simple LRU-style cache to avoid re-analyzing identical recent queries."""

    def __init__(self, maxsize: int = 20, ttl_s: float = 30.0):
        self._store: dict[str, tuple[float, IntentResult]] = {}
        self._maxsize = maxsize
        self._ttl = ttl_s

    def get(self, key: str) -> Optional[IntentResult]:
        entry = self._store.get(key)
        if entry and (time.time() - entry[0]) < self._ttl:
            result = entry[1]
            result.from_cache = True
            return result
        return None

    def set(self, key: str, result: IntentResult) -> None:
        if len(self._store) >= self._maxsize:
            # Evict oldest
            oldest = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest]
        self._store[key] = (time.time(), result)


# ─────────────────────── Intent Engine ──────────────────────────────────────

class IntentEngine:
    """
    Groq-powered deep thinking intent analysis engine.

    Usage (concurrent pattern — zero latency impact):

        # Start analysis at the same moment you start the filler thread
        intent_future = self.intent_engine.analyze_async(text, history)

        # ... main LLM pipeline runs ...

        # Collect result when needed
        result = intent_future.result(timeout=2.0)
    """

    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, model: str, confidence_threshold: float = 0.6):
        self._api_key = api_key
        self._model = model
        self._threshold = confidence_threshold
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._cache = _IntentCache()
        self._enabled = bool(api_key)

        if not self._enabled:
            logger.warning("IntentEngine: No Groq API key — running in pass-through mode.")

    # ── Public API ────────────────────────────────────────────────────────

    def analyze(self, query: str, history: list[dict] | None = None) -> IntentResult:
        """
        Synchronously analyze intent. Blocks until result is ready.
        Falls back to a default IntentResult on any error.
        """
        if not self._enabled:
            return self._passthrough(query)

        # Normalize for cache key
        cache_key = query.strip().lower()[:200]
        cached = self._cache.get(cache_key)
        if cached:
            logger.debug("IntentEngine: cache hit for '%s'", cache_key[:50])
            return cached

        t0 = time.time()
        try:
            result = self._call_groq(query, history or [])
            result.latency_ms = (time.time() - t0) * 1000
            logger.info(
                "IntentEngine: cat=%s act=%s conf=%.0f%% latency=%.0fms",
                result.category, result.action,
                result.confidence * 100, result.latency_ms,
            )
            self._cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.warning("IntentEngine analysis failed: %s", e)
            fallback = self._passthrough(query)
            fallback.error = str(e)
            fallback.latency_ms = (time.time() - t0) * 1000
            return fallback

    def analyze_async(self, query: str, history: list[dict] | None = None):
        """
        Non-blocking analysis. Returns a concurrent.futures.Future.
        The Orchestrator can collect the result at any time with `.result(timeout=N)`.
        """
        from concurrent.futures import Future, ThreadPoolExecutor
        future: Future[IntentResult] = Future()

        def _run():
            try:
                result = self.analyze(query, history)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return future

    # ── Internal ──────────────────────────────────────────────────────────

    def _call_groq(self, query: str, history: list[dict]) -> IntentResult:
        """Call Groq API and parse the structured JSON response."""
        history_summary = self._summarize_history(history)
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            query=query,
            history_summary=history_summary,
        )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,   # Near-zero: we want deterministic classification
            "max_tokens": 300,
            "response_format": {"type": "json_object"},
        }

        # Use a short, dedicated client for intention analysis
        client = httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0))
        resp = post_with_retry(self.GROQ_URL, payload, self._headers)
        resp.raise_for_status()

        raw = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(raw)
        return self._parse(data)

    def _parse(self, data: dict) -> IntentResult:
        """Parse raw JSON dict into an IntentResult."""
        category = data.get("category", "conversation")
        if category not in INTENT_CATEGORIES:
            category = "conversation"

        return IntentResult(
            category=category,
            action=data.get("action", ""),
            entities=data.get("entities", {}),
            confidence=float(data.get("confidence", 1.0)),
            is_ambiguous=bool(data.get("is_ambiguous", False)),
            ambiguity_note=data.get("ambiguity_note", ""),
            rewritten_query=data.get("rewritten_query", ""),
            reasoning=data.get("reasoning", ""),
        )

    @staticmethod
    def _summarize_history(history: list[dict]) -> str:
        """Build a short 2-turn history summary for the intent prompt."""
        if not history:
            return "(no prior context)"
        tail = history[-4:]  # last 2 turns (user + assistant × 2)
        lines = []
        for msg in tail:
            role = msg.get("role", "?")
            content = msg.get("content", "")[:100]
            lines.append(f"  {role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _passthrough(query: str) -> IntentResult:
        """Fallback when engine is disabled or fails — neutral, high-confidence result."""
        return IntentResult(
            category="conversation",
            confidence=1.0,
            rewritten_query=query,
        )
