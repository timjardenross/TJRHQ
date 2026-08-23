"""Extraction dispatch by file extension (USS-TJR-MSN-0205C)."""

from __future__ import annotations

from pathlib import Path

from .base import ExtractionResult, ExtractionError, UnsupportedFileTypeError

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".xls")

__all__ = ["ExtractionResult", "ExtractionError", "UnsupportedFileTypeError",
           "SUPPORTED_EXTENSIONS", "extract"]


def extract(path, low_text_chars_per_page: int = 50) -> ExtractionResult:
    ext = Path(path).suffix.lower()
    primary_error: ExtractionError | None = None

    if ext == ".pdf":
        from . import pdf_parser
        return pdf_parser.extract(path, low_text_chars_per_page)
    if ext == ".docx":
        from . import docx_parser
        try:
            return docx_parser.extract(path)
        except ExtractionError as exc:
            primary_error = exc
    elif ext in (".txt", ".md"):
        from . import text_parser
        return text_parser.extract(path)
    elif ext in (".csv", ".xlsx", ".xls"):
        from . import tabular_parser
        try:
            return tabular_parser.extract(path)
        except ExtractionError as exc:
            primary_error = exc
    else:
        raise UnsupportedFileTypeError(f"unsupported file extension: {ext}")

    # Primary extractor failed — try Docling as fallback (handles .xls natively,
    # can recover corrupted/unusual DOCX/XLSX that pandas/python-docx reject).
    try:
        from . import docling_parser
        return docling_parser.extract(path)
    except ExtractionError as docling_exc:
        raise ExtractionError(
            f"primary failed ({primary_error}); docling fallback also failed ({docling_exc})"
        ) from primary_error
