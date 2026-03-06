"""
Vision Router — Orchestrates capture → OCR/Analysis pipeline.
===============================================================
High-level API that combines screen capture, OCR, and AI analysis
into a single unified interface.
"""

import logging
from typing import Optional

from Jarvis.core.vision.capture import get_screen_capture, CaptureResult
from Jarvis.core.vision.ocr import get_ocr_engine, OCRResult
from Jarvis.core.vision.analyzer import get_vision_analyzer, AnalysisResult

logger = logging.getLogger("jarvis.vision.router")


class VisionRouter:
    """
    Unified vision pipeline.

    Supports three modes:
      1. capture_and_ocr()     → Screenshot → OCR → text extraction
      2. capture_and_analyze() → Screenshot → Gemini Vision → description
      3. full_pipeline()       → Screenshot → OCR + Vision → rich result
    """

    def __init__(self):
        self._capture = get_screen_capture()
        self._ocr = get_ocr_engine()
        self._analyzer = get_vision_analyzer()

    def capture_and_ocr(self, monitor: int = 1) -> dict:
        """
        Capture screen and extract text via OCR.

        Returns:
            dict with keys: ocr_text, ocr_blocks, ocr_engine,
                            capture_ms, ocr_ms, total_ms
        """
        cap = self._capture.capture_full(monitor)
        pil_img = self._capture.capture_as_pil(monitor)
        ocr = self._ocr.extract(pil_img)

        return {
            "ocr_text": ocr.text,
            "ocr_blocks": ocr.blocks,
            "ocr_engine": ocr.engine,
            "ocr_confidence": ocr.confidence,
            "capture_ms": cap.capture_ms,
            "ocr_ms": ocr.elapsed_ms,
            "total_ms": cap.capture_ms + ocr.elapsed_ms,
        }

    def capture_and_analyze(
        self,
        query: str = "Describe what you see on this screen.",
        monitor: int = 1,
    ) -> dict:
        """
        Capture screen and analyze with Gemini Vision API.

        Returns:
            dict with keys: description, model, capture_ms, analysis_ms, total_ms
        """
        cap = self._capture.capture_full(monitor)
        analysis = self._analyzer.analyze(cap.image_bytes, query)

        return {
            "description": analysis.description,
            "model": analysis.model,
            "error": analysis.error,
            "capture_ms": cap.capture_ms,
            "analysis_ms": analysis.elapsed_ms,
            "total_ms": cap.capture_ms + analysis.elapsed_ms,
        }

    def full_pipeline(
        self,
        query: str = "What's on the screen?",
        monitor: int = 1,
        include_ocr: bool = True,
        include_analysis: bool = True,
    ) -> dict:
        """
        Run the full vision pipeline: capture → OCR + AI Analysis.

        Returns combined results from all stages.
        """
        cap = self._capture.capture_full(monitor)
        result = {
            "capture_ms": cap.capture_ms,
            "width": cap.width,
            "height": cap.height,
        }

        if include_ocr and self._ocr.available:
            pil_img = self._capture.capture_as_pil(monitor)
            ocr = self._ocr.extract(pil_img)
            result.update({
                "ocr_text": ocr.text,
                "ocr_blocks": ocr.blocks,
                "ocr_confidence": ocr.confidence,
                "ocr_engine": ocr.engine,
                "ocr_ms": ocr.elapsed_ms,
            })

        if include_analysis and self._analyzer.available:
            analysis = self._analyzer.analyze(cap.image_bytes, query)
            result.update({
                "description": analysis.description,
                "analysis_model": analysis.model,
                "analysis_error": analysis.error,
                "analysis_ms": analysis.elapsed_ms,
            })

        return result

    def benchmark_capture(self, frames: int = 20) -> dict:
        """Run a capture speed benchmark."""
        return self._capture.benchmark(frames)


# ── Module singleton ────────────────────────────────────────────────────

_router: Optional[VisionRouter] = None


def get_vision_router() -> VisionRouter:
    global _router
    if _router is None:
        _router = VisionRouter()
    return _router
