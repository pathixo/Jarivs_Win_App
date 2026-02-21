"""Persistent transcription worker — stays alive, model loaded in memory.
Reads WAV file paths from stdin, writes JSON results to stdout."""
import sys
import json
import time

def main():
    # Load model ONCE at startup
    t0 = time.time()
    from faster_whisper import WhisperModel
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    print(json.dumps({"status": "ready", "load_time": round(time.time() - t0, 2)}), flush=True)

    # Process loop — read WAV paths from stdin
    for line in sys.stdin:
        wav_path = line.strip()
        if not wav_path:
            continue
        if wav_path == "EXIT":
            break

        try:
            t1 = time.time()
            segments, info = model.transcribe(wav_path, beam_size=1, language="en")
            segments_list = list(segments)
            text = " ".join([s.text for s in segments_list]).strip()
            elapsed = round(time.time() - t1, 2)
            print(json.dumps({"text": text, "error": None, "time": elapsed}), flush=True)
        except Exception as e:
            print(json.dumps({"text": "", "error": str(e), "time": 0}), flush=True)

if __name__ == "__main__":
    main()
