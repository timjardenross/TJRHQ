"""OCR orchestration (USS-TJR-MSN-0205C).

Tries ocrmypdf first (produces a text-layered PDF, re-extracted with the
PDF parser); falls back to tesseract (rasterise + per-page OCR) if
ocrmypdf is unavailable or fails. PaddleOCR is not in this chain — it's an
interface stub only (see paddleocr_stub.py).

Engine modules are injectable so callers/tests can substitute fakes
without touching subprocess or the filesystem.
"""

from __future__ import annotations

from pathlib import Path

from parsers import pdf_parser

from . import ocrmypdf_engine, tesseract_engine
from .base import OCREngineError, OCRResult


def run_ocr(pdf_path, workdir, low_text_chars_per_page: int = 50, language: str = "eng",
            ocrmypdf_mod=ocrmypdf_engine, tesseract_mod=tesseract_engine,
            pdf_extract=pdf_parser.extract) -> OCRResult:
    """`language` is an ocrmypdf/Tesseract language code, default "eng" —
    MSN-0206A. Passed through to whichever engine actually runs, and
    recorded on the returned OCRResult for provenance."""
    errors = []

    if ocrmypdf_mod.available():
        try:
            workdir = Path(workdir)
            workdir.mkdir(parents=True, exist_ok=True)
            out_path = workdir / f"{Path(pdf_path).stem}.ocr.pdf"
            ocred_path = ocrmypdf_mod.run(pdf_path, out_path, language=language)
            extraction = pdf_extract(ocred_path, low_text_chars_per_page)
            if extraction.text.strip():
                return OCRResult(text=extraction.text, engine="ocrmypdf", success=True, language=language)
            errors.append("ocrmypdf: produced no extractable text")
        except OCREngineError as exc:
            errors.append(f"ocrmypdf: {exc}")
        except Exception as exc:  # noqa: BLE001 — any parser/engine failure should fall through to tesseract
            errors.append(f"ocrmypdf: unexpected error: {exc}")
    else:
        errors.append("ocrmypdf: not available")

    if tesseract_mod.available():
        try:
            text = tesseract_mod.run(pdf_path, language=language)
            if text.strip():
                return OCRResult(text=text, engine="tesseract", success=True, language=language)
            errors.append("tesseract: produced no extractable text")
        except OCREngineError as exc:
            errors.append(f"tesseract: {exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tesseract: unexpected error: {exc}")
    else:
        errors.append("tesseract: not available")

    return OCRResult(text="", engine=None, success=False, error="; ".join(errors))
