import pytest

from ocr import orchestrator, paddleocr_stub
from ocr.base import OCREngineError


class _Unavailable:
    @staticmethod
    def available():
        return False


class _OcrMyPdfSuccess:
    @staticmethod
    def available():
        return True

    @staticmethod
    def run(pdf_path, out_path, language=None):
        return out_path


class _OcrMyPdfFails:
    @staticmethod
    def available():
        return True

    @staticmethod
    def run(pdf_path, out_path, language=None):
        raise OCREngineError("ocrmypdf exploded")


class _TesseractSuccess:
    @staticmethod
    def available():
        return True

    @staticmethod
    def run(pdf_path, language=None):
        return "tesseract extracted text"


class _TesseractEmpty:
    @staticmethod
    def available():
        return True

    @staticmethod
    def run(pdf_path, language=None):
        return ""


def _fake_pdf_extract(path, threshold):
    class R:
        text = "OCR extracted text here"
    return R()


def test_both_engines_unavailable(tmp_path):
    result = orchestrator.run_ocr("fake.pdf", tmp_path,
                                   ocrmypdf_mod=_Unavailable, tesseract_mod=_Unavailable)
    assert result.success is False
    assert "not available" in result.error


def test_ocrmypdf_success_short_circuits_tesseract(tmp_path):
    result = orchestrator.run_ocr("fake.pdf", tmp_path,
                                   ocrmypdf_mod=_OcrMyPdfSuccess, tesseract_mod=_TesseractSuccess,
                                   pdf_extract=_fake_pdf_extract)
    assert result.success is True
    assert result.engine == "ocrmypdf"
    assert result.text == "OCR extracted text here"


def test_falls_back_to_tesseract_when_ocrmypdf_fails(tmp_path):
    result = orchestrator.run_ocr("fake.pdf", tmp_path,
                                   ocrmypdf_mod=_OcrMyPdfFails, tesseract_mod=_TesseractSuccess)
    assert result.success is True
    assert result.engine == "tesseract"
    assert result.text == "tesseract extracted text"


def test_both_engines_produce_no_text_reports_failure(tmp_path):
    result = orchestrator.run_ocr("fake.pdf", tmp_path,
                                   ocrmypdf_mod=_OcrMyPdfFails, tesseract_mod=_TesseractEmpty)
    assert result.success is False
    assert "ocrmypdf" in result.error and "tesseract" in result.error


def test_language_is_threaded_through_to_engine_and_result(tmp_path):
    """MSN-0206A: future language expansion — run_ocr's language argument
    must reach whichever engine actually runs, and be recorded on the
    returned OCRResult for provenance."""
    seen = {}

    class _OcrMyPdfCapturesLanguage:
        @staticmethod
        def available():
            return True

        @staticmethod
        def run(pdf_path, out_path, language=None):
            seen["language"] = language
            return out_path

    result = orchestrator.run_ocr("fake.pdf", tmp_path, language="eng+fra",
                                   ocrmypdf_mod=_OcrMyPdfCapturesLanguage, tesseract_mod=_Unavailable,
                                   pdf_extract=_fake_pdf_extract)
    assert seen["language"] == "eng+fra"
    assert result.success is True
    assert result.language == "eng+fra"


def test_paddleocr_stub_raises_clearly():
    with pytest.raises(OCREngineError, match="interface stub only"):
        paddleocr_stub.run("fake.pdf")
    assert paddleocr_stub.available() is False
