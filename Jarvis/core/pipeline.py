"""
StreamingPipeline — Overlapping STT → LLM → TTS cascade.

Orchestrates the three stages so they overlap in time:
  - STT result feeds immediately into LLM
  - LLM tokens accumulate into sentences
  - Each sentence is sent to TTS while LLM continues generating

This module provides:
  1. Eager sentence flushing (flush on .!? or after 60+ chars at comma/semicolon)
  2. TTFT (time-to-first-token) tracking per stage
  3. Barge-in support: external signal can cancel the current pipeline
  4. Filler injection: if LLM takes >600ms, speak a filler phrase

Typical latencies (target):
  - Cloud path:  STT(200ms) + LLM-TTFT(300ms) + TTS(100ms) = ~600ms perceived
  - Local path:  STT(400ms) + LLM-TTFT(800ms) + TTS(150ms) = ~1350ms perceived
"""

import logging
import json
import os
import threading
import time
import random
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional, Generator

logger = logging.getLogger("jarvis.pipeline")


# ── Sentence Splitter ───────────────────────────────────────────────────

# Punctuation that ends a sentence (spoken unit)
_SENTENCE_ENDERS = frozenset(".!?")
# Punctuation where we flush mid-sentence if buffer is long enough
_MID_FLUSH_CHARS = frozenset(",;:")
_MID_FLUSH_THRESHOLD = 40  # chars before we flush at a comma
_MAX_BUFFER = 80  # absolute max buffer before forced flush


def eager_sentence_split(token_stream: Generator[str, None, None]):
    """
    Yield (sentence, is_final) tuples from a token stream.

    Flush rules:
      1. Immediately on sentence-ending punctuation (.!?)
      2. At comma/semicolon if buffer > 40 chars
      3. At newline
      4. Forced flush at 80 chars even without punctuation
      5. Final flush when stream ends
    """
    buf = ""
    for token in token_stream:
        buf += token

        # Check for sentence enders
        while buf:
            # Find the earliest sentence ender
            earliest = -1
            for ch in _SENTENCE_ENDERS:
                idx = buf.find(ch)
                if idx != -1 and (earliest == -1 or idx < earliest):
                    earliest = idx

            if earliest != -1:
                # Flush up to and including the ender
                sentence = buf[: earliest + 1].strip()
                buf = buf[earliest + 1 :]
                if sentence and len(sentence) > 3:
                    yield sentence, False
                continue

            # Check for newline flush
            nl_idx = buf.find("\n")
            if nl_idx != -1:
                sentence = buf[:nl_idx].strip()
                buf = buf[nl_idx + 1 :]
                if sentence and len(sentence) > 3:
                    yield sentence, False
                continue

            # Check for mid-flush at commas if buffer long enough
            if len(buf) >= _MID_FLUSH_THRESHOLD:
                flush_idx = -1
                for ch in _MID_FLUSH_CHARS:
                    idx = buf.rfind(ch)
                    if idx != -1 and idx >= _MID_FLUSH_THRESHOLD - 15:
                        if flush_idx == -1 or idx > flush_idx:
                            flush_idx = idx
                if flush_idx != -1:
                    sentence = buf[: flush_idx + 1].strip()
                    buf = buf[flush_idx + 1 :]
                    if sentence and len(sentence) > 3:
                        yield sentence, False
                    continue

            # Forced flush at max buffer
            if len(buf) >= _MAX_BUFFER:
                # Find last space to avoid splitting words
                space_idx = buf.rfind(" ", 0, _MAX_BUFFER)
                if space_idx > 20:
                    sentence = buf[:space_idx].strip()
                    buf = buf[space_idx + 1 :]
                else:
                    sentence = buf[:_MAX_BUFFER].strip()
                    buf = buf[_MAX_BUFFER:]
                if sentence:
                    yield sentence, False
                continue

            break  # nothing to flush yet

    # Final flush
    remaining = buf.strip()
    if remaining and len(remaining) > 1:
        yield remaining, True


# ── Telemetry ───────────────────────────────────────────────────────────

@dataclass
class PipelineMetrics:
    """Timing metrics for the last pipeline run."""
    stt_ms: float = 0.0
    llm_ttft_ms: float = 0.0         # Time to first token
    llm_total_ms: float = 0.0        # Total LLM time
    tts_first_ms: float = 0.0        # Time to first TTS audio ready
    total_perceived_ms: float = 0.0  # STT end → first audio plays
    tokens_generated: int = 0
    sentences_flushed: int = 0
    provider_used: str = ""
    engine_used: str = ""
    filler_spoken: bool = False

    def summary(self) -> str:
        return (
            f"Pipeline: perceived={self.total_perceived_ms:.0f}ms | "
            f"STT={self.stt_ms:.0f}ms | TTFT={self.llm_ttft_ms:.0f}ms | "
            f"TTS={self.tts_first_ms:.0f}ms | tokens={self.tokens_generated} | "
            f"sentences={self.sentences_flushed} | provider={self.provider_used} | "
            f"tts_engine={self.engine_used}"
        )


# ── Fillers ─────────────────────────────────────────────────────────────

FILLER_PHRASES = [
    "Let me check that.",
    "One moment.",
    "Looking into it.",
    "Processing.",
    "On it.",
    "Working on that.",
]

FILLER_TIMEOUT_S = 0.6  # Speak filler if no LLM tokens after this


# ── StreamingPipeline ───────────────────────────────────────────────────

class StreamingPipeline:
    """
    Overlapping STT→LLM→TTS pipeline with barge-in support.

    Usage:
        pipeline = StreamingPipeline(brain, tts)
        metrics = pipeline.run(
            text="What's the weather?",
            token_callback=worker.stream_token.emit,
            begin_callback=worker.stream_begin.emit,
            speak_fn=tts.speak,
        )
    """

    def __init__(self, brain, tts=None):
        self.brain = brain
        self.tts = tts
        self._cancelled = threading.Event()
        self._metrics = PipelineMetrics()

    @property
    def metrics(self) -> PipelineMetrics:
        return self._metrics

    def cancel(self):
        """Cancel the current pipeline run (barge-in)."""
        self._cancelled.set()
        if self.tts:
            self.tts.stop()
        logger.info("Pipeline cancelled (barge-in)")

    def reset(self):
        """Reset cancellation state for new run."""
        self._cancelled.clear()

    def run(
        self,
        text: str,
        token_callback: Optional[Callable[[str], None]] = None,
        begin_callback: Optional[Callable[[], None]] = None,
        speak_fn: Optional[Callable[[str], None]] = None,
        stt_latency_ms: float = 0.0,
    ) -> PipelineMetrics:
        """
        Execute the full pipeline: LLM streaming → sentence splitting → TTS.

        Args:
            text: User query (already transcribed)
            token_callback: Called for each visible token (UI streaming)
            begin_callback: Called when streaming begins
            speak_fn: Called for each sentence to speak (TTS)
            stt_latency_ms: STT latency to include in metrics

        Returns:
            PipelineMetrics with timing data
        """
        self.reset()
        m = PipelineMetrics(stt_ms=stt_latency_ms)
        t_start = time.time()

        # Filler injection
        first_token_event = threading.Event()

        def _filler_thread():
            time.sleep(FILLER_TIMEOUT_S)
            if not first_token_event.is_set() and not self._cancelled.is_set():
                filler = random.choice(FILLER_PHRASES)
                m.filler_spoken = True
                if speak_fn:
                    speak_fn(filler)
                logger.info("Filler spoken: %s", filler)

        filler_t = threading.Thread(target=_filler_thread, daemon=True)
        filler_t.start()

        # Begin streaming
        if begin_callback:
            begin_callback()

        # Token generator with TTFT tracking
        llm_response = ""
        t_llm_start = time.time()

        def _tracked_token_stream():
            nonlocal llm_response
            for token in self.brain.generate_response_stream(text):
                if self._cancelled.is_set():
                    return
                if not first_token_event.is_set():
                    first_token_event.set()
                    m.llm_ttft_ms = (time.time() - t_llm_start) * 1000
                m.tokens_generated += 1
                llm_response += token
                if token_callback:
                    token_callback(token)
                yield token

        # Sentence splitting + TTS
        first_tts_done = False
        t_first_tts = None

        try:
            for sentence, is_final in eager_sentence_split(_tracked_token_stream()):
                if self._cancelled.is_set():
                    break

                m.sentences_flushed += 1

                if speak_fn and sentence.strip():
                    if not first_tts_done:
                        t_first_tts = time.time()
                    speak_fn(sentence)
                    if not first_tts_done:
                        m.tts_first_ms = (time.time() - (t_first_tts or t_start)) * 1000
                        first_tts_done = True

        except Exception as e:
            logger.error("Pipeline error: %s", e, exc_info=True)
            first_token_event.set()  # Prevent late filler

        m.llm_total_ms = (time.time() - t_llm_start) * 1000
        m.total_perceived_ms = m.stt_ms + m.llm_ttft_ms + m.tts_first_ms

        # Record provider/engine info
        if hasattr(self.brain, 'provider_router'):
            m.provider_used = getattr(self.brain.settings, 'provider', '')
        if self.tts:
            m.engine_used = getattr(self.tts, 'engine_used', '')

        self._metrics = m
        logger.info(m.summary())

        # Write telemetry to audit log
        _log_pipeline_metrics(m)

        return m


def _log_pipeline_metrics(metrics: PipelineMetrics):
    """Append pipeline timing to the audit log."""
    try:
        from Jarvis.config import LOGS_DIR
        audit_path = os.path.join(LOGS_DIR, "audit.jsonl")
        entry = {
            "timestamp": time.time(),
            "action_type": "pipeline_metrics",
            "perceived_ms": round(metrics.total_perceived_ms, 1),
            "stt_ms": round(metrics.stt_ms, 1),
            "llm_ttft_ms": round(metrics.llm_ttft_ms, 1),
            "llm_total_ms": round(metrics.llm_total_ms, 1),
            "tts_first_ms": round(metrics.tts_first_ms, 1),
            "tokens": metrics.tokens_generated,
            "sentences": metrics.sentences_flushed,
            "provider": metrics.provider_used,
            "tts_engine": metrics.engine_used,
            "filler": metrics.filler_spoken,
        }
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug("Failed to log pipeline metrics: %s", e)
