import sys
import threading
import pyaudio
import wave
import os
import time
import numpy as np
import logging
from PyQt6.QtCore import QObject, pyqtSignal
from Jarvis.config import PORCUPINE_ACCESS_KEY, VAD_ENGINE, STT_PROVIDER, GROQ_API_KEY, GEMINI_API_KEY, BARGE_IN_ENABLED
# ... (rest of imports)

class Listener(QObject):
    # ... (rest of class until __init__)
    def __init__(self):
        super().__init__()
        self.listening = False
        self.manual_pause = False
        self.model = None
        self.model_lock = threading.Lock()
        self._is_processing = False
        self._is_tts_playing = False   # Track TTS playback state for barge-in
        self._pa = None
        self._stream = None
        
        # Initialize VAD engine
        self._vad = create_vad(VAD_ENGINE)
        
        # Initialize STT Router (replaces subprocess worker)
        self._stt_router = STTRouter(
            groq_api_key=GROQ_API_KEY,
            gemini_api_key=GEMINI_API_KEY,
            stt_provider=STT_PROVIDER,
            local_model="small.en",
            local_device="auto",
        )
        
        # Barge-in state
        self._barge_in_enabled = BARGE_IN_ENABLED
        self._barge_in_speech_start = None
        
        # Audio processor for wave visualization
        self.audio_processor = AudioProcessor(
            sample_rate=self.RATE,
            fft_size=512,
            num_bands=32
        )

    def start(self):
        self.listening = True
        # Pre-load STT model in background (replaces subprocess worker)
        self._stt_router.preload()
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def stop(self):
        self.listening = False
        self._close_stream()
        self._stt_router.close()

    def set_processing(self, is_processing):
        self._is_processing = is_processing
        # Only emit state if not manually paused
        if not self.manual_pause:
             self.state_changed.emit("processing" if is_processing else "waiting")

    def set_tts_playing(self, is_playing: bool):
        """Track TTS playback state for barge-in detection."""
        self._is_tts_playing = is_playing
        if not is_playing:
            self._barge_in_speech_start = None

    def toggle_pause(self):
        """Manual toggle for user pause command."""
        self.manual_pause = not self.manual_pause
        if self.manual_pause:
            self.state_changed.emit("paused")
        else:
            self.state_changed.emit("waiting")
        return self.manual_pause
    
    def get_audio_spectrum(self):
        """
        Get the current audio frequency spectrum (32 normalized bands).
        
        Returns:
            np.ndarray: 32 frequency bins normalized to 0.0-1.0 range
        """
        return self.audio_processor.get_spectrum()
    
    def get_audio_spectrum_from_queue(self, timeout=0.01):
        """
        Get spectrum from queue without blocking.
        
        Args:
            timeout: Timeout in seconds (default: 0.01)
            
        Returns:
            np.ndarray or None: Spectrum data if available
        """
        return self.audio_processor.get_spectrum_from_queue(timeout=timeout)

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

    def _transcribe(self, frames):
        """Transcribe audio frames using STT Router (in-memory, no file I/O)."""
        t_start = time.time()
        
        # Combine all frames into a single byte buffer
        audio_bytes = b''.join(frames)
        
        try:
            pa = pyaudio.PyAudio()
            sample_width = pa.get_sample_size(self.FORMAT)
            pa.terminate()
        except Exception:
            sample_width = 2  # Default for paInt16
        
        audio_duration = len(audio_bytes) / (self.RATE * self.CHANNELS * sample_width)
        print(f"[STT] Transcribing {audio_duration:.1f}s audio ({len(audio_bytes)} bytes)...")

        # Use STT Router instead of subprocess worker
        result = self._stt_router.transcribe(
            audio_bytes=audio_bytes,
            sample_rate=self.RATE,
            channels=self.CHANNELS,
            sample_width=sample_width,
        )

        total = time.time() - t_start
        text = result.get("text", "").strip()
        provider = result.get("provider", "unknown")
        stt_time = result.get("time", 0)
        error = result.get("error")

        if error:
            print(f"[STT] Error ({provider}): {error}")
            return

        print(f"[STT] '{text}' ({provider}, stt={stt_time}s, total={total:.2f}s)")

        if text and len(text) > 2:
            print(f">>> COMMAND: {text}")
            self.command_received.emit(text)
        else:
            print(f"[STT] Filtered: '{text}'")

    def _listen_loop(self):
        try:
            if not self._open_stream():
                print("Cannot open microphone. Text-only mode.")
                return

            print(f"Autonomous listener active (VAD={VAD_ENGINE}, STT={STT_PROVIDER}).")
            self.state_changed.emit("waiting")

            while self.listening:
                try:
                    # Barge-in mode: keep VAD active during TTS playback
                    if self._is_tts_playing and self._barge_in_enabled:
                        self._handle_barge_in_check()
                        continue
                    
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

                    # Voice Activity Detection using configured engine
                    try:
                        # Process audio for visualization (non-blocking)
                        try:
                            self.audio_processor.process_chunk(data)
                        except Exception:
                            pass
                        
                        # Use VAD engine for speech detection
                        is_speech = self._vad.is_speech(data, self.RATE)
                    except Exception:
                        continue

                    if is_speech:
                        self.state_changed.emit("listening")
                        frames = self._record_until_silence(data)
                        if frames:
                            # NOTE: Stream stays open during transcription
                            # (no close/reopen — saves ~50-100ms)
                            self.state_changed.emit("processing")
                            self._transcribe(frames)
                        self.state_changed.emit("waiting")
                        # Reset VAD state after each utterance
                        self._vad.reset()

                except Exception as e:
                    if "Input overflow" not in str(e):
                        print(f"Listen loop error: {e}")
                    time.sleep(0.05)

        except Exception as e:
            print(f"Listener CRITICAL: {e}")
            logging.error(f"Listener CRITICAL: {e}", exc_info=True)

    def _handle_barge_in_check(self):
        """Check for barge-in (user speaking during TTS playback)."""
        try:
            if self._stream is None or not self._stream.is_active():
                if not self._open_stream():
                    time.sleep(0.1)
                    return

            data = self._stream.read(self.CHUNK, exception_on_overflow=False)
            if not data:
                time.sleep(0.05)
                return
            
            # Use VAD with higher threshold during barge-in to avoid self-trigger
            is_speech = self._vad.is_speech(data, self.RATE)
            confidence = self._vad.get_confidence()
            
            # Require higher confidence during barge-in (echo rejection)
            if is_speech and confidence > 0.7:
                if self._barge_in_speech_start is None:
                    self._barge_in_speech_start = time.time()
                elif (time.time() - self._barge_in_speech_start) * 1000 >= self.BARGE_IN_SPEECH_MS:
                    # Sustained speech detected — trigger barge-in
                    print("[BARGE-IN] User interruption detected!")
                    self._barge_in_speech_start = None
                    self.barge_in_detected.emit()
                    # Don't process here — the barge-in handler will stop TTS
                    # and re-enter normal listen mode
                    return
            else:
                self._barge_in_speech_start = None

        except Exception:
            time.sleep(0.05)

                except Exception as e:
                    if "Input overflow" not in str(e):
                        print(f"Listen loop error: {e}")
                    time.sleep(0.05)

        except Exception as e:
            print(f"Listener CRITICAL: {e}")
            logging.error(f"Listener CRITICAL: {e}", exc_info=True)

    def _record_until_silence(self, initial_chunk):
        """Record speech until silence is detected (using VAD engine)."""
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

            # Process audio for visualization (non-blocking)
            try:
                self.audio_processor.process_chunk(data)
            except Exception:
                pass

            if elapsed > self.MAX_DURATION:
                break

            # Use VAD engine for silence detection
            try:
                is_speech = self._vad.is_speech(data, self.RATE)
            except Exception:
                is_speech = False

            if not is_speech:
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
