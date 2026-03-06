"""
Screen Capture — Fast, low-latency screen grabbing via mss.
=============================================================
Primary capture backend for the vision pipeline. Uses `mss` for
native-speed screen grabs (~10-30ms per 1080p frame).

Supports:
  - Full screen capture
  - Region-of-interest (ROI) capture
  - Multi-monitor selection
  - Frame rate benchmarking
"""

import io
import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("jarvis.vision.capture")

try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    logger.warning("mss not installed. Screen capture disabled. Run: pip install mss")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@dataclass
class CaptureResult:
    """Result of a screen capture operation."""
    image_bytes: bytes          # PNG-encoded image data
    width: int
    height: int
    capture_ms: float           # Time taken to capture in ms
    monitor_index: int = 0      # Which monitor was captured


class ScreenCapture:
    """
    High-performance screen capture using mss.

    Target: <50ms per 1080p frame.
    """

    def __init__(self):
        self._sct: Optional["mss.mss"] = None

    def _ensure_sct(self):
        if self._sct is None:
            if not MSS_AVAILABLE:
                raise ImportError("mss is required for screen capture. pip install mss")
            self._sct = mss.mss()

    @property
    def monitors(self) -> list[dict]:
        """Return list of available monitors with geometry."""
        self._ensure_sct()
        return self._sct.monitors  # [0] = combined, [1..n] = individual

    def capture_full(self, monitor_index: int = 0) -> CaptureResult:
        """
        Capture the entire screen (or a specific monitor).

        Args:
            monitor_index: 0 = all monitors combined, 1 = primary, 2+ = secondary

        Returns:
            CaptureResult with PNG bytes
        """
        self._ensure_sct()
        t0 = time.perf_counter()

        monitor = self._sct.monitors[monitor_index]
        raw = self._sct.grab(monitor)

        # Convert to PNG bytes
        png_bytes = mss.tools.to_png(raw.rgb, raw.size)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug("Screen capture: %dx%d in %.1fms", raw.width, raw.height, elapsed_ms)

        return CaptureResult(
            image_bytes=png_bytes,
            width=raw.width,
            height=raw.height,
            capture_ms=elapsed_ms,
            monitor_index=monitor_index,
        )

    def capture_region(self, left: int, top: int, width: int, height: int) -> CaptureResult:
        """Capture a specific rectangular region of the screen."""
        self._ensure_sct()
        t0 = time.perf_counter()

        region = {"left": left, "top": top, "width": width, "height": height}
        raw = self._sct.grab(region)
        png_bytes = mss.tools.to_png(raw.rgb, raw.size)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        return CaptureResult(
            image_bytes=png_bytes,
            width=raw.width,
            height=raw.height,
            capture_ms=elapsed_ms,
        )

    def capture_as_pil(self, monitor_index: int = 0) -> "Image.Image":
        """Capture and return as a PIL Image (for OCR/analysis pipelines)."""
        if not PIL_AVAILABLE:
            raise ImportError("Pillow required. pip install Pillow")

        result = self.capture_full(monitor_index)
        return Image.open(io.BytesIO(result.image_bytes))

    def benchmark(self, frames: int = 20, monitor_index: int = 1) -> dict:
        """
        Run a capture benchmark.

        Returns dict with avg_ms, min_ms, max_ms, fps.
        """
        times = []
        for _ in range(frames):
            result = self.capture_full(monitor_index)
            times.append(result.capture_ms)

        avg = sum(times) / len(times)
        return {
            "frames": frames,
            "avg_ms": round(avg, 1),
            "min_ms": round(min(times), 1),
            "max_ms": round(max(times), 1),
            "fps": round(1000 / avg, 1) if avg > 0 else 0,
            "target_met": avg < 50,
        }

    def close(self):
        """Release the mss context."""
        if self._sct:
            self._sct.close()
            self._sct = None


# ── Module-level singleton ──────────────────────────────────────────────

_capture: Optional[ScreenCapture] = None


def get_screen_capture() -> ScreenCapture:
    global _capture
    if _capture is None:
        _capture = ScreenCapture()
    return _capture
