"""Extraction dispatch by file extension (USS-TJR-MSN-0205C)."""

from __future__ import annotations

from pathlib import Path

from .base import ExtractionResult, ExtractionError, UnsupportedFileTypeError

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".xls")

__all__ = ["ExtractionResult", "ExtractionError", "UnsupportedFileTypeError",
           "SUPPORTED_EXTENSIONS", "extract"]


def extract(path, low_text_chars_per_page: int = 50) -> ExtractionResult:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        from . import pdf_parser
        return pdf_parser.extract(path, low_text_chars_per_page)
    if ext == ".docx":
        from . import docx_parser
        return docx_parser.extract(path)
    if ext in (".txt", ".md"):
        from . import text_parser
        return text_parser.extract(path)
    if ext in (".csv", ".xlsx", ".xls"):
        from . import tabular_parser
        return tabular_parser.extract(path)
    raise UnsupportedFileTypeError(f"unsupported file extension: {ext}")
