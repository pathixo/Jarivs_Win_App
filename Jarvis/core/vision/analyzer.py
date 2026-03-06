"""
Vision Analyzer — AI-powered screen understanding via Gemini Vision API.
=========================================================================
Uses Google's multimodal Gemini models to analyze screenshots and answer
questions about what's on screen.

VRAM impact: ~0 (API-based, no local models).
"""

import base64
import logging
import time
from dataclasses import dataclass
from typing import Optional

from Jarvis.config import GEMINI_API_KEY

logger = logging.getLogger("jarvis.vision.analyzer")


@dataclass
class AnalysisResult:
    """Result of a vision analysis."""
    description: str
    raw_response: str = ""
    elapsed_ms: float = 0.0
    model: str = ""
    error: Optional[str] = None


class VisionAnalyzer:
    """
    Screen understanding powered by Gemini multimodal API.

    Given a screenshot (PNG bytes), sends it to the Gemini Vision API
    with a user query and returns a natural-language description.
    """

    DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(self, api_key: str = "", model: str = ""):
        self._api_key = api_key or GEMINI_API_KEY
        self._model = model or self.DEFAULT_MODEL

    def analyze(
        self,
        image_bytes: bytes,
        query: str = "Describe what you see on this screen.",
        max_tokens: int = 1024,
    ) -> AnalysisResult:
        """
        Analyze a screenshot using Gemini Vision.

        Args:
            image_bytes: PNG/JPEG image data
            query: Natural-language question about the image
            max_tokens: Max response length

        Returns:
            AnalysisResult with the model's description
        """
        if not self._api_key:
            return AnalysisResult(
                description="",
                error="GEMINI_API_KEY not configured. Set it in .env.",
            )

        t0 = time.perf_counter()

        try:
            import google.generativeai as genai

            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel(self._model)

            # Build the multimodal prompt
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(image_bytes))

            response = model.generate_content(
                [query, img],
                generation_config=genai.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.3,
                ),
            )

            description = response.text.strip() if response.text else ""
            elapsed = (time.perf_counter() - t0) * 1000

            return AnalysisResult(
                description=description,
                raw_response=description,
                elapsed_ms=elapsed,
                model=self._model,
            )

        except ImportError:
            return AnalysisResult(
                description="",
                error="google-generativeai not installed. Run: pip install google-generativeai",
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.error("Vision analysis failed: %s", e)
            return AnalysisResult(
                description="",
                elapsed_ms=elapsed,
                model=self._model,
                error=str(e),
            )

    @property
    def available(self) -> bool:
        return bool(self._api_key)


# ── Module singleton ────────────────────────────────────────────────────

_analyzer: Optional[VisionAnalyzer] = None


def get_vision_analyzer() -> VisionAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = VisionAnalyzer()
    return _analyzer
