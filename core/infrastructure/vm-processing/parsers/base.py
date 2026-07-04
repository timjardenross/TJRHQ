"""Shared types for document parsers (USS-TJR-MSN-0205C)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractionResult:
    text: str
    needs_ocr: bool = False
    page_count: int = None
    metadata: dict = field(default_factory=dict)


class UnsupportedFileTypeError(ValueError):
    pass


class ExtractionError(RuntimeError):
    pass
