"""OCRmyPDF engine — primary OCR path (USS-TJR-MSN-0205C).

Shells out to the `ocrmypdf` CLI (must be installed on the VM). Adds a
searchable text layer to the PDF; `--skip-text` leaves pages that already
have extractable text untouched, so mixed documents (some scanned pages,
some native) OCR only the pages that need it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import OCREngineError


def available() -> bool:
    return shutil.which("ocrmypdf") is not None


def run(pdf_path, output_path, timeout: int = 600, language: str = "eng") -> Path:
    """Run ocrmypdf; returns the path to the OCR'd PDF (with text layer).

    `language` is an ocrmypdf/Tesseract language code (e.g. "eng", "eng+fra"
    for multi-language documents) — MSN-0206A. Only "eng" traineddata ships
    with the base `tesseract` Homebrew formula; additional languages need
    `brew install tesseract-lang` (see ocr/README or the OCR install docs).
    """
    if not available():
        raise OCREngineError("ocrmypdf binary not found on PATH")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ocrmypdf", "--skip-text", "--quiet", "--language", language, str(pdf_path), str(output_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise OCREngineError(f"ocrmypdf timed out after {timeout}s") from exc

    if proc.returncode != 0:
        raise OCREngineError(f"ocrmypdf failed (rc={proc.returncode}): {proc.stderr.strip()[:500]}")
    return output_path
