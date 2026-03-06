"""
OCR Module — Optical character recognition from screen captures.
=================================================================
Supports two backends:
  - EasyOCR (GPU-accelerated, ~500MB VRAM, higher accuracy)
  - pytesseract (CPU-only, no VRAM, fast for simple text)

Automatically selects the best available backend.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("jarvis.vision.ocr")

# ── Backend availability checks ─────────────────────────────────────────

EASYOCR_AVAILABLE = False
TESSERACT_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    pass

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    pass


@dataclass
class OCRResult:
    """Result of an OCR operation."""
    text: str                       # Full extracted text
    blocks: list[dict] = field(default_factory=list)  # Individual text blocks with bbox
    engine: str = ""                # Which engine was used
    elapsed_ms: float = 0.0
    confidence: float = 0.0         # Average confidence (0-1)


class OCREngine:
    """
    Unified OCR interface supporting EasyOCR and pytesseract.

    Prefers EasyOCR for GPU acceleration and higher accuracy.
    Falls back to pytesseract if EasyOCR is unavailable.
    """

    def __init__(self, languages: list[str] = None, prefer_gpu: bool = True):
        self._languages = languages or ["en"]
        self._prefer_gpu = prefer_gpu
        self._easyocr_reader = None
        self._engine_name = "none"

        # Initialize best available engine
        if EASYOCR_AVAILABLE and prefer_gpu:
            self._engine_name = "easyocr"
        elif TESSERACT_AVAILABLE:
            self._engine_name = "tesseract"
        else:
            logger.warning("No OCR engine available. Install easyocr or pytesseract.")

    def _get_easyocr(self):
        """Lazy-load EasyOCR reader (takes a few seconds on first call)."""
        if self._easyocr_reader is None:
            logger.info("Loading EasyOCR reader (languages=%s, gpu=%s)...",
                        self._languages, self._prefer_gpu)
            self._easyocr_reader = easyocr.Reader(
                self._languages, gpu=self._prefer_gpu
            )
        return self._easyocr_reader

    def extract(self, image) -> OCRResult:
        """
        Extract text from an image.

        Args:
            image: PIL Image, numpy array, or file path string.

        Returns:
            OCRResult with extracted text and metadata.
        """
        t0 = time.perf_counter()

        if self._engine_name == "easyocr":
            result = self._extract_easyocr(image)
        elif self._engine_name == "tesseract":
            result = self._extract_tesseract(image)
        else:
            return OCRResult(text="", engine="none", elapsed_ms=0)

        result.elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug("OCR complete: %d chars in %.1fms (%s)",
                      len(result.text), result.elapsed_ms, result.engine)
        return result

    def _extract_easyocr(self, image) -> OCRResult:
        """Extract text using EasyOCR."""
        import numpy as np

        reader = self._get_easyocr()

        # Convert PIL Image to numpy if needed
        if hasattr(image, "convert"):
            image = np.array(image)

        raw = reader.readtext(image)

        blocks = []
        texts = []
        confidences = []
        for bbox, text, conf in raw:
            blocks.append({
                "text": text,
                "bbox": bbox,
                "confidence": conf,
            })
            texts.append(text)
            confidences.append(conf)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0

        return OCRResult(
            text=" ".join(texts),
            blocks=blocks,
            engine="easyocr",
            confidence=avg_conf,
        )

    def _extract_tesseract(self, image) -> OCRResult:
        """Extract text using pytesseract."""
        # Accept PIL Image or file path
        if isinstance(image, str):
            from PIL import Image
            image = Image.open(image)

        text = pytesseract.image_to_string(image)

        # Get detailed data for block-level info
        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            blocks = []
            confidences = []
            for i, txt in enumerate(data["text"]):
                if txt.strip():
                    conf = int(data["conf"][i])
                    if conf > 0:
                        blocks.append({
                            "text": txt,
                            "bbox": [
                                data["left"][i], data["top"][i],
                                data["left"][i] + data["width"][i],
                                data["top"][i] + data["height"][i],
                            ],
                            "confidence": conf / 100.0,
                        })
                        confidences.append(conf / 100.0)
            avg_conf = sum(confidences) / len(confidences) if confidences else 0
        except Exception:
            blocks = []
            avg_conf = 0

        return OCRResult(
            text=text.strip(),
            blocks=blocks,
            engine="tesseract",
            confidence=avg_conf,
        )

    @property
    def available(self) -> bool:
        return self._engine_name != "none"

    @property
    def engine_name(self) -> str:
        return self._engine_name


# ── Module-level singleton ──────────────────────────────────────────────

_ocr: Optional[OCREngine] = None


def get_ocr_engine() -> OCREngine:
    global _ocr
    if _ocr is None:
        _ocr = OCREngine()
    return _ocr
