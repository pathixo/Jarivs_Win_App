"""
Memory Engine — AI Personalization Memory for Jarvis
=====================================================
ChatGPT-style memory system that stores facts about the user for
context injection into LLM prompts.

Two acquisition modes:
  1. **Explicit**: User says "remember that I prefer dark mode"
  2. **Auto-extract**: After each LLM turn, a lightweight Groq prompt
     extracts personal facts from the conversation.

Facts are stored in SQLite, deduplicated by word-overlap, and injected
into the system prompt as a "User Context" block.

Usage:
    from Jarvis.core.memory_engine import get_memory_engine
    engine = get_memory_engine()
    engine.add_explicit("I prefer dark mode", context="User said: ...")
    facts = engine.get_relevant_memories("What theme do I like?")
"""

import json
import logging
import re
import threading
import time
from typing import Optional

from Jarvis.core.database import get_database

logger = logging.getLogger("jarvis.memory")

# ─────────────────────────── Constants ──────────────────────────────────────

# Patterns that trigger explicit memory storage
EXPLICIT_PATTERNS = [
    re.compile(r"(?:please\s+)?remember\s+(?:that\s+)?(.+)", re.IGNORECASE),
    re.compile(r"(?:my\s+name\s+is|i'?m\s+called?|call\s+me)\s+(.+)", re.IGNORECASE),
    re.compile(r"i\s+(?:prefer|like|love|hate|dislike|always|never|usually)\s+(.+)", re.IGNORECASE),
    re.compile(r"(?:don'?t\s+forget|keep\s+in\s+mind)\s+(?:that\s+)?(.+)", re.IGNORECASE),
    re.compile(r"(?:i\s+am|i'?m)\s+(?:a\s+|an\s+)?(\w[\w\s]{2,30})", re.IGNORECASE),
    re.compile(r"(?:i\s+work\s+(?:at|for|in|as))\s+(.+)", re.IGNORECASE),
    re.compile(r"(?:i\s+live\s+in|i'?m\s+from|i\s+stay\s+in)\s+(.+)", re.IGNORECASE),
    re.compile(r"(?:my\s+(?:favorite|favourite)\s+\w+\s+is)\s+(.+)", re.IGNORECASE),
]

# Auto-extraction prompt (sent to Groq after each conversation turn)
AUTO_EXTRACT_PROMPT = """Analyze this conversation exchange and extract any personal facts, preferences, 
or important details the user revealed about themselves. Focus on:
- Name, age, location, occupation
- Preferences (tools, languages, frameworks, themes, etc.)
- Habits and routines  
- Important dates or events
- Technical setup or environment details

Return ONLY a JSON array of extracted facts as short strings. 
If no personal facts were revealed, return an empty array [].

Examples:
- ["User's name is Alex", "User prefers dark mode", "User works at Google"]
- ["User uses Python 3.11", "User's birthday is March 15"]
- []

User message: {user_msg}
Assistant response: {assistant_msg}

Extracted facts (JSON array only):"""

# Word-overlap threshold for deduplication
DEDUP_THRESHOLD = 0.6

# Maximum memories to inject into prompts
MAX_PROMPT_MEMORIES = 15

# ─────────────────────────── Singleton ──────────────────────────────────────

_instance: Optional["MemoryEngine"] = None


def get_memory_engine() -> "MemoryEngine":
    """Return the global MemoryEngine singleton."""
    global _instance
    if _instance is None:
        _instance = MemoryEngine()
    return _instance


# ─────────────────────────── MemoryEngine ───────────────────────────────────

class MemoryEngine:
    """
    AI personalization memory with explicit + auto-extraction modes.

    Thread-safe. Auto-extraction runs in background threads to avoid
    blocking the main pipeline.
    """

    def __init__(self, user_id: str | None = None):
        self._db = get_database()
        self._user_id = user_id
        self._lock = threading.Lock()
        self._extract_semaphore = threading.Semaphore(1)  # limit concurrent extractions

    # ── Lazy user resolution ─────────────────────────────────────────────

    def _ensure_user(self) -> str:
        if not self._user_id:
            from Jarvis.core.user_profile import get_profile_manager
            self._user_id = get_profile_manager().current_user_id
        return self._user_id

    # ── Explicit Memory ──────────────────────────────────────────────────

    def try_explicit_save(self, user_text: str) -> Optional[str]:
        """
        Check if user text contains an explicit memory request and save it.
        Returns the extracted fact string if saved, or None.
        """
        fact = self.check_explicit_memory(user_text)
        if fact:
            success = self.add_explicit(fact, context=f"User said: {user_text}")
            return fact if success else None
        return None

    def check_explicit_memory(self, user_text: str) -> Optional[str]:
        """
        Check if user text contains an explicit memory request.
        Returns the extracted fact string, or None if no match.
        """
        for pattern in EXPLICIT_PATTERNS:
            m = pattern.search(user_text)
            if m:
                fact = m.group(1).strip().rstrip(".,!?")
                if len(fact) >= 3:
                    return fact
        return None

    def add_explicit(self, fact: str, context: str = "") -> bool:
        """
        Store an explicitly requested memory.
        Returns True if stored, False if duplicate.
        """
        if self._is_duplicate(fact):
            logger.debug("Duplicate memory skipped: %s", fact[:50])
            return False

        uid = self._ensure_user()
        now = time.time()
        self._db.execute(
            "INSERT INTO memories (user_id, fact, source, context, confidence, active, created_at, updated_at) "
            "VALUES (?, ?, 'explicit', ?, 1.0, 1, ?, ?)",
            (uid, fact, context, now, now),
        )
        logger.info("Explicit memory stored: %s", fact[:60])
        return True

    # ── Auto-Extraction ──────────────────────────────────────────────────

    def auto_extract_async(
        self,
        user_msg: str,
        assistant_msg: str,
        confidence_threshold: float = 0.7,
    ) -> None:
        """
        Trigger auto-extraction in a background thread.
        Rate-limited by semaphore (max 1 concurrent extraction).
        """
        if not self._extract_semaphore.acquire(blocking=False):
            logger.debug("Auto-extraction skipped (already running)")
            return

        def _extract():
            try:
                self._do_auto_extract(user_msg, assistant_msg, confidence_threshold)
            finally:
                self._extract_semaphore.release()

        threading.Thread(target=_extract, daemon=True, name="memory-extract").start()

    def _do_auto_extract(
        self,
        user_msg: str,
        assistant_msg: str,
        confidence_threshold: float,
    ) -> None:
        """Run the actual extraction via Groq (cheapest/fastest provider)."""
        try:
            from Jarvis.config import GROQ_API_KEY
            if not GROQ_API_KEY:
                logger.debug("Groq API key not set, skipping auto-extraction")
                return

            import httpx

            prompt = AUTO_EXTRACT_PROMPT.format(
                user_msg=user_msg[:500],
                assistant_msg=assistant_msg[:500],
            )

            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama3-8b-8192",  # smallest/cheapest model
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 200,
                },
                timeout=10.0,
            )

            if resp.status_code != 200:
                logger.warning("Groq extraction failed: %d", resp.status_code)
                return

            content = resp.json()["choices"][0]["message"]["content"].strip()

            # Parse JSON array from response
            facts = self._parse_facts_json(content)
            if not facts:
                return

            uid = self._ensure_user()
            now = time.time()
            context = f"User: {user_msg[:200]}"

            for fact in facts:
                fact = fact.strip()
                if len(fact) < 3 or self._is_duplicate(fact):
                    continue
                self._db.execute(
                    "INSERT INTO memories (user_id, fact, source, context, confidence, active, created_at, updated_at) "
                    "VALUES (?, ?, 'auto', ?, ?, 1, ?, ?)",
                    (uid, fact, context, confidence_threshold, now, now),
                )
                logger.info("Auto-extracted memory: %s", fact[:60])

        except Exception as e:
            logger.warning("Auto-extraction error: %s", e)

    @staticmethod
    def _parse_facts_json(content: str) -> list[str]:
        """Parse a JSON array of fact strings from LLM output."""
        # Try direct parse
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return [str(f) for f in parsed if f and isinstance(f, str)]
        except json.JSONDecodeError:
            pass

        # Try to find JSON array within the text
        match = re.search(r"\[.*?\]", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    return [str(f) for f in parsed if f and isinstance(f, str)]
            except json.JSONDecodeError:
                pass

        return []

    # ── Recall / Query ───────────────────────────────────────────────────

    def get_relevant_memories(self, query: str = "", limit: int = MAX_PROMPT_MEMORIES) -> list[dict]:
        """
        Retrieve active memories, optionally ranked by keyword relevance.
        Returns list of dicts with keys: id, fact, source, confidence, created_at.
        """
        uid = self._ensure_user()

        if query:
            # Keyword-based relevance: score memories by word overlap with query
            all_memories = self._db.fetch_all(
                "SELECT id, fact, source, confidence, created_at FROM memories "
                "WHERE user_id = ? AND active = 1 ORDER BY created_at DESC",
                (uid,),
            )
            query_words = set(query.lower().split())
            scored = []
            for row in all_memories:
                fact_words = set(row["fact"].lower().split())
                overlap = len(query_words & fact_words)
                score = overlap / max(len(query_words), 1)
                scored.append((score, dict(row)))

            # Sort by relevance (descending), then by recency
            scored.sort(key=lambda x: (-x[0], -x[1].get("created_at", 0)))
            return [item[1] for item in scored[:limit]]
        else:
            # No query — return most recent
            rows = self._db.fetch_all(
                "SELECT id, fact, source, confidence, created_at FROM memories "
                "WHERE user_id = ? AND active = 1 ORDER BY created_at DESC LIMIT ?",
                (uid, limit),
            )
            return [dict(r) for r in rows]

    def get_all_memories(self, include_inactive: bool = False) -> list[dict]:
        """Return all memories for the current user."""
        uid = self._ensure_user()
        if include_inactive:
            rows = self._db.fetch_all(
                "SELECT * FROM memories WHERE user_id = ? ORDER BY created_at DESC",
                (uid,),
            )
        else:
            rows = self._db.fetch_all(
                "SELECT * FROM memories WHERE user_id = ? AND active = 1 ORDER BY created_at DESC",
                (uid,),
            )
        return [dict(r) for r in rows]

    def format_for_prompt(self, query: str = "") -> str:
        """
        Format relevant memories as a text block for LLM prompt injection.
        Returns empty string if no memories exist.
        """
        memories = self.get_relevant_memories(query)
        if not memories:
            return ""

        lines = ["## Known Facts About the User"]
        for m in memories:
            lines.append(f"- {m['fact']}")

        return "\n".join(lines)

    # ── Memory Management ────────────────────────────────────────────────

    def delete_memory(self, memory_id: int) -> bool:
        """Soft-delete a memory by ID."""
        uid = self._ensure_user()
        cursor = self._db.execute(
            "UPDATE memories SET active = 0, updated_at = ? WHERE id = ? AND user_id = ?",
            (time.time(), memory_id, uid),
        )
        return cursor.rowcount > 0

    def clear_all_memories(self) -> int:
        """Soft-delete all memories for the current user. Returns count."""
        uid = self._ensure_user()
        cursor = self._db.execute(
            "UPDATE memories SET active = 0, updated_at = ? WHERE user_id = ? AND active = 1",
            (time.time(), uid),
        )
        count = cursor.rowcount
        logger.info("Cleared %d memories", count)
        return count

    def get_memory_count(self) -> dict:
        """Return memory statistics."""
        uid = self._ensure_user()
        total = self._db.fetch_scalar(
            "SELECT COUNT(*) FROM memories WHERE user_id = ? AND active = 1",
            (uid,), default=0,
        )
        auto = self._db.fetch_scalar(
            "SELECT COUNT(*) FROM memories WHERE user_id = ? AND active = 1 AND source = 'auto'",
            (uid,), default=0,
        )
        explicit = self._db.fetch_scalar(
            "SELECT COUNT(*) FROM memories WHERE user_id = ? AND active = 1 AND source = 'explicit'",
            (uid,), default=0,
        )
        return {"total": total, "auto": auto, "explicit": explicit}

    # ── Deduplication ────────────────────────────────────────────────────

    def _is_duplicate(self, new_fact: str) -> bool:
        """Check if a semantically similar fact already exists (word overlap)."""
        uid = self._ensure_user()
        existing = self._db.fetch_all(
            "SELECT fact FROM memories WHERE user_id = ? AND active = 1",
            (uid,),
        )

        new_words = set(new_fact.lower().split())
        if not new_words:
            return False

        for row in existing:
            existing_words = set(row["fact"].lower().split())
            if not existing_words:
                continue
            # Jaccard-like overlap
            intersection = len(new_words & existing_words)
            union = len(new_words | existing_words)
            if union > 0 and (intersection / union) >= DEDUP_THRESHOLD:
                return True

        return False
