"""Docling fallback extractor (IBM Docling — USS-TJR-OSS-GAP-REPORT-2026-08-23).

Used as a last-resort fallback when primary parsers (PyMuPDF, python-docx,
pandas/openpyxl, ocrmypdf, tesseract) fail. Docling handles:
  - PDF (including scanned, multi-column, complex layout)
  - DOCX / PPTX / HTML / Markdown
  - XLSX / XLS / CSV (table extraction)
  - Images (PNG/JPEG via built-in OCR)

It is intentionally NOT the primary extractor — primary parsers are faster
and lighter. Docling runs only when everything else has failed, so install
cost is only paid on actual failures.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import ExtractionResult, ExtractionError

log = logging.getLogger(__name__)


def _available() -> bool:
    try:
        import docling  # noqa: F401
        return True
    except ImportError:
        return False


def extract(path, **_kwargs) -> ExtractionResult:
    """Extract text + tables from path using Docling. Raises ExtractionError on failure."""
    if not _available():
        raise ExtractionError("docling not installed — run: pip install docling")

    from docling.document_converter import DocumentConverter

    path = Path(path)
    log.info("[docling] Attempting extraction: %s", path.name)

    try:
        converter = DocumentConverter()
        result = converter.convert(str(path))
        doc = result.document
    except Exception as exc:
        raise ExtractionError(f"docling conversion failed: {exc}") from exc

    # Primary text via markdown export (preserves structure, headers, lists)
    try:
        text = doc.export_to_markdown()
    except Exception:
        text = ""

    # Fallback: join all text items if markdown export empty
    if not text.strip():
        try:
            parts = []
            for item in doc.texts:
                if hasattr(item, "text") and item.text.strip():
                    parts.append(item.text.strip())
            text = "\n\n".join(parts)
        except Exception:
            pass

    # Append table data as CSV blocks
    table_count = 0
    try:
        for table in doc.tables:
            try:
                df = table.export_to_dataframe()
                if df is not None and not df.empty:
                    table_count += 1
                    text += f"\n\n## Table {table_count}\n{df.to_csv(index=False)}"
            except Exception:
                continue
    except Exception:
        pass

    if not text.strip():
        raise ExtractionError("docling produced no extractable text")

    log.info("[docling] Extracted %d chars, %d table(s) from %s",
             len(text), table_count, path.name)

    return ExtractionResult(
        text=text.strip(),
        needs_ocr=False,
        page_count=None,
        metadata={
            "extractor": "docling",
            "table_count": table_count,
            "char_count": len(text.strip()),
        },
    )
