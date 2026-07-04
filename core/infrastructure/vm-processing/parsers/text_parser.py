"""Plain text / Markdown extraction (USS-TJR-MSN-0205C)."""

from __future__ import annotations

from pathlib import Path

from .base import ExtractionResult


def extract(path) -> ExtractionResult:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return ExtractionResult(text=text.strip(), needs_ocr=False, page_count=1,
                             metadata={"char_count": len(text)})
