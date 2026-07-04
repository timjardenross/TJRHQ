"""Real-binary OCR integration tests (USS-TJR-MSN-0206A).

Everywhere else in this suite, OCR engines are faked (tests/test_ocr_orchestrator.py)
so CI never depends on ocrmypdf/tesseract being installed. This file is the
one place that exercises the *real* binaries end-to-end — skipped
automatically if they're not on PATH, so it's a no-op in environments
without them (e.g. a bare CI runner) but a genuine regression check
wherever they are installed (this dev machine, the VM once provisioned).
"""
import shutil

import fitz  # PyMuPDF
import pytest

from ocr import ocrmypdf_engine, tesseract_engine, orchestrator
from parsers import pdf_parser

TESSERACT_INSTALLED = shutil.which("tesseract") is not None
OCRMYPDF_INSTALLED = shutil.which("ocrmypdf") is not None


def _make_scanned_pdf(tmp_path, text="MSN-0206A OCR TEST DOCUMENT"):
    """Build a PDF with zero extractable text — a text-bearing raster image
    as the entire page content, the same shape as a real scanned document."""
    text_doc = fitz.open()
    text_page = text_doc.new_page()
    text_page.insert_text((36, 100), text, fontsize=24)
    pix = text_page.get_pixmap(dpi=150)

    scanned_doc = fitz.open()
    page = scanned_doc.new_page(width=pix.width, height=pix.height)
    page.insert_image(page.rect, pixmap=pix)
    out_path = tmp_path / "scanned.pdf"
    scanned_doc.save(str(out_path))
    scanned_doc.close()
    text_doc.close()

    # Sanity: confirm this really is a zero-text "scan", not accidentally readable.
    extraction = pdf_parser.extract(out_path, low_text_chars_per_page=50)
    assert extraction.needs_ocr is True
    return out_path


@pytest.mark.skipif(not OCRMYPDF_INSTALLED, reason="ocrmypdf not installed")
def test_real_ocrmypdf_recovers_text_from_scanned_pdf(tmp_path):
    scanned = _make_scanned_pdf(tmp_path)
    out_path = tmp_path / "ocr-work" / "scanned.ocr.pdf"

    result_path = ocrmypdf_engine.run(scanned, out_path, language="eng")

    # orchestrator.run_ocr() only checks the re-extracted text is non-empty
    # after a successful OCR pass — it does not re-apply the low-text
    # threshold (that heuristic exists to *detect* the need for OCR, not to
    # re-validate a short-but-genuine result afterwards). A single short
    # line of recovered text can legitimately fall under
    # low_text_chars_per_page and still be a correct OCR result.
    extraction = pdf_parser.extract(result_path, low_text_chars_per_page=50)
    assert "MSN-0206A" in extraction.text
    assert "OCR" in extraction.text


@pytest.mark.skipif(not TESSERACT_INSTALLED, reason="tesseract not installed")
def test_real_tesseract_recovers_text_from_scanned_pdf(tmp_path):
    scanned = _make_scanned_pdf(tmp_path)

    text = tesseract_engine.run(scanned, language="eng")

    assert "MSN-0206A" in text
    assert "OCR" in text


@pytest.mark.skipif(not (OCRMYPDF_INSTALLED and TESSERACT_INSTALLED), reason="requires both engines installed")
def test_real_orchestrator_prefers_ocrmypdf_and_records_provenance(tmp_path):
    scanned = _make_scanned_pdf(tmp_path)

    result = orchestrator.run_ocr(scanned, tmp_path / "ocr-work", low_text_chars_per_page=50, language="eng")

    assert result.success is True
    assert result.engine == "ocrmypdf"  # tried first, real binary succeeds, tesseract never invoked
    assert result.language == "eng"
    assert "MSN-0206A" in result.text


@pytest.mark.skipif(not OCRMYPDF_INSTALLED, reason="ocrmypdf not installed")
def test_real_ocrmypdf_reports_clear_error_for_missing_language_pack(tmp_path):
    """MSN-0206A: detect OCR failures — an uninstalled language pack must
    surface as a caught, readable OCREngineError, not a crash."""
    from ocr.base import OCREngineError

    scanned = _make_scanned_pdf(tmp_path)
    out_path = tmp_path / "ocr-work" / "scanned.ocr.pdf"

    with pytest.raises(OCREngineError):
        ocrmypdf_engine.run(scanned, out_path, language="xyz_not_a_real_language")
