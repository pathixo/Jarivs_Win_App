import asyncio
import edge_tts
import threading
import os
import time
import queue
import logging
from PyQt6.QtCore import QObject, pyqtSignal
from Jarvis.config import TTS_VOICE, DATA_DIR, TTS_ENGINE, KOKORO_MODEL_PATH, KOKORO_VOICES_PATH

logger = logging.getLogger("jarvis.tts")

# Voice constants
VOICE_ENGLISH = TTS_VOICE                    # e.g. en-GB-LibbyNeural
VOICE_HINDI   = "hi-IN-SwaraNeural"          # Female Hindi voice


class TTS(QObject):
    """
    Multi-engine TTS with automatic routing.

    Engine selection (TTS_ENGINE config):
      - "auto"   → Kokoro (local GPU) with edge-tts fallback
      - "kokoro" → Always use Kokoro ONNX (lowest latency, ~50-150ms)
      - "edge"   → Always use edge-tts (Microsoft cloud, ~300-600ms)

    Signals:
      audio_generated(str)     — emitted with WAV/MP3 path for QMediaPlayer
      tts_started()            — emitted when speech synthesis begins
      tts_finished()           — emitted when all queued speech is done
      playback_started()       — emitted when audio playback begins
      playback_finished()      — emitted when audio playback ends
    """
    audio_generated = pyqtSignal(str)
    tts_started = pyqtSignal()
    tts_finished = pyqtSignal()
    playback_started = pyqtSignal()
    playback_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._voice = TTS_VOICE
        self._rate = "+15%"
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._language_mode = "auto"   # "auto", "en", "hi"
        self._is_speaking = False
        self._engine = TTS_ENGINE.lower()

        # Ensure temp directory exists
        self._temp_dir = os.path.join(DATA_DIR, "temp_tts")
        os.makedirs(self._temp_dir, exist_ok=True)

        # Initialize Kokoro TTS engine (local GPU)
        self._kokoro = None
        if self._engine in ("auto", "kokoro"):
            try:
                from Jarvis.output.kokoro_tts import KokoroTTS
                self._kokoro = KokoroTTS(
                    model_path=KOKORO_MODEL_PATH,
                    voices_path=KOKORO_VOICES_PATH,
                )
                if self._kokoro.available:
                    logger.info("Kokoro TTS engine loaded (local GPU)")
                else:
                    logger.info("Kokoro TTS unavailable, will use edge-tts")
                    self._kokoro = None
            except Exception as e:
                logger.warning("Kokoro TTS init failed: %s — using edge-tts", e)
                self._kokoro = None

        # Persistent event loop for edge-tts (avoids creating new loop per request)
        self._edge_loop = asyncio.new_event_loop()
        self._edge_loop_thread = threading.Thread(
            target=self._run_edge_loop, daemon=True, name="edge-tts-loop"
        )
        self._edge_loop_thread.start()

        # Start the worker thread
        self._worker_thread = threading.Thread(target=self._worker, daemon=True, name="tts-worker")
        self._worker_thread.start()

        # Latency telemetry
        self._last_latency_ms = 0.0
        self._engine_used = "none"

    def _run_edge_loop(self):
        """Run a persistent asyncio event loop for edge-tts."""
        asyncio.set_event_loop(self._edge_loop)
        self._edge_loop.run_forever()

    @property
    def is_speaking(self) -> bool:
        """Whether TTS is currently generating or playing audio."""
        return self._is_speaking

    @property
    def last_latency_ms(self) -> float:
        """Latency of the last TTS synthesis in milliseconds."""
        return self._last_latency_ms

    @property
    def engine_used(self) -> str:
        """Name of the engine used for the last synthesis."""
        return self._engine_used

    # ── Voice Control ────────────────────────────────────────────────────

    def set_voice(self, voice_id: str) -> None:
        """Change the TTS voice (e.g., 'en-GB-RyanNeural')."""
        self._voice = voice_id

    def set_rate(self, rate: str) -> None:
        """Change the TTS rate (e.g., '+10%', '-5%')."""
        self._rate = rate

    def get_voice(self) -> str:
        """Return the current TTS voice ID."""
        return self._voice

    def set_language_mode(self, mode: str) -> bool:
        """
        Set TTS language mode (Hindi/English only).
        
        Args:
            mode: 'auto' (detect per-text), 'en' (always English), 'hi' (always Hindi)
            
        Returns:
            True if language set successfully, False if unsupported
        """
        mode_lower = mode.lower()
        if mode_lower not in ("auto", "en", "hi"):
            logger.warning("Unsupported language mode: %s. Only 'auto', 'en', 'hi' supported.", mode)
            return False
        
        self._language_mode = mode_lower
        if mode_lower == "hi":
            self._voice = VOICE_HINDI
        elif mode_lower == "en":
            self._voice = VOICE_ENGLISH
        logger.info("TTS language mode set to: %s", mode_lower)
        return True

    @staticmethod
    def _detect_script(text: str) -> str:
        """Return 'hi' if text has significant Devanagari content, else 'en'."""
        devanagari = sum(1 for c in text if '\u0900' <= c <= '\u097F')
        return "hi" if devanagari / max(len(text), 1) > 0.15 else "en"

    # ── Speech Synthesis ─────────────────────────────────────────────────

    def _clean_for_speech(self, text: str) -> str:
        """Sanitize Markdown and URLs for natural speech synthesis."""
        import re
        
        # 1. Strip Action/Shell tags (already done in orchestrator, but for safety)
        text = re.sub(r"\[/?(ACTION|SHELL|EXEC_CODE|SYSTEMINFO).*?\]", "", text, flags=re.I).strip()
        
        # 2. Markdown Bold/Italic (**text**, __text__, *text*, _text_)
        # We remove the symbols but keep the content.
        text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
        text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
        
        # 3. Markdown Headings (# Heading)
        # We remove the hashes and just read the content.
        text = re.sub(r"^#+\s+", "", text, flags=re.M)
        
        # 4. Dividers (---, ===) - Remove entirely
        text = re.sub(r"^[=\-]{3,}$", "", text, flags=re.M)
        
        # 5. Bullet points (- item, * item)
        # User requested: Spoken as "bullet", no dash read aloud.
        # So we replace the dash with the word "bullet".
        text = re.sub(r"^[ \t]*[\-\*][ \t]+", "bullet ", text, flags=re.M)
        
        # 6. Numbered lists (1. item) - Usually fine to read as "one dot" or just "one"
        # We'll leave them as is for now or slightly clean them.
        
        # 7. Inline Code (`code`)
        text = re.sub(r"`(.*?)`", r"\1", text)
        
        # 8. URLs (https://...) - Don't read full URLs, just say "link"
        text = re.sub(r"https?://\S+", "link", text)
        text = re.sub(r"www\.\S+", "URL", text)
        
        # 9. Truncated markers
        text = text.replace("(truncated)", "").replace("...", ".")
        
        # 10. Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        
        return text

    def speak(self, text: str, priority: bool = False) -> None:
        """
        Add text to the speech queue.
        If priority is True, it could potentially clear the queue (not implemented yet for safety).
        """
        if not text.strip():
            return
        
        # Strip action/system tags first
        import re
        text = re.sub(r"\[/?(ACTION|SHELL|EXEC_CODE|SYSTEMINFO).*?\]", "", text, flags=re.I)
        # Clean markdown/formatting symbols
        text = self._clean_for_speech(text).strip()
        
        if text:
            self._queue.put(text)

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """
        Strip markdown and formatting symbols so they are not read aloud.
        Bold **text** → text, headers # Heading → Heading, URLs → silenced, etc.
        """
        import re

        # 1. Markdown headers  (## Heading → Heading)  — must run first
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

        # 2. Bold/italic markers  (**text** / *text* / __text__ / _text_)
        text = re.sub(r"\*{1,3}([^*]+?)\*{1,3}", r"\1", text)
        text = re.sub(r"_{1,2}([^_]+?)_{1,2}", r"\1", text)

        # 3. Inline code  (`code` → code)
        text = re.sub(r"`{1,3}(.+?)`{1,3}", r"\1", text, flags=re.DOTALL)

        # 4. Remaining action/system tags
        text = re.sub(r"\[.*?\]", "", text)

        # 5. Horizontal rules  (--- / *** / ___)
        text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

        # 6. Blockquotes  (> text → text)
        text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)

        # 7. Bullet points  (- item / * item / + item → item)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)

        # 8. Numbered lists  (1. item → item)
        text = re.sub(r"^\s*\d+[.)]\s+", "", text, flags=re.MULTILINE)

        # 9. Silence long URLs — don't read https://... aloud
        text = re.sub(r"https?://\S+", "the link", text)

        # 10. Markdown links [label](url) → label
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

        # 11. Remove leftover: ~, ^, |
        text = re.sub(r"[~^|]", "", text)

        # 12. Remove trailing "..." or "(truncated)"
        text = re.sub(r"\.\.\.$", "", text.strip())
        text = re.sub(r"\(truncated\)", "", text, flags=re.IGNORECASE)

        # 13. Collapse whitespace / newlines
        text = re.sub(r"\n{2,}", ". ", text)
        text = re.sub(r"\n", " ", text)
        text = re.sub(r"\s{2,}", " ", text)

        return text.strip()

    def stop(self):
        """Clear the queue and stop current speech. Signal barge-in."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._is_speaking = False
        self.tts_finished.emit()

    def _worker(self):
        """Background worker to process the speech queue."""
        while not self._stop_event.is_set():
            try:
                text = self._queue.get(timeout=1)
                self._is_speaking = True
                self.tts_started.emit()
                self._process_text(text)
                self._queue.task_done()
                # Check if queue is now empty
                if self._queue.empty():
                    self._is_speaking = False
                    self.tts_finished.emit()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error("TTS Worker error: %s", e)
                self._is_speaking = False

    def _process_text(self, text):
        """Route text to the best available TTS engine."""
        t0 = time.time()

        # Try Kokoro first (local, lowest latency)
        if self._kokoro and self._engine in ("auto", "kokoro"):
            success = self._process_with_kokoro(text)
            if success:
                self._last_latency_ms = (time.time() - t0) * 1000
                self._engine_used = "kokoro"
                logger.info("TTS latency: %.0fms (kokoro)", self._last_latency_ms)
                return

        # Fall back to edge-tts
        success = self._process_with_edge(text)
        self._last_latency_ms = (time.time() - t0) * 1000
        self._engine_used = "edge"
        logger.info("TTS latency: %.0fms (edge-tts)", self._last_latency_ms)

    def _process_with_kokoro(self, text: str) -> bool:
        """Synthesize using Kokoro (local GPU) and emit file path."""
        # Truncate long text
        if len(text) > 500:
            text = text[:500]

        filename = f"tts_{int(time.time() * 1000)}.wav"
        output_file = os.path.abspath(os.path.join(self._temp_dir, filename))

        success = self._kokoro.synthesize_to_wav(text, output_file)
        if success and os.path.exists(output_file):
            self.audio_generated.emit(output_file)
            return True
        return False

    def _process_with_edge(self, text: str) -> bool:
        """Synthesize using edge-tts (cloud) and emit file path."""
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._speak_async(text), self._edge_loop
            )
            future.result(timeout=15)  # Wait up to 15s for cloud TTS
            return True
        except Exception as e:
            logger.error("Edge TTS processing error: %s", e)
            return False

    async def _speak_async(self, text):
        # Truncate long responses for TTS (speak only reasonable chunks)
        if len(text) > 500:
            text = text[:500]

        # Auto-select voice: detect Hindi (Devanagari) vs English
        if self._language_mode == "auto":
            lang = self._detect_script(text)
            voice = VOICE_HINDI if lang == "hi" else self._voice
        elif self._language_mode == "hi":
            voice = VOICE_HINDI
        else:
            voice = self._voice

        # Unique filename to avoid race conditions
        filename = f"tts_{int(time.time() * 1000)}.mp3"
        output_file = os.path.abspath(os.path.join(self._temp_dir, filename))
        
        try:
            communicate = edge_tts.Communicate(text, voice, rate=self._rate)
            await communicate.save(output_file)
            
            if os.path.exists(output_file):
                self.audio_generated.emit(output_file)
                
        except Exception as e:
            logger.error("Edge TTS failure: %s", e)

