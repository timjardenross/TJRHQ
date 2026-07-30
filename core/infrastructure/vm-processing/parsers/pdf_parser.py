"""PDF extraction via PyMuPDF, with low-text (scanned) detection
(USS-TJR-MSN-0205C).

A PDF page with little or no extractable text is almost always a scanned
image rather than a page with genuinely no content — averaging under
`low_text_chars_per_page` characters per page flags the whole document for
OCR rather than accepting a near-empty extraction.
"""

from __future__ import annotations

import fitz  # PyMuPDF

from .base import ExtractionResult, ExtractionError


def extract(path, low_text_chars_per_page: int = 50) -> ExtractionResult:
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise ExtractionError(f"failed to open PDF: {exc}") from exc

    try:
        page_texts = [page.get_text() for page in doc]
        page_count = doc.page_count
        pdf_info = {k: v for k, v in (doc.metadata or {}).items() if v}
    finally:
        doc.close()

    text = "\n\n".join(page_texts)
    total_chars = sum(len(t.strip()) for t in page_texts)
    avg_chars_per_page = (total_chars / page_count) if page_count else 0
    needs_ocr = avg_chars_per_page < low_text_chars_per_page

    return ExtractionResult(
        text=text.strip(),
        needs_ocr=needs_ocr,
        page_count=page_count,
        metadata={
            "avg_chars_per_page": round(avg_chars_per_page, 1),
            "total_chars": total_chars,
            "low_text_threshold": low_text_chars_per_page,
            # PyMuPDF's Info-dict metadata (title/author/subject/keywords/
            # creator/producer) — feeds the Content Eligibility Engine's
            # ebook-producer-tool and author-pattern checks (USS-TJR-MSN-0206B).
            "pdf_info": pdf_info,
        },
    )
