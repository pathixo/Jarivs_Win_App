import threading
import pyaudio
import wave
import os
import time
import numpy as np
import logging
from PyQt6.QtCore import QObject, pyqtSignal
from Jarvis.config import PORCUPINE_ACCESS_KEY


class Listener(QObject):
    """
    Fully autonomous voice listener with VAD.
    Always listening — detects speech via energy threshold,
    records until silence, transcribes, emits command.
    """
    state_changed = pyqtSignal(str)
    command_received = pyqtSignal(str)

    SPEECH_THRESHOLD = 500
    SILENCE_THRESHOLD = 300
    SILENCE_DURATION = 0.6
    MIN_SPEECH_DURATION = 0.3
    MAX_DURATION = 15.0

    RATE = 16000
    CHANNELS = 1
    CHUNK = 1024
    FORMAT = pyaudio.paInt16

    def __init__(self):
        super().__init__()
        self.listening = False
        self.manual_pause = False
        self.model = None
        self.model_lock = threading.Lock()
        self._is_processing = False
        self._pa = None
        self._stream = None

    def start(self):
        self.listening = True
        threading.Thread(target=self._preload_model, daemon=True).start()
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def stop(self):
        self.listening = False
        self._close_stream()

    def set_processing(self, is_processing):
        self._is_processing = is_processing
        # Only emit state if not manually paused
        if not self.manual_pause:
             self.state_changed.emit("processing" if is_processing else "waiting")

    def toggle_pause(self):
        """Manual toggle for user pause command."""
        self.manual_pause = not self.manual_pause
        if self.manual_pause:
            self.state_changed.emit("paused")
        else:
            self.state_changed.emit("waiting")
        return self.manual_pause

    def _open_stream(self):
        """Open the microphone stream."""
        try:
            if self._pa is None:
                self._pa = pyaudio.PyAudio()
            if self._stream is None or not self._stream.is_active():
                self._stream = self._pa.open(
                    format=self.FORMAT,
                    channels=self.CHANNELS,
                    rate=self.RATE,
                    input=True,
                    frames_per_buffer=self.CHUNK
                )
            return True
        except Exception as e:
            print(f"Mic open error: {e}")
            return False

    def _close_stream(self):
        """Close the microphone stream safely."""
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
                self._stream = None
        except Exception:
            self._stream = None

    def _preload_model(self):
        try:
            with self.model_lock:
                if self.model:
                    return
                print("Loading Whisper model...")
                from faster_whisper import WhisperModel
                self.model = WhisperModel("tiny", device="cpu", compute_type="int8")
                print("Whisper model ready.")
        except Exception as e:
            print(f"Model load error: {e}")
            logging.error(f"Model Preload Error: {e}", exc_info=True)

    def _listen_loop(self):
        try:
            if not self._open_stream():
                print("Cannot open microphone. Text-only mode.")
                return

            print("Autonomous listener active.")
            self.state_changed.emit("waiting")

            while self.listening:
                try:
                    if self._is_processing or self.manual_pause:
                        time.sleep(0.1)
                        continue

                    if self._stream is None or not self._stream.is_active():
                        if not self._open_stream():
                            time.sleep(1)
                            continue

                    try:
                        data = self._stream.read(self.CHUNK, exception_on_overflow=False)
                    except Exception:
                        time.sleep(0.05)
                        continue

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
                        self.state_changed.emit("listening")
                        frames = self._record_until_silence(data)
                        if frames:
                            # CLOSE stream before transcribing to avoid native code conflict
                            self._close_stream()
                            self.state_changed.emit("processing")
                            self._transcribe(frames)
                            # Reopen stream after transcription
                            self._open_stream()
                        self.state_changed.emit("waiting")

                except Exception as e:
                    if "Input overflow" not in str(e):
                        print(f"Listen loop error: {e}")
                    time.sleep(0.05)

        except Exception as e:
            print(f"Listener CRITICAL: {e}")
            logging.error(f"Listener CRITICAL: {e}", exc_info=True)

    def _record_until_silence(self, initial_chunk):
        """Record speech until silence is detected."""
        frames = [initial_chunk]
        start_time = time.time()
        silence_start = None

        while True:
            try:
                data = self._stream.read(self.CHUNK, exception_on_overflow=False)
            except Exception:
                break

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

        duration = time.time() - start_time
        print(f"Recorded: {duration:.1f}s, {len(frames)} chunks")

        if duration < self.MIN_SPEECH_DURATION or len(frames) < 5:
            print("Too short, skipping.")
            return None

        return frames

    def _transcribe(self, frames):
        """Save audio to WAV and transcribe with Whisper."""
        filename = os.path.join(os.path.dirname(__file__), "command.wav")

        try:
            pa = pyaudio.PyAudio()
            sample_width = pa.get_sample_size(self.FORMAT)
            pa.terminate()

            wf = wave.open(filename, 'wb')
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(sample_width)
            wf.setframerate(self.RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
            print(f"Saved WAV: {os.path.getsize(filename)} bytes")
        except Exception as e:
            print(f"WAV save error: {e}")
            return

        try:
            with self.model_lock:
                if not self.model:
                    print("Loading Whisper model on demand...")
                    from faster_whisper import WhisperModel
                    self.model = WhisperModel("tiny", device="cpu", compute_type="int8")

            print("Transcribing...")
            segments, info = self.model.transcribe(filename, beam_size=1, language="en")
            segments_list = list(segments)
            text = " ".join([s.text for s in segments_list]).strip()

            print(f"Transcribed: '{text}' ({len(segments_list)} segments)")

            if text and len(text) > 2:
                print(f">>> COMMAND: {text}")
                self.command_received.emit(text)
            else:
                print(f"Filtered: '{text}'")

        except Exception as e:
            print(f"STT Error: {e}")
            logging.error(f"STT Error: {e}", exc_info=True)
