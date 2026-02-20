import struct
import pvporcupine
import threading
import pyaudio
import wave
import os
import time
import numpy as np
import logging
from PyQt6.QtCore import QObject, pyqtSignal
from Jarvis.config import PORCUPINE_ACCESS_KEY
from Jarvis.input.audio_capture import AudioCapture


class Listener(QObject):
    """
    Fully autonomous voice listener.
    Always listening — detects speech via energy threshold (VAD),
    records until silence, transcribes, emits command.
    No wake word or button needed.
    """
    state_changed = pyqtSignal(str)   # "listening", "processing", "waiting"
    command_received = pyqtSignal(str)

    # Voice Activity Detection thresholds
    SPEECH_THRESHOLD = 600    # RMS above this = speech detected
    SILENCE_THRESHOLD = 400   # RMS below this = silence  
    SILENCE_DURATION = 0.8    # Seconds of silence to stop recording
    MIN_SPEECH_DURATION = 0.3 # Minimum speech length to process
    MAX_DURATION = 15.0       # Max recording length

    def __init__(self):
        super().__init__()
        self.listening = False
        self.audio = AudioCapture()
        self.model = None
        self.model_lock = threading.Lock()
        self._is_processing = False  # Prevent listening while speaking

    def start(self):
        self.listening = True
        threading.Thread(target=self._listen_loop, daemon=True).start()
        threading.Thread(target=self._preload_model, daemon=True).start()

    def stop(self):
        self.listening = False

    def set_processing(self, is_processing):
        """Called when TTS is speaking so we don't listen to ourselves."""
        self._is_processing = is_processing

    def _preload_model(self):
        try:
            with self.model_lock:
                if self.model:
                    return
                from faster_whisper import WhisperModel
                self.model = WhisperModel("tiny", device="cpu", compute_type="int8")
                print("Whisper model ready.")
        except Exception as e:
            logging.error(f"Model Preload Error: {e}", exc_info=True)

    def _listen_loop(self):
        try:
            if not self.audio.stream:
                self.audio.start_recording()

            print("Autonomous listener active.")
            self.state_changed.emit("waiting")

            while self.listening:
                try:
                    # Skip listening while TTS is playing
                    if self._is_processing:
                        time.sleep(0.1)
                        continue

                    # Read a chunk and check for speech
                    data = self.audio.read_chunk()
                    if not data:
                        time.sleep(0.05)
                        continue

                    # Voice Activity Detection
                    try:
                        audio_data = np.frombuffer(data, dtype=np.int16)
                        rms = np.sqrt(np.mean(audio_data.astype(np.float32)**2))
                    except Exception:
                        continue

                    if rms > self.SPEECH_THRESHOLD:
                        # Speech detected! Start recording
                        self.state_changed.emit("listening")
                        self._record_command(data)
                        self.state_changed.emit("waiting")

                except Exception as e:
                    if "Input overflow" not in str(e):
                        logging.error(f"Listen loop error: {e}")
                    time.sleep(0.05)

        except Exception as e:
            logging.error(f"Listener CRITICAL: {e}", exc_info=True)

    def _record_command(self, initial_chunk):
        """Record speech until silence is detected, then transcribe."""
        frames = [initial_chunk]
        start_time = time.time()
        silence_start = None
        has_speech = True

        while True:
            data = self.audio.read_chunk()
            if not data:
                break

            frames.append(data)

            elapsed = time.time() - start_time
            if elapsed > self.MAX_DURATION:
                break

            try:
                audio_data = np.frombuffer(data, dtype=np.int16)
                rms = np.sqrt(np.mean(audio_data.astype(np.float32)**2))
            except Exception:
                rms = 0

            if rms < self.SILENCE_THRESHOLD:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start > self.SILENCE_DURATION:
                    break
            else:
                silence_start = None

        # Check minimum duration
        duration = time.time() - start_time
        if duration < self.MIN_SPEECH_DURATION or len(frames) < 5:
            return

        # Transcribe
        self.state_changed.emit("processing")
        self._transcribe(frames)

    def _transcribe(self, frames):
        """Save audio and transcribe with Whisper."""
        filename = os.path.join(os.path.dirname(__file__), "command.wav")
        
        # Calculate recording duration for debugging
        duration = len(frames) * 1024 / 16000
        print(f"Recording: {duration:.1f}s, {len(frames)} chunks")
        
        try:
            wf = wave.open(filename, 'wb')
            wf.setnchannels(1)
            wf.setsampwidth(self.audio.p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(b''.join(frames))
            wf.close()
            print(f"Saved WAV: {os.path.getsize(filename)} bytes")
        except Exception as e:
            print(f"WAV save error: {e}")
            logging.error(f"WAV save error: {e}")
            return

        try:
            with self.model_lock:
                if not self.model:
                    print("Loading Whisper model...")
                    from faster_whisper import WhisperModel
                    self.model = WhisperModel("tiny", device="cpu", compute_type="int8")

            print("Transcribing...")
            segments, info = self.model.transcribe(filename, beam_size=1, language="en")
            segments_list = list(segments)  # Consume the generator
            text = " ".join([s.text for s in segments_list]).strip()
            
            print(f"Raw transcription: '{text}' ({len(segments_list)} segments)")

            # Only filter very short garbage (1-2 chars) 
            if text and len(text) > 2:
                print(f">>> COMMAND: {text}")
                self.command_received.emit(text)
            else:
                print(f"Filtered out short text: '{text}'")

        except Exception as e:
            print(f"STT Error: {e}")
            logging.error(f"STT Error: {e}", exc_info=True)
