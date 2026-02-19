
import struct
import pvporcupine
import threading
import pyaudio
import wave
import os
import time
import numpy as np
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

        if PORCUPINE_ACCESS_KEY:
            try:
                self.porcupine = pvporcupine.create(access_key=PORCUPINE_ACCESS_KEY, keywords=["jarvis"])
                print("Porcupine initialized successfully")
            except Exception as e:
                print(f"Porcupine Init Error: {e}")
        else:
            print("Porcupine Access Key missing. Voice wake word disabled.")

    def start(self):
        # Even if porcupine is missing, we might want to start for manual trigger?
        # But _listen_loop depends on reading chunks.
        # Let's allow start if we have manual trigger capability even without Porcupine
        self.listening = True
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def stop(self):
        self.listening = False

    def start_listening(self):
        """Manually trigger listening phase (skip wake word)"""
        self.manual_trigger.set()

    def _listen_loop(self):
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
                print(f"Listening Error: {e}")
                time.sleep(1)

    def _record_and_transcribe(self):
        print("Recording command...")
        frames = []
        
        # Configuration for Silence Detection
        SILENCE_THRESHOLD = 500  # RMS threshold (adjust based on mic)
        SILENCE_DURATION = 1.5   # Seconds of silence to stop
        MAX_DURATION = 10.0      # Max recording length
        
        start_time = time.time()
        silence_start = None
        
        while True:
            data = self.audio.read_chunk()
            if not data: break
            
            frames.append(data)
            
            # Check for max duration
            if time.time() - start_time > MAX_DURATION:
                print("Max duration reached.")
                break
                
            # Check for silence
            # Convert bytes to numpy array
            audio_data = np.frombuffer(data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_data**2))
            
            if rms < SILENCE_THRESHOLD:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start > SILENCE_DURATION:
                    # Only stop if we have recorded something significant first?
                    # For now just stop.
                    print("Silence detected.")
                    break
            else:
                silence_start = None # Reset silence counter
        
        # Determine if recording was valid (not too short)
        if len(frames) < 10: # < ~0.5s
             print("Recording too short, ignoring.")
             return

        self.state_changed.emit("processing")
        print("Processing command...")
        
        # Save to temp file
        filename = "command.wav"
        wf = wave.open(filename, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(self.audio.p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(16000)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        # Transcribe
        try:
            from faster_whisper import WhisperModel
            # Loading model takes time. Ideally cache this or load in separate thread eagerly.
            # Using 'tiny' for speed.
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            segments, info = model.transcribe(filename, beam_size=5)
            text = " ".join([segment.text for segment in segments]).strip()
            print(f"Transcribed: {text}")
            
            if text:
                self.command_received.emit(text)
            else:
                 print("No text transcribed.")
                
        except ImportError:
            print("faster-whisper not installed or found.")
        except Exception as e:
            print(f"STT Error: {e}")
