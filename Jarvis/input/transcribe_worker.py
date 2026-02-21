"""Standalone transcription worker — runs in a subprocess to avoid ctranslate2/PyQt6 conflicts."""
import sys
import json

def transcribe(wav_path):
    from faster_whisper import WhisperModel
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, info = model.transcribe(wav_path, beam_size=1, language="en")
    segments_list = list(segments)
    text = " ".join([s.text for s in segments_list]).strip()
    return text

if __name__ == "__main__":
    wav_path = sys.argv[1]
    try:
        text = transcribe(wav_path)
        print(json.dumps({"text": text, "error": None}))
    except Exception as e:
        print(json.dumps({"text": "", "error": str(e)}))
