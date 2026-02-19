
import struct
import pvporcupine
import threading
import pyaudio
from Jarvis.config import PORCUPINE_ACCESS_KEY
from Jarvis.input.audio_capture import AudioCapture
# from faster_whisper import WhisperModel # Uncomment when ready

class Listener:
    def __init__(self, on_wake_word=None, on_command=None):
        self.on_wake_word = on_wake_word
        self.on_command = on_command
        self.listening = False
        self.porcupine = None
        self.audio = AudioCapture()

        if PORCUPINE_ACCESS_KEY:
            try:
                self.porcupine = pvporcupine.create(access_key=PORCUPINE_ACCESS_KEY, keywords=["jarvis"])
                print("Porcupine initialized successfully")
            except Exception as e:
                print(f"Porcupine Init Error: {e}")
        else:
            print("Porcupine Access Key missing. Voice disabled.")

    def start(self):
        if not self.porcupine: return
        self.listening = True
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def listen_for_command(self):
        """
        Records audio after wake word and transcribes it relative to faster-whisper.
        For now, we simulate or use a simple recording if whisper is not fully set up.
        """
        print("Listening for command...")
        # 1. Record audio for fixed duration or silence detection
        # Simple fixed duration for MVP
        self.audio.stop_recording() # Stop continuous stream
        self.audio.start_recording() # Restart freshly? or just read
        
        # Actually we need a separate recording logic for command
        # For MVP let's record 5 seconds
        frames = []
        for _ in range(0, int(16000 / 1024 * 5)):
            data = self.audio.read_chunk()
            if data: frames.append(data)
        
        print("Processing command...")
        # Save to temp file
        import wave
        filename = "command.wav"
        wf = wave.open(filename, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(self.audio.p.get_sample_size(pyaudio.paInt16)) # 16-bit
        wf.setframerate(16000)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        # Transcribe
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            segments, info = model.transcribe(filename, beam_size=5)
            text = " ".join([segment.text for segment in segments])
            print(f"Transcribed: {text}")
            
            if self.on_command:
                self.on_command(text)
        except ImportError:
            print("faster-whisper not installed or found.")
        except Exception as e:
            print(f"STT Error: {e}")
            
        # Resume wake word listening?
        # Ideally we should go back to listen loop, but current logic is linear in loop
        pass

    def _listen_loop(self):
        # This loop needs to be carefully managed to avoid blocking UI
        if not self.audio.stream:
             self.audio.start_recording() 
        
        print("Listening for wake word...")
        while self.listening:
            try:
                pcm = self.audio.read_chunk()
                if pcm and len(pcm) == self.porcupine.frame_length * 2: 
                   frame = struct.unpack_from("h" * self.porcupine.frame_length, pcm)
                   keyword_index = self.porcupine.process(frame)
                   if keyword_index >= 0:
                       print("Wake word detected!")
                       if self.on_wake_word:
                           self.on_wake_word()
                       
                       # Trigger STT
                       self.listen_for_command()
                       
                       # Resume listening for wake word
                       print("Resuming wake word listener...")
            except Exception as e:
                print(f"Listening Error: {e}")
                break

    def stop(self):
        self.listening = False
        if self.porcupine:
            self.porcupine.delete()
        self.audio.close()
