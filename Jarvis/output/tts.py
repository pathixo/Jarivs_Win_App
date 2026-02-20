import asyncio
import edge_tts
import threading
import os
from PyQt6.QtCore import QObject, pyqtSignal
from Jarvis.config import TTS_VOICE

class TTS(QObject):
    audio_generated = pyqtSignal(str)

    def speak(self, text):
        """
        Synthesizes speech from text using Edge TTS.
        Function is non-blocking (runs in thread).
        """
        threading.Thread(target=self._run_speak, args=(text,), daemon=True).start()

    def _run_speak(self, text):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._speak_async(text))
            loop.close()
        except Exception as e:
            print(f"TTS Error: {e}")

    async def _speak_async(self, text):
        # Truncate long responses for TTS (speak only first ~200 chars)
        if len(text) > 250:
            text = text[:250] + "..."
        
        # Use +15% speed for snappier delivery
        communicate = edge_tts.Communicate(text, TTS_VOICE, rate="+15%")
        output_file = os.path.abspath("temp_tts.mp3")
        await communicate.save(output_file)
        
        self.audio_generated.emit(output_file)

