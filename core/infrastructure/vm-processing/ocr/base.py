"""Shared types for OCR engines (USS-TJR-MSN-0205C)."""

from __future__ import annotations

from dataclasses import dataclass


class OCREngineError(RuntimeError):
    pass


@dataclass
class OCRResult:
    text: str
    engine: str = None
    success: bool = False
    error: str = ""
    language: str = None
