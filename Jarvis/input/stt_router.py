"""
STT Router — Multi-Provider Speech-to-Text
=============================================
Routes transcription between:
  - Groq Whisper API  (cloud, ~200ms, most accurate, free tier: 28800s/day)
  - Local faster-whisper  (local, ~300-800ms, CPU/GPU)

Provides:
  - Automatic provider selection and fallback
  - In-memory audio transcription (no WAV files for cloud)
  - Usage tracking to stay within free tier limits
  - Unified interface for the listener pipeline
"""

import io
import json
import time
import wave
import logging
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger("jarvis.stt_router")


class GroqSTT:
    """
    Groq Whisper API — cloud-based STT with ~200ms latency.
    
    Free tier: 28,800 audio seconds/day (~8 hours).
    Uses whisper-large-v3-turbo for high accuracy.
    """

    API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._model = "whisper-large-v3-turbo"
        self._daily_seconds_used = 0.0
        self._daily_limit = 28800.0  # 8 hours
        self._day_start = time.time()
        self._lock = threading.Lock()
        
        # Use httpx for connection pooling
        try:
            import httpx
            self._client = httpx.Client(
                timeout=15.0,
                http2=True,
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
            )
            self._use_httpx = True
        except ImportError:
            import requests
            self._session = requests.Session()
            self._use_httpx = False
        
        logger.info("GroqSTT initialized (model=%s)", self._model)

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        language: Optional[str] = None,
    ) -> dict:
        """
        Transcribe raw PCM audio bytes via Groq Whisper API.
        
        Returns: {"text": str, "time": float, "language": str, "error": str|None}
        """
        t0 = time.time()
        
        # Check daily usage limits
        self._reset_daily_if_needed()
        audio_duration = len(audio_bytes) / (sample_rate * channels * sample_width)
        
        if self._daily_seconds_used + audio_duration > self._daily_limit:
            return {
                "text": "",
                "error": "Daily Groq STT limit reached",
                "time": 0,
                "language": language or "unknown",
            }

        # Convert raw PCM to WAV in-memory (Groq API requires file format)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_bytes)
        wav_buffer.seek(0)

        # Prepare multipart upload
        headers = {"Authorization": f"Bearer {self._api_key}"}
        files = {"file": ("audio.wav", wav_buffer, "audio/wav")}
        data = {
            "model": self._model,
            "response_format": "json",
        }
        if language and language != "auto":
            data["language"] = language

        try:
            if self._use_httpx:
                resp = self._client.post(
                    self.API_URL, headers=headers, files=files, data=data
                )
                resp.raise_for_status()
                result = resp.json()
            else:
                resp = self._session.post(
                    self.API_URL, headers=headers, files=files, data=data, timeout=15
                )
                resp.raise_for_status()
                result = resp.json()

            elapsed = round(time.time() - t0, 3)
            text = result.get("text", "").strip()
            
            # Track usage
            with self._lock:
                self._daily_seconds_used += audio_duration

            logger.info("GroqSTT: '%s' (%.3fs, %.1fs audio)", text[:50], elapsed, audio_duration)
            return {
                "text": text,
                "error": None,
                "time": elapsed,
                "language": language or "auto",
            }

        except Exception as e:
            elapsed = round(time.time() - t0, 3)
            logger.error("GroqSTT error: %s (%.3fs)", e, elapsed)
            return {
                "text": "",
                "error": str(e),
                "time": elapsed,
                "language": language or "auto",
            }

    def _reset_daily_if_needed(self):
        """Reset daily counter after 24 hours."""
        now = time.time()
        if now - self._day_start > 86400:
            with self._lock:
                self._daily_seconds_used = 0.0
                self._day_start = now

    @property
    def remaining_seconds(self) -> float:
        self._reset_daily_if_needed()
        return max(0, self._daily_limit - self._daily_seconds_used)

    def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            headers = {"Authorization": f"Bearer {self._api_key}"}
            if self._use_httpx:
                r = self._client.get("https://api.groq.com/openai/v1/models", headers=headers)
            else:
                r = self._session.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def close(self):
        """Clean up HTTP client."""
        try:
            if self._use_httpx and hasattr(self, '_client'):
                self._client.close()
            elif hasattr(self, '_session'):
                self._session.close()
        except Exception:
            pass


class LocalSTT:
    """
    Local faster-whisper STT — runs on CPU or GPU.
    
    Keeps the model loaded in memory for fast repeated transcriptions.
    Supports in-memory audio (no file I/O needed).
    """

    def __init__(self, model_size: str = "small.en", device: str = "auto", compute_type: str = "auto"):
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None
        self._lock = threading.Lock()
        self._language = None  # None = auto-detect
        
        logger.info("LocalSTT configured (model=%s, device=%s)", model_size, device)

    def load_model(self):
        """Load the faster-whisper model (call once on startup)."""
        try:
            from faster_whisper import WhisperModel
            
            # Auto-detect best device/compute type
            device = self._device
            compute_type = self._compute_type
            
            if device == "auto":
                try:
                    import torch
                    if torch.cuda.is_available():
                        device = "cuda"
                        compute_type = "float16" if compute_type == "auto" else compute_type
                        logger.info("LocalSTT: CUDA available, using GPU")
                    else:
                        device = "cpu"
                        compute_type = "int8" if compute_type == "auto" else compute_type
                except ImportError:
                    device = "cpu"
                    compute_type = "int8" if compute_type == "auto" else compute_type
            elif compute_type == "auto":
                compute_type = "float16" if device == "cuda" else "int8"

            t0 = time.time()
            self._model = WhisperModel(self._model_size, device=device, compute_type=compute_type)
            elapsed = time.time() - t0
            logger.info("LocalSTT model loaded: %s on %s/%s (%.1fs)", 
                       self._model_size, device, compute_type, elapsed)
            print(f"[STT] Local model loaded: {self._model_size} on {device}/{compute_type} ({elapsed:.1f}s)")
            
        except Exception as e:
            logger.error("Failed to load local STT model: %s", e)
            print(f"[STT] Local model load error: {e}")

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        language: Optional[str] = None,
    ) -> dict:
        """
        Transcribe raw PCM audio bytes using local faster-whisper.
        No file I/O — processes numpy array directly.
        """
        if self._model is None:
            self.load_model()
            if self._model is None:
                return {"text": "", "error": "Model not loaded", "time": 0, "language": "unknown"}

        t0 = time.time()
        lang = language if language and language != "auto" else self._language

        try:
            # Convert bytes to numpy float32 array (faster-whisper accepts this)
            audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0

            with self._lock:
                segments, info = self._model.transcribe(
                    audio_float32,
                    beam_size=1,
                    language=lang,
                    initial_prompt="Jarvis open browser terminal script create folder file help status",
                    vad_filter=True,  # Built-in VAD for better accuracy
                )
                text = " ".join(s.text for s in segments).strip()

            elapsed = round(time.time() - t0, 3)
            logger.info("LocalSTT: '%s' (%.3fs)", text[:50], elapsed)
            return {
                "text": text,
                "error": None,
                "time": elapsed,
                "language": info.language if lang is None else lang,
            }

        except Exception as e:
            elapsed = round(time.time() - t0, 3)
            logger.error("LocalSTT error: %s (%.3fs)", e, elapsed)
            return {"text": "", "error": str(e), "time": elapsed, "language": lang or "auto"}

    def set_language(self, lang: str):
        """Set language for transcription. 'auto' for auto-detect."""
        self._language = None if lang == "auto" else lang
        logger.info("LocalSTT language set to: %s", lang)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None


class STTRouter:
    """
    Intelligent STT provider router with automatic fallback.
    
    Routes transcription to the fastest available provider:
      1. Groq Whisper API (primary — ~200ms, most accurate)
      2. Local faster-whisper (fallback — ~300-800ms)
    
    Automatically falls back when:
      - Groq API key not configured
      - Groq daily quota exhausted
      - Network unavailable
      - API returns error
    """

    def __init__(self, groq_api_key: str = "", stt_provider: str = "auto",
                 local_model: str = "small.en", local_device: str = "auto"):
        self._provider = stt_provider  # "auto", "groq", "local"
        self._groq: Optional[GroqSTT] = None
        self._local: Optional[LocalSTT] = None
        self._language = None
        
        # Initialize providers
        if groq_api_key and stt_provider in ("auto", "groq"):
            self._groq = GroqSTT(groq_api_key)
        
        if stt_provider in ("auto", "local"):
            self._local = LocalSTT(model_size=local_model, device=local_device)
        
        # Stats
        self._groq_calls = 0
        self._local_calls = 0
        self._groq_errors = 0
        
        logger.info("STTRouter initialized (provider=%s, groq=%s, local=%s)",
                    stt_provider,
                    "available" if self._groq else "unavailable",
                    "configured" if self._local else "unavailable")

    def preload(self):
        """Pre-load local model in background (call on startup)."""
        if self._local:
            import threading
            threading.Thread(target=self._local.load_model, daemon=True).start()

    def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,
        language: Optional[str] = None,
    ) -> dict:
        """
        Transcribe audio bytes using the best available provider.
        
        Returns: {"text": str, "time": float, "language": str, "error": str|None, "provider": str}
        """
        lang = language or self._language

        # Try Groq first (if available and provider allows)
        if self._groq and self._should_use_groq():
            result = self._groq.transcribe_bytes(audio_bytes, sample_rate, channels, sample_width, lang)
            if result.get("error") is None:
                self._groq_calls += 1
                result["provider"] = "groq"
                return result
            else:
                self._groq_errors += 1
                logger.warning("GroqSTT failed (%s), falling back to local", result["error"])

        # Fallback to local
        if self._local:
            result = self._local.transcribe_bytes(audio_bytes, sample_rate, channels, sample_width, lang)
            self._local_calls += 1
            result["provider"] = "local"
            return result

        return {
            "text": "",
            "error": "No STT provider available",
            "time": 0,
            "language": lang or "auto",
            "provider": "none",
        }

    def _should_use_groq(self) -> bool:
        """Determine if Groq should be used based on provider setting and availability."""
        if self._provider == "local":
            return False
        if self._groq is None:
            return False
        if self._provider == "groq":
            return True
        # Auto mode: use Groq if it has remaining quota
        return self._groq.remaining_seconds > 60  # At least 1 minute remaining

    def set_language(self, lang: str):
        """Set language for all providers."""
        self._language = lang if lang != "auto" else None
        if self._local:
            self._local.set_language(lang)
        logger.info("STTRouter language set to: %s", lang)

    def get_stats(self) -> dict:
        """Return usage statistics."""
        return {
            "provider": self._provider,
            "groq_calls": self._groq_calls,
            "local_calls": self._local_calls,
            "groq_errors": self._groq_errors,
            "groq_remaining_seconds": self._groq.remaining_seconds if self._groq else 0,
        }

    def close(self):
        """Clean up resources."""
        if self._groq:
            self._groq.close()
