"""PaddleOCR interface stub (USS-TJR-MSN-0205C).

Mission scope explicitly calls for an interface stub only, not a working
integration. `orchestrator.run_ocr()` never calls this automatically — it
tries ocrmypdf then tesseract. Wire PaddleOCR in here (and into the
orchestrator's fallback chain) if it's adopted later; until then this
raises clearly rather than silently returning empty text.
"""

from __future__ import annotations

from .base import OCREngineError


def available() -> bool:
    return False


def run(pdf_path, **kwargs) -> str:
    raise OCREngineError(
        "PaddleOCR is not implemented (interface stub only, USS-TJR-MSN-0205C scope)"
    )
