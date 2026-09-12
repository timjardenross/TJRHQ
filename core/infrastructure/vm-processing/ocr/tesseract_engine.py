"""Tesseract engine — fallback OCR path (USS-TJR-MSN-0205C).

Used when ocrmypdf is unavailable or fails. Rasterises each PDF page with
PyMuPDF and runs the `tesseract` CLI against each page image, concatenating
the results — no PDF text layer is produced, just plain text.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz  # PyMuPDF

from .base import OCREngineError


def available() -> bool:
    return shutil.which("tesseract") is not None


def run(pdf_path, dpi: int = 300, timeout_per_page: int = 120, language: str = "eng") -> str:
    """`language` is a Tesseract language code (e.g. "eng", "eng+fra") —
    MSN-0206A. Only "eng" ships with the base `tesseract` Homebrew formula;
    additional languages need `brew install tesseract-lang`."""
    if not available():
        raise OCREngineError("tesseract binary not found on PATH")

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        raise OCREngineError(f"failed to open PDF for rasterisation: {exc}") from exc

    texts = []
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=dpi)
                img_path = Path(tmpdir) / f"page-{i}.png"
                pix.save(str(img_path))
                try:
                    proc = subprocess.run(
                        ["tesseract", str(img_path), "stdout", "-l", language],
                        capture_output=True, text=True, timeout=timeout_per_page,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise OCREngineError(f"tesseract timed out on page {i}") from exc
                if proc.returncode != 0:
                    raise OCREngineError(
                        f"tesseract failed on page {i} (rc={proc.returncode}): {proc.stderr.strip()[:300]}"
                    )
                texts.append(proc.stdout)
    finally:
        doc.close()

    return "\n\n".join(texts).strip()
