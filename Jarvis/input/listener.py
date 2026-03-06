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
from Jarvis.input.vad import create_vad
from Jarvis.input.stt_router import STTRouter
from Jarvis.input.audio_processor import AudioProcessor
from Jarvis.core.language_detector import LanguageDetector
from Jarvis.core.telemetry import get_telemetry, AgentPhase, TelemetryType

# Porcupine wake word detection (optional - graceful fallback if not available)
try:
    import pvporcupine
    PORCUPINE_AVAILABLE = True
except ImportError:
    pvporcupine = None
    PORCUPINE_AVAILABLE = False

telemetry = get_telemetry()
    

class Listener(QObject):
    """Autonomous voice listener with wake word, VAD, STT routing, and barge-in support."""

    # ── Qt Signals ───────────────────────────────────────────────────────────
    command_received  = pyqtSignal(str)   # Emitted with transcribed text
    state_changed     = pyqtSignal(str)   # "listening" | "processing" | "waiting" | "paused" | "hotword"
    barge_in_detected = pyqtSignal()      # User spoke during TTS playback
    wake_word_detected = pyqtSignal()     # Wake word "Jarvis" detected

    # ── Audio Constants ──────────────────────────────────────────────────────
    FORMAT             = pyaudio.paInt16
    CHANNELS           = 1
    RATE               = 16000           # 16 kHz — standard for Whisper
    CHUNK              = 512             # 32ms at 16 kHz (Silero VAD optimal)
    MAX_DURATION       = 30.0            # Max recording length (seconds)
    MIN_SPEECH_DURATION = 0.3            # Ignore clips shorter than this
    SILENCE_DURATION   = 0.8            # Silence before ending recording
    BARGE_IN_SPEECH_MS = 300            # ms of sustained speech to trigger barge-in
    HOTWORD_TIMEOUT    = 5.0            # Seconds to wait for speech after wake word

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
        
        # Language detection and context tracking
        self._language_detector = LanguageDetector()
        self._last_detected_language = None  # Remember last detected language for STT
        
        # Initialize VAD engine
        self._vad = create_vad(VAD_ENGINE)
        
        # Initialize Porcupine wake word engine (optional)
        self._porcupine = None
        self._hotword_enabled = False
        self._init_porcupine()
        
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
    
    def _init_porcupine(self):
        """Initialize Porcupine wake word detection if API key is available."""
        if not PORCUPINE_AVAILABLE:
            print("[Hotword] Porcupine not installed. Using VAD-only mode.")
            return
            
        if not PORCUPINE_ACCESS_KEY:
            print("[Hotword] PORCUPINE_ACCESS_KEY not set. Using VAD-only mode.")
            return
        
        try:
            # Use built-in "jarvis" wake word
            self._porcupine = pvporcupine.create(
                access_key=PORCUPINE_ACCESS_KEY,
                keywords=["jarvis"],
                sensitivities=[0.5]  # 0.0-1.0, higher = more sensitive
            )
            self._hotword_enabled = True
            # Porcupine requires specific frame length
            self._porcupine_frame_length = self._porcupine.frame_length
            print(f"[Hotword] Porcupine initialized. Wake word: 'Jarvis' (frame_length={self._porcupine_frame_length})")
        except Exception as e:
            print(f"[Hotword] Porcupine init failed: {e}. Using VAD-only mode.")
            self._porcupine = None
            self._hotword_enabled = False

    def start(self):
        self.listening = True
        # Pre-load STT model in background (replaces subprocess worker)
        self._stt_router.preload()
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def stop(self):
        self.listening = False
        self._close_stream()
        self._stt_router.close()
        # Clean up Porcupine
        if self._porcupine is not None:
            try:
                self._porcupine.delete()
            except Exception:
                pass
            self._porcupine = None
    
    def is_hotword_enabled(self) -> bool:
        """Check if hotword detection is active."""
        return self._hotword_enabled and self._porcupine is not None

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
        telemetry.emit(AgentPhase.TRANSCRIBING, "Starting speech-to-text conversion...", provider=STT_PROVIDER)
        
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
        
        # Try to detect language from context (use last detected language as hint)
        # This helps with consecutive Hindi/English utterances
        stt_language = self._last_detected_language or None
        
        # Use STT Router with language hint
        result = self._stt_router.transcribe(
            audio_bytes=audio_bytes,
            sample_rate=self.RATE,
            channels=self.CHANNELS,
            sample_width=sample_width,
            language=stt_language,  # Pass detected language hint
        )

        total = time.time() - t_start
        text = result.get("text", "").strip()
        provider = result.get("provider", "unknown")
        stt_time = result.get("time", 0)
        error = result.get("error")
        detected_lang = result.get("language", "auto")

        if error:
            telemetry.emit(AgentPhase.ERROR, f"Transcription failed: {error}", type=TelemetryType.ERROR, provider=provider)
            print(f"[STT] Error ({provider}): {error}")
            return

        # Remember the detected language for next transcription
        if detected_lang and detected_lang != "auto":
            self._last_detected_language = detected_lang

        telemetry.emit(AgentPhase.TRANSCRIBING, f"Transcribed: \"{text}\"", type=TelemetryType.SUCCESS, provider=provider)
        print(f"[STT] '{text}' ({provider}, stt={stt_time}s, total={total:.2f}s, lang={detected_lang})")

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

            mode_info = f"VAD={VAD_ENGINE}, STT={STT_PROVIDER}"
            if self._hotword_enabled:
                mode_info = f"Hotword=Jarvis, {mode_info}"
                print(f"Autonomous listener active ({mode_info}). Say 'Jarvis' to activate.")
                self.state_changed.emit("hotword")
            else:
                print(f"Autonomous listener active ({mode_info}). Always listening.")
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

                    # ── Hotword Detection Mode ──────────────────────────────
                    if self._hotword_enabled:
                        if self._wait_for_hotword():
                            # Wake word detected! Now record the command
                            self.wake_word_detected.emit()
                            self.state_changed.emit("listening")
                            frames = self._record_after_hotword()
                            if frames:
                                self.state_changed.emit("processing")
                                self._transcribe(frames)
                            # Go back to hotword waiting mode
                            self.state_changed.emit("hotword")
                            self._vad.reset()
                        continue

                    # ── VAD-only Mode (no hotword) ──────────────────────────
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
                        telemetry.emit(AgentPhase.LISTENING, "Speech detected, capturing audio...")
                        self.state_changed.emit("listening")
                        frames = self._record_until_silence(data)
                        if frames:
                            # NOTE: Stream stays open during transcription
                            # (no close/reopen — saves ~50-100ms)
                            self.state_changed.emit("processing")
                            self._transcribe(frames)
                        self.state_changed.emit("waiting")
                        telemetry.emit(AgentPhase.IDLE, "Pipeline reset to IDLE.")
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

        except Exception as e:
            print(f"Listener CRITICAL: {e}")
            logging.error(f"Listener CRITICAL: {e}", exc_info=True)

    def _wait_for_hotword(self) -> bool:
        """
        Wait for Porcupine to detect the wake word "Jarvis".
        
        Returns:
            True if wake word detected, False if listener stopped or error
        """
        if self._porcupine is None:
            return False
        
        try:
            # Porcupine needs exactly frame_length samples (512 for 16kHz)
            frame_length = self._porcupine.frame_length
            
            # Read audio frame (Porcupine expects int16 samples)
            data = self._stream.read(frame_length, exception_on_overflow=False)
            if not data:
                return False
            
            # Convert bytes to int16 array
            pcm = np.frombuffer(data, dtype=np.int16)
            
            # Process with Porcupine
            keyword_index = self._porcupine.process(pcm)
            
            if keyword_index >= 0:
                print(f"[Hotword] Wake word 'Jarvis' detected!")
                return True
            
            return False
            
        except Exception as e:
            if "Input overflow" not in str(e):
                logging.debug(f"Hotword detection error: {e}")
            return False

    def _record_after_hotword(self):
        """
        Record speech after wake word detection.
        Uses VAD to detect when user starts speaking and when they stop.
        
        Returns:
            List of audio frames or None if timeout/no speech
        """
        frames = []
        speech_started = False
        speech_start_time = None
        silence_start = None
        timeout_start = time.time()
        
        print("[Hotword] Listening for command...")
        
        while True:
            # Check for timeout (no speech after wake word)
            if not speech_started and (time.time() - timeout_start) > self.HOTWORD_TIMEOUT:
                print("[Hotword] Timeout - no speech detected after wake word")
                return None
            
            try:
                data = self._stream.read(self.CHUNK, exception_on_overflow=False)
            except Exception:
                break
            
            if not data:
                continue
            
            # Process audio for visualization
            try:
                self.audio_processor.process_chunk(data)
            except Exception:
                pass
            
            # Use VAD to detect speech
            try:
                is_speech = self._vad.is_speech(data, self.RATE)
            except Exception:
                is_speech = False
            
            if is_speech:
                if not speech_started:
                    speech_started = True
                    speech_start_time = time.time()
                    print("[Hotword] Speech detected, recording...")
                
                frames.append(data)
                silence_start = None
                
                # Max duration check
                if len(frames) * self.CHUNK / self.RATE > self.MAX_DURATION:
                    break
            else:
                if speech_started:
                    frames.append(data)  # Include trailing silence
                    
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > self.SILENCE_DURATION:
                        # Enough silence, stop recording
                        break
        
        if not frames or not speech_started:
            return None
        
        duration = len(frames) * self.CHUNK / self.RATE
        print(f"[Hotword] Recorded: {duration:.1f}s, {len(frames)} chunks")
        
        if duration < self.MIN_SPEECH_DURATION:
            print("[Hotword] Too short, skipping.")
            return None
        
        return frames

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
