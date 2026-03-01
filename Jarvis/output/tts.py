import asyncio
import edge_tts
import threading
import os
import time
import queue
import logging
from PyQt6.QtCore import QObject, pyqtSignal
from Jarvis.config import TTS_VOICE, DATA_DIR

logger = logging.getLogger("jarvis.tts")

class TTS(QObject):
    audio_generated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._voice = TTS_VOICE
        self._rate = "+15%"
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        
        # Ensure temp directory exists
        self._temp_dir = os.path.join(DATA_DIR, "temp_tts")
        os.makedirs(self._temp_dir, exist_ok=True)
        
        # Start the worker thread
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

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

    # ── Speech Synthesis ─────────────────────────────────────────────────

    def speak(self, text: str, priority: bool = False) -> None:
        """
        Add text to the speech queue.
        If priority is True, it could potentially clear the queue (not implemented yet for safety).
        """
        if not text.strip():
            return
        
        # Basic sanitization: remove any remaining tags
        import re
        text = re.sub(r"\[/?(ACTION|SHELL|EXEC_CODE|SYSTEMINFO).*?\]", "", text, flags=re.I).strip()
        
        if text:
            self._queue.put(text)

    def stop(self):
        """Clear the queue and stop current speech."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        # We don't have a direct way to stop the QMediaPlayer from here, 
        # but clearing the queue prevents further speech.

    def _worker(self):
        """Background worker to process the speech queue."""
        while not self._stop_event.is_set():
            try:
                text = self._queue.get(timeout=1)
                self._process_text(text)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error("TTS Worker error: %s", e)

    def _process_text(self, text):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._speak_async(text))
            loop.close()
        except Exception as e:
            logger.error("TTS Processing error: %s", e)

    async def _speak_async(self, text):
        # Truncate long responses for TTS (speak only reasonable chunks)
        if len(text) > 500:
            text = text[:500] + "..."

        # Unique filename to avoid race conditions
        filename = f"tts_{int(time.time() * 1000)}.mp3"
        output_file = os.path.abspath(os.path.join(self._temp_dir, filename))
        
        try:
            communicate = edge_tts.Communicate(text, self._voice, rate=self._rate)
            await communicate.save(output_file)
            
            if os.path.exists(output_file):
                self.audio_generated.emit(output_file)
                
                # We need to wait a bit so the player can actually start before we move to next text?
                # Actually, the UI player will queue them if we're not careful.
                # For now, we'll just emit and let the player handle it.
                # In a more advanced version, we'd wait for a 'playback_finished' signal.
                
        except Exception as e:
            logger.error("Edge TTS failure: %s", e)
