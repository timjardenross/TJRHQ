"""
Docling-based document processor for the knowledge pipeline.
Extracts text, tables, and metadata from PDF/Word/HTML/Markdown.
Falls back gracefully if docling unavailable.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def extract_document(file_path: "str | Path") -> Optional[dict]:
    """
    Extract structured content from a document file.
    Returns dict with keys: text, tables, metadata, source_path
    Returns None if extraction fails — caller should fall back to raw read.
    """
    try:
        from docling.document_converter import DocumentConverter
        converter = DocumentConverter()
        result = converter.convert(str(file_path))
        return {
            "text": result.document.export_to_markdown(),
            "tables": [t.export_to_dataframe().to_dict() for t in result.document.tables] if hasattr(result.document, "tables") else [],
            "metadata": {"source_path": str(file_path), "format": Path(file_path).suffix},
            "source_path": str(file_path),
        }
    except ImportError:
        log.warning("docling not available — falling back to raw file read")
        return None
    except Exception as e:
        log.warning("docling extraction failed for %s: %s", file_path, e)
        return None
