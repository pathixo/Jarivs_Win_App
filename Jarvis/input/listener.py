
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
    state_changed = pyqtSignal(str) # "listening", "processing", "waiting"
    command_received = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.listening = False
        self.porcupine = None
        self.audio = AudioCapture()
        self.manual_trigger = threading.Event()
        self.model = None # Cache for Whisper model
        self.model_lock = threading.Lock() # Ensure thread safety for model loading

        if PORCUPINE_ACCESS_KEY:
            try:
                self.porcupine = pvporcupine.create(access_key=PORCUPINE_ACCESS_KEY, keywords=["jarvis"])
                print("Porcupine initialized successfully")
            except Exception as e:
                print(f"Porcupine Init Error: {e}")
                logging.error(f"Porcupine Init Error: {e}")
        else:
            print("Porcupine Access Key missing. Voice wake word disabled.")

    def start(self):
        self.listening = True
        threading.Thread(target=self._listen_loop, daemon=True).start()
        
        # Preload model in background to avoid lag on first command
        # Check if model is already loaded to avoid redundant threads
        if not self.model:
            threading.Thread(target=self._preload_model, daemon=True).start()

    def _preload_model(self):
        print("Preloading Whisper model...")
        try:
            with self.model_lock:
                if self.model: return # Double check
                from faster_whisper import WhisperModel
                # Using 'tiny' for speed. CPU int8.
                self.model = WhisperModel("tiny", device="cpu", compute_type="int8")
                print("Whisper model loaded.")
        except Exception as e:
            print(f"Model Preload Error: {e}")
            logging.error(f"Model Preload Error: {e}", exc_info=True)

    def stop(self):
        self.listening = False

    def start_listening(self):
        """Manually trigger listening phase (skip wake word)"""
        self.manual_trigger.set()

    def _listen_loop(self):
        try:
            # Open audio stream
            if not self.audio.stream:
                 self.audio.start_recording()
            
            print("Listener loop started...")
            self.state_changed.emit("waiting")
            
            while self.listening:
                try:
                    # Check for manual trigger
                    if self.manual_trigger.is_set():
                        self.manual_trigger.clear()
                        print("Manual trigger detected!")
                        self.state_changed.emit("listening")
                        self._record_and_transcribe()
                        self.state_changed.emit("waiting")
                        continue

                    pcm = self.audio.read_chunk()
                    if not pcm: continue
                    
                    # Wake Word Detection (only if initialized)
                    if self.porcupine and len(pcm) == self.porcupine.frame_length * 2: 
                       frame = struct.unpack_from("h" * self.porcupine.frame_length, pcm)
                       keyword_index = self.porcupine.process(frame)
                       if keyword_index >= 0:
                           print("Wake word detected!")
                           self.state_changed.emit("listening")
                           self._record_and_transcribe()
                           self.state_changed.emit("waiting")
                           print("Resuming wake word listener...")
                except Exception as e:
                    # Don't spam logs but do capture
                    if "Input overflow" not in str(e):
                        logging.error(f"Listener Loop Inner Error: {e}")
                    time.sleep(0.1)
        except Exception as e:
            logging.error(f"Listener Loop CRITICAL Error: {e}", exc_info=True)
            print(f"Listener Loop Crashed: {e}")

    def _record_and_transcribe(self):
        print("Recording command...")
        frames = []
        
        # Configuration for Silence Detection
        SILENCE_THRESHOLD = 500  # RMS threshold
        SILENCE_DURATION = 1.0   # Reduced for snappier response
        MAX_DURATION = 10.0      # Max recording length
        
        start_time = time.time()
        silence_start = None
        
        try:
            while True:
                data = self.audio.read_chunk()
                if not data: break
                
                frames.append(data)
                
                # Check for max duration
                if time.time() - start_time > MAX_DURATION:
                    print("Max duration reached.")
                    break
                    
                # Check for silence
                try:
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    if len(audio_data) > 0:
                        rms = np.sqrt(np.mean(audio_data**2))
                    else:
                        rms = 0
                except Exception:
                    rms = 0
                
                if rms < SILENCE_THRESHOLD:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > SILENCE_DURATION:
                        print("Silence detected.")
                        break
                else:
                    silence_start = None # Reset
            
            if len(frames) < 10: 
                 print("Recording too short, ignoring.")
                 return

            self.state_changed.emit("processing")
            print("Processing command...")
            
            # Save to temp file
            filename = "command.wav"
            try:
                wf = wave.open(filename, 'wb')
                wf.setnchannels(1)
                wf.setsampwidth(self.audio.p.get_sample_size(pyaudio.paInt16))
                wf.setframerate(16000)
                wf.writeframes(b''.join(frames))
                wf.close()
            except Exception as e:
                print(f"Error saving wav: {e}")
                logging.error(f"Error saving wav: {e}")
                return
            
            # Transcribe
            try:
                with self.model_lock:
                    if not self.model:
                        print("Model not loaded yet, loading now...")
                        from faster_whisper import WhisperModel
                        self.model = WhisperModel("tiny", device="cpu", compute_type="int8")
                
                print("Transcribing...")
                # Run blocking transcribe
                # Note: This is still running in the listener thread context locally called by _listen_loop
                # If this crashes, it kills the thread.
                segments, info = self.model.transcribe(filename, beam_size=5)
                text = " ".join([segment.text for segment in segments]).strip()
                print(f"Transcribed: {text}")
                
                if text:
                    self.command_received.emit(text)
                else:
                     print("No text transcribed.")
                    
            except ImportError:
                print("faster-whisper not installed or found.")
                logging.error("faster-whisper not installed")
            except Exception as e:
                print(f"STT Error: {e}")
                logging.error(f"STT Error: {e}", exc_info=True)
                
        except Exception as e:
             logging.error(f"Record/Transcribe Error: {e}", exc_info=True)
