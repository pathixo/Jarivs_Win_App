"""
Voice Activity Detection (VAD) Engines
========================================
Provides two VAD implementations:
  - SileroVAD  — Neural network VAD (accurate, <1ms per chunk)
  - EnergyVAD  — RMS energy threshold (legacy, fast)

Both expose a unified interface:
  - is_speech(audio_chunk: bytes) -> bool
  - reset()
"""

import logging
import numpy as np
from abc import ABC, abstractmethod

logger = logging.getLogger("jarvis.vad")


class BaseVAD(ABC):
    """Abstract base class for VAD engines."""

    @abstractmethod
    def is_speech(self, audio_chunk: bytes, sample_rate: int = 16000) -> bool:
        """Return True if the audio chunk contains speech."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state."""
        ...

    @abstractmethod
    def get_confidence(self) -> float:
        """Return the confidence of the last detection (0.0 - 1.0)."""
        ...


class SileroVAD(BaseVAD):
    """
    Neural Voice Activity Detection using Silero VAD.
    
    Uses a small ONNX model (~1.5MB) that runs on CPU in <1ms per chunk.
    Dramatically more accurate than energy-based detection, especially
    for distinguishing speech from background noise, keyboard clicks, etc.
    """

    def __init__(self, threshold: float = 0.5, min_speech_ms: int = 64):
        self._threshold = threshold
        self._min_speech_ms = min_speech_ms
        self._confidence = 0.0
        self._model = None
        self._load_model()

    def _load_model(self):
        """Load the Silero VAD model."""
        try:
            from silero_vad import load_silero_vad
            self._model = load_silero_vad(onnx=True)
            logger.info("Silero VAD loaded (ONNX, threshold=%.2f)", self._threshold)
        except Exception as e:
            logger.error("Failed to load Silero VAD: %s. Falling back to energy-based.", e)
            self._model = None

    def is_speech(self, audio_chunk: bytes, sample_rate: int = 16000) -> bool:
        """Detect speech using Silero VAD neural network."""
        if self._model is None:
            # Fallback to energy-based if model failed to load
            return self._energy_fallback(audio_chunk)

        try:
            import torch
            # Convert bytes to float32 tensor
            audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            tensor = torch.from_numpy(audio_float32)
            
            # Silero VAD expects specific chunk sizes: 512 for 16kHz
            # If our chunk is larger, process in sub-chunks and take max confidence
            chunk_size = 512  # 32ms at 16kHz
            if len(tensor) >= chunk_size:
                max_conf = 0.0
                for i in range(0, len(tensor) - chunk_size + 1, chunk_size):
                    sub_chunk = tensor[i:i + chunk_size]
                    conf = self._model(sub_chunk, sample_rate).item()
                    max_conf = max(max_conf, conf)
                self._confidence = max_conf
            else:
                # Pad short chunks
                padded = torch.zeros(chunk_size)
                padded[:len(tensor)] = tensor
                self._confidence = self._model(padded, sample_rate).item()

            return self._confidence >= self._threshold

        except Exception as e:
            logger.debug("Silero VAD error: %s, using energy fallback", e)
            return self._energy_fallback(audio_chunk)

    def _energy_fallback(self, audio_chunk: bytes) -> bool:
        """Simple energy-based fallback if Silero fails."""
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
        rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
        self._confidence = min(rms / 1000.0, 1.0)
        return rms > 450

    def reset(self) -> None:
        """Reset Silero VAD internal state."""
        if self._model is not None:
            try:
                self._model.reset_states()
            except Exception:
                pass
        self._confidence = 0.0

    def get_confidence(self) -> float:
        return self._confidence

    @property
    def is_available(self) -> bool:
        return self._model is not None


class EnergyVAD(BaseVAD):
    """
    Legacy RMS energy-based Voice Activity Detection.
    
    Simple but noisy — triggers on keyboard clicks, fan noise, etc.
    Kept for compatibility and as a fallback.
    """

    def __init__(self, speech_threshold: int = 450, silence_threshold: int = 300):
        self._speech_threshold = speech_threshold
        self._silence_threshold = silence_threshold
        self._confidence = 0.0

    def is_speech(self, audio_chunk: bytes, sample_rate: int = 16000) -> bool:
        """Detect speech using RMS energy threshold."""
        try:
            audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
            self._confidence = min(rms / 1000.0, 1.0)
            return rms > self._speech_threshold
        except Exception:
            self._confidence = 0.0
            return False

    def is_silence(self, audio_chunk: bytes, sample_rate: int = 16000) -> bool:
        """Return True if the audio chunk is silence."""
        try:
            audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
            return rms < self._silence_threshold
        except Exception:
            return True

    def reset(self) -> None:
        self._confidence = 0.0

    def get_confidence(self) -> float:
        return self._confidence


def create_vad(engine: str = "silero", **kwargs) -> BaseVAD:
    """
    Factory function to create the appropriate VAD engine.
    
    Args:
        engine: "silero" or "energy"
        **kwargs: Passed to the VAD constructor
    
    Returns:
        BaseVAD instance
    """
    if engine == "silero":
        vad = SileroVAD(**kwargs)
        if vad.is_available:
            return vad
        logger.warning("Silero VAD not available, falling back to energy-based")
        return EnergyVAD()
    elif engine == "energy":
        return EnergyVAD(**kwargs)
    else:
        logger.warning("Unknown VAD engine '%s', using energy-based", engine)
        return EnergyVAD()
