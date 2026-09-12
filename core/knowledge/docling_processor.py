"""
Docling-based document processor for the knowledge pipeline (USS-TJR-MSN-0366
Stream 3 — Stage 2A New Open-Source Tool Adoption).

Extracts structured markdown (headings, lists, tables) from PDF/Word/HTML —
IBM's Docling (github.com/docling-project/docling), CPU-only, no
infra beyond the `pip install docling` package itself. See
`knowledge/OSS-Gap-Solutions-2026-08-23.md` GAP 5 for the original proposal.

Runs from its own isolated venv (platform-runtime/.venv-docling), NOT
platform-runtime/.venv — docling's dependency graph pulls in torch,
transformers, and (on a plain `pip install docling`) the full CUDA build
of torch even for CPU-only use, ~6.2GB installed (confirmed live,
2026-09-12). See `core/knowledge/requirements-docling.txt` for the exact
install commands (including how to avoid the CUDA-torch download). That
footprint has zero business being a transitive dependency of every other
tool that imports platform-runtime/requirements.txt.

Falls back gracefully if docling is unavailable at all, or if a specific
conversion fails — callers (ingest_knowledge.py, docling_ingest.py) treat
`None` as "use a plainer extraction path instead", never as a hard error.

Confirmed real rough edge (2026-09-12, this sandbox): docling's default
PDF pipeline (StandardPdfPipeline) unconditionally initialises a
HuggingFace-hosted layout-detection model on first use
(`docling-project/docling-layout-heron`) — every PDF conversion needs it,
regardless of do_ocr/do_table_structure settings, because
`_init_models()` builds it unconditionally
(docling/pipeline/standard_pdf_pipeline.py). In a network-restricted
environment where huggingface.co is not reachable, that raises inside
DocumentConverter.convert() (confirmed live: `httpx.ProxyError: 403
Forbidden` against huggingface.co). DOCX and HTML need no such model —
both backends parse the file's own structure directly and worked
out of the box, offline, in this same sandbox.

Since a genuinely offline environment shouldn't lose PDF text extraction
entirely over this, `extract_document()` retries a failed PDF conversion
using docling's `NativePdfPipeline` — text-layer extraction straight from
the PDF's embedded text via pypdfium2, no ML model, no network call. The
trade-off, also confirmed live: no table-structure recognition for PDFs
extracted this way (TableFormer is part of the ML pipeline this fallback
skips) — a scanned/image-only PDF also will not extract via this fallback
either (no OCR ran). Both are logged in the returned metadata
(`layout_fallback: true` / table_count: 0) so a reviewer can tell a
network-degraded extraction from a normal one, and so a deployment with
real internet egress (or a pre-warmed local HF cache under
`artifacts_path`) can confirm it never needed the fallback at all.
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

PDF_SUFFIXES = {".pdf"}


def _extract_tables(doc) -> list[dict]:
    tables = []
    for table in getattr(doc, "tables", []) or []:
        try:
            df = table.export_to_dataframe()
            if df is not None and not df.empty:
                tables.append(df.to_dict())
        except Exception:  # noqa: BLE001,S112 - best-effort per-table export; one malformed table must not lose the rest
            continue
    return tables


def _convert_pdf_native(path: Path):
    """Text-layer-only PDF conversion — no ML layout/OCR model, no network.
    Used as the fallback when the standard pipeline's layout model can't be
    fetched (offline/restricted-egress host) or otherwise fails."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import NativePdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.pipeline.native_pdf_pipeline import NativePdfPipeline

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=NativePdfPipelineOptions(),
                pipeline_cls=NativePdfPipeline,
            )
        }
    )
    return converter.convert(str(path))


def extract_document(file_path: str | Path) -> dict | None:
    """
    Extract structured content from a document file (PDF/DOCX/HTML/PPTX/etc
    — anything docling's DocumentConverter recognises).

    Returns dict with keys: text (markdown), tables (list of dict-of-columns,
    one per extracted table), metadata, source_path.
    Returns None if extraction fails outright — caller should fall back to
    a plainer extraction (e.g. raw read_text for already-text formats).
    """
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        log.warning(
            "docling not available (pip install docling into "
            "platform-runtime/.venv-docling — see that dir's setup notes) "
            "— falling back to raw file read"
        )
        return None

    path = Path(file_path)
    layout_fallback = False
    try:
        converter = DocumentConverter()
        result = converter.convert(str(path))
        doc = result.document
    except Exception as exc:  # noqa: BLE001 - already handled: PDF retry-with-fallback-pipeline logic follows in this except block
        if path.suffix.lower() in PDF_SUFFIXES:
            log.warning(
                "docling standard PDF pipeline failed for %s (%s) — retrying "
                "with NativePdfPipeline (text-layer only, no layout/table ML "
                "model, no network required)",
                path.name, exc,
            )
            try:
                result = _convert_pdf_native(path)
                doc = result.document
                layout_fallback = True
            except Exception as exc2:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
                log.warning("docling native-PDF fallback also failed for %s: %s", path, exc2)
                return None
        else:
            log.warning("docling extraction failed for %s: %s", path, exc)
            return None

    try:
        text = doc.export_to_markdown()
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
        log.warning("docling markdown export failed for %s: %s", path, exc)
        return None

    if not text or not text.strip():
        log.warning("docling produced no extractable text for %s", path)
        return None

    tables = _extract_tables(doc)
    return {
        "text": text,
        "tables": tables,
        "metadata": {
            "source_path": str(path),
            "format": path.suffix.lower(),
            "extractor": "docling",
            "table_count": len(tables),
            "char_count": len(text),
            "layout_fallback": layout_fallback,
        },
        "source_path": str(path),
    }
