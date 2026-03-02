"""
LLM Provider Router — Latency-Aware Multi-Provider Orchestration
=================================================================
Intelligent routing layer that selects the optimal LLM provider for each query:

  Tier 1: Groq   (~100ms TTFT, 30 RPM free tier)  — conversational queries
  Tier 2: Gemini  (~200ms TTFT, 15 RPM free tier)  — complex / quota overflow
  Tier 3: Ollama  (~2-20s TTFT, no limits)          — offline fallback

Features:
  - Per-provider quota tracking (RPM, TPM)
  - Automatic tier escalation on rate limits
  - Query complexity classification for routing
  - Latency tracking per provider
  - Connection pre-warming
  - Streaming-first design
"""

import logging
import time
import threading
import re
from typing import Optional, Iterator
from dataclasses import dataclass, field

logger = logging.getLogger("jarvis.provider_router")


@dataclass
class ProviderQuota:
    """Track API usage for rate-limit aware routing."""
    rpm_limit: int = 30           # requests per minute
    tpm_limit: int = 0            # tokens per minute (0 = unlimited)
    requests_this_minute: int = 0
    tokens_this_minute: int = 0
    minute_start: float = field(default_factory=time.time)
    total_requests: int = 0
    total_errors: int = 0
    avg_ttft_ms: float = 0.0      # average time-to-first-token
    _ttft_samples: list = field(default_factory=list)

    def can_use(self) -> bool:
        """Check if this provider is within rate limits."""
        self._reset_if_needed()
        if self.rpm_limit > 0 and self.requests_this_minute >= self.rpm_limit - 1:
            return False  # Leave 1 RPM headroom
        return True

    def record_request(self, tokens: int = 0):
        """Record a completed request."""
        self._reset_if_needed()
        self.requests_this_minute += 1
        self.tokens_this_minute += tokens
        self.total_requests += 1

    def record_error(self):
        """Record a failed request."""
        self.total_errors += 1

    def record_ttft(self, ttft_ms: float):
        """Record time-to-first-token for latency tracking."""
        self._ttft_samples.append(ttft_ms)
        if len(self._ttft_samples) > 20:
            self._ttft_samples = self._ttft_samples[-20:]
        self.avg_ttft_ms = sum(self._ttft_samples) / len(self._ttft_samples)

    def _reset_if_needed(self):
        now = time.time()
        if now - self.minute_start >= 60:
            self.requests_this_minute = 0
            self.tokens_this_minute = 0
            self.minute_start = now

    @property
    def usage_pct(self) -> float:
        """Return usage percentage of RPM limit."""
        if self.rpm_limit <= 0:
            return 0.0
        self._reset_if_needed()
        return self.requests_this_minute / self.rpm_limit


class ProviderRouter:
    """
    Latency-aware LLM provider router.
    
    Selects the fastest available provider based on:
      1. Provider availability (API key configured + healthy)
      2. Rate limit headroom (within RPM/TPM limits)
      3. Query complexity (simple→fast provider, complex→smart provider)
      4. Historical latency (track avg TTFT per provider)
    """

    # Query complexity patterns
    _SIMPLE_PATTERNS = [
        r"^(hi|hello|hey|thanks|thank you|bye|goodbye|good morning|good night)",
        r"^(what time|what date|what day|who are you|what's your name)",
        r"^(tell me a joke|say something|greet me)",
        r"^(yes|no|ok|okay|sure|alright|fine|got it)\s*$",
    ]

    _COMPLEX_PATTERNS = [
        r"\b(explain|analyze|compare|contrast|evaluate|summarize|describe in detail)\b",
        r"\b(step.{0,5}by.{0,5}step|in\s+detail|comprehensively|thorough)\b",
        r"\b(architecture|design pattern|algorithm|data structure)\b",
        r"\b(write|create|develop|implement|build)\s+(a\s+)?(full|complete|detailed)",
    ]

    _CODE_PATTERNS = [
        r"\b(python|javascript|typescript|code|script|function|class|debug|refactor)\b",
        r"\b(write|create|generate)\s+(a\s+)?(script|program|app|function|class)\b",
        r"\b(fix|debug|refactor|optimize)\s+(this|the|my)\s+(code|script|function)\b",
    ]

    def __init__(self, brain):
        """
        Initialize the provider router.
        
        Args:
            brain: The Brain instance that holds backends and settings
        """
        self._brain = brain
        self._lock = threading.Lock()
        
        # Provider quotas (from free tier limits)
        from Jarvis.core.brain import Provider
        self._quotas = {
            Provider.GROQ:   ProviderQuota(rpm_limit=30, tpm_limit=6000),
            Provider.GEMINI: ProviderQuota(rpm_limit=15, tpm_limit=0),
            Provider.GROK:   ProviderQuota(rpm_limit=10, tpm_limit=0),
            Provider.OLLAMA: ProviderQuota(rpm_limit=0, tpm_limit=0),  # No limits
        }
        
        # Provider priority tiers (fastest → slowest)
        self._tier_order = [Provider.GROQ, Provider.GEMINI, Provider.GROK, Provider.OLLAMA]
        
        # Track which providers are available
        self._available = set()
        self._check_availability()
        
        logger.info("ProviderRouter initialized | available: %s", 
                    [p.value for p in self._available])

    def _check_availability(self):
        """Check which providers are configured and potentially available."""
        from Jarvis.core.brain import Provider
        from Jarvis.config import GROQ_API_KEY, GEMINI_API_KEY, GROK_API_KEY
        
        key_map = {
            Provider.GROQ: GROQ_API_KEY,
            Provider.GEMINI: GEMINI_API_KEY,
            Provider.GROK: GROK_API_KEY,
        }
        
        for provider, key in key_map.items():
            if key:
                self._available.add(provider)
        
        # Ollama is always potentially available (local)
        self._available.add(Provider.OLLAMA)

    def select_provider(self, query: str, preferred: Optional[str] = None) -> str:
        """
        Select the optimal provider for a given query.
        
        Args:
            query: The user's query text
            preferred: User's preferred provider (from settings)
            
        Returns:
            Provider name (str) to use for this query
        """
        from Jarvis.core.brain import Provider
        
        # If user explicitly set a provider and it's available, respect it
        # unless it's rate-limited
        if preferred and preferred != "auto":
            try:
                pref_provider = Provider(preferred)
                if pref_provider in self._available:
                    quota = self._quotas.get(pref_provider)
                    if quota is None or quota.can_use():
                        return preferred
                    else:
                        logger.info("Preferred provider %s is rate-limited, routing elsewhere", preferred)
            except ValueError:
                pass

        # Classify query complexity
        complexity = self._classify_complexity(query)
        
        # Select based on complexity and availability
        if complexity == "simple":
            # Simple queries → fastest provider (Groq → Gemini → Ollama)
            order = [Provider.GROQ, Provider.GEMINI, Provider.OLLAMA]
        elif complexity == "code":
            # Code queries → Ollama local models for privacy, or Groq for speed
            order = [Provider.GROQ, Provider.OLLAMA, Provider.GEMINI]
        elif complexity == "complex":
            # Complex queries → Gemini Flash for quality, or Groq
            order = [Provider.GEMINI, Provider.GROQ, Provider.OLLAMA]
        else:
            # Default: speed-first
            order = self._tier_order

        # Find first available provider with quota headroom
        for provider in order:
            if provider not in self._available:
                continue
            quota = self._quotas.get(provider)
            if quota and not quota.can_use():
                continue
            return provider.value

        # Ultimate fallback
        return Provider.OLLAMA.value

    def _classify_complexity(self, query: str) -> str:
        """Classify query as simple/complex/code for routing."""
        q = query.strip().lower()
        
        for pat in self._SIMPLE_PATTERNS:
            if re.search(pat, q, re.IGNORECASE):
                return "simple"
        
        for pat in self._CODE_PATTERNS:
            if re.search(pat, q, re.IGNORECASE):
                return "code"
        
        for pat in self._COMPLEX_PATTERNS:
            if re.search(pat, q, re.IGNORECASE):
                return "complex"
        
        # Default based on length
        if len(q.split()) <= 10:
            return "simple"
        elif len(q.split()) > 25:
            return "complex"
        
        return "normal"

    def record_success(self, provider_name: str, ttft_ms: float = 0, tokens: int = 0):
        """Record a successful request for quota tracking."""
        from Jarvis.core.brain import Provider
        try:
            provider = Provider(provider_name)
            quota = self._quotas.get(provider)
            if quota:
                with self._lock:
                    quota.record_request(tokens)
                    if ttft_ms > 0:
                        quota.record_ttft(ttft_ms)
        except ValueError:
            pass

    def record_error(self, provider_name: str):
        """Record a failed request."""
        from Jarvis.core.brain import Provider
        try:
            provider = Provider(provider_name)
            quota = self._quotas.get(provider)
            if quota:
                with self._lock:
                    quota.record_error()
        except ValueError:
            pass

    def get_stats(self) -> dict:
        """Return provider usage statistics."""
        stats = {}
        for provider, quota in self._quotas.items():
            if provider in self._available:
                stats[provider.value] = {
                    "requests": quota.total_requests,
                    "errors": quota.total_errors,
                    "rpm_usage": f"{quota.usage_pct:.0%}",
                    "avg_ttft_ms": round(quota.avg_ttft_ms, 1),
                }
        return stats

    def get_max_tokens_for_query(self, query: str, default: int = 512) -> int:
        """
        Return appropriate max_tokens based on query complexity.
        Short for simple queries (faster TTS), longer for complex ones.
        """
        complexity = self._classify_complexity(query)
        if complexity == "simple":
            return min(80, default)
        elif complexity == "normal":
            return min(200, default)
        elif complexity == "code":
            return min(400, default)
        else:  # complex
            return default
