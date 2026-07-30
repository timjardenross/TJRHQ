"""Tests for the Content Eligibility Engine (USS-TJR-MSN-0206B).

Cases below mirror real PDF metadata pulled from the MSN-0205E OneDrive
intake set (core/infrastructure/vm-processing/eligibility.py's module
docstring records the calibration run) — not invented numbers.
"""

import eligibility


# -- check_filename ---------------------------------------------------------------

def test_epub_is_unsupported_media():
    result = eligibility.check_filename("Some_Novel_-_Jane_Doe.epub")
    assert result.eligible is False
    assert result.reason == "unsupported_media"


def test_mobi_is_unsupported_media():
    result = eligibility.check_filename("book.mobi")
    assert result.eligible is False
    assert result.reason == "unsupported_media"


def test_office_lock_file_is_temporary_document():
    result = eligibility.check_filename("~$ANZ Contract.docx")
    assert result.eligible is False
    assert result.reason == "temporary_document"


def test_incomplete_download_is_temporary_document():
    result = eligibility.check_filename("statement.pdf.crdownload")
    assert result.eligible is False
    assert result.reason == "temporary_document"


def test_placeholder_stem_is_temporary_document():
    result = eligibility.check_filename("Untitled.pdf")
    assert result.eligible is False
    assert result.reason == "temporary_document"


def test_ordinary_pdf_filename_is_eligible():
    result = eligibility.check_filename("ANZ Contract.pdf")
    assert result.eligible is True
    assert result.reason is None


# -- check_content: known ebooks from the real intake set ---------------------------------------------------------------

def test_calibre_produced_ebook_is_recreational_content():
    """Physicians_Directory_Of_Trusted_Remedies_-_Mark_E_Johnson.pdf: real
    creator/producer = 'calibre 7.4.0', 464 pages."""
    result = eligibility.check_content(
        "Physicians_Directory_Of_Trusted_Remedies_-_Mark_E_Johnson.pdf",
        text="Some recovered body text with no special markers.",
        page_count=464,
        pdf_metadata={"creator": "calibre 7.4.0", "producer": "calibre 7.4.0",
                      "author": "Mark E. Johnson"},
    )
    assert result.eligible is False
    assert result.reason == "recreational_content"
    assert result.evidence["ebook_producer_tool"] == "calibre"


def test_internet_archive_scan_is_recreational_content():
    """The_Mirror_Mind_-_William_Johnston.pdf: real creator contains
    'Internet Archive (Scribe Version...)', author 'Johnston, William, 1925-2010'."""
    result = eligibility.check_content(
        "The_Mirror_Mind_-_William_Johnston.pdf",
        text="Recovered scanned text.",
        page_count=196,
        pdf_metadata={
            "creator": "Internet Archive (Scribe Version 4.5-initial-63-g7e8faad7)",
            "producer": "Internet Archive PDF 1.2.0; including mupdf and pymupdf/skimage",
            "author": "Johnston, William, 1925-2010",
        },
    )
    assert result.eligible is False
    assert result.reason == "recreational_content"
    assert result.evidence["ebook_producer_tool"] == "internet archive"
    assert "author_metadata_pattern" in result.evidence


def test_isbn_plus_filename_pattern_plus_page_count_is_recreational_content():
    """Banking_50_-_Bernardo_Nicoletti.pdf: real producer 'Springer-i' (not
    calibre/IA), 553 pages, real body text contains an ISBN line — no single
    signal alone should cross the threshold, but the combination does."""
    text = "Some front matter.\nISBN 978-3-030-70719-4\nMore text follows." + ("x" * 100)
    result = eligibility.check_content(
        "Banking_50_-_Bernardo_Nicoletti.pdf",
        text=text,
        page_count=553,
        pdf_metadata={"producer": "Springer-i"},
    )
    assert result.eligible is False
    assert result.reason == "recreational_content"
    assert result.evidence["isbn_found"] is True
    assert result.evidence["page_count"] == 553
    assert result.evidence["filename_pattern"] == "Bernardo Nicoletti"


def test_book_structure_signal_contributes_to_exclusion():
    """Simplified_Herbal_Remedies_for_Beginners_-_Aurora_Hawthorne.pdf: real
    body has a 'Table of Contents' plus 11 'Chapter N' markers."""
    text = (
        "Table of Contents\n"
        "Chapter 1: Introduction\n"
        "Chapter 2: Basics\n"
        "Chapter 3: Advanced\n"
    )
    result = eligibility.check_content(
        "Simplified_Herbal_Remedies_for_Beginners_-_Aurora_Hawthorne.pdf",
        text=text, page_count=100, pdf_metadata={"creator": "calibre 7.4.0"},
    )
    assert result.eligible is False
    assert result.evidence["book_structure"] == "table of contents + 3+ chapter markers"


# -- check_content: real false-positive risk — government reports with an ISBN ---------------------------------------------------------------

def test_government_report_with_isbn_stays_eligible():
    """national-baseline-report-for-mentally-healthy-workplaces.pdf: a real
    53-page government report that legitimately prints an ISBN in its front
    matter but is not a book — must not be silently hidden from the
    Captain's review queue. ISBN alone must never cross the threshold."""
    text = "Front matter.\nISBN: 978-0-6450123-4-5\nContents follow." + ("x" * 100)
    result = eligibility.check_content(
        "national-baseline-report-for-mentally-healthy-workplaces.pdf",
        text=text, page_count=53, pdf_metadata={},
    )
    assert result.eligible is True
    assert result.evidence.get("isbn_found") is True  # signal recorded, but not enough alone


def test_isbn_alone_never_excludes():
    result = eligibility.check_content(
        "quarterly-report.pdf",
        text="ISBN 978-1-23456-789-7 appears somewhere in this document.",
        page_count=10,
        pdf_metadata={},
    )
    assert result.eligible is True


def test_page_count_alone_never_excludes():
    result = eligibility.check_content(
        "ANZ Enterprise Agreement 2023-2027 (Australia).pdf",
        text="A long enterprise agreement with no book markers.",
        page_count=200,
        pdf_metadata={},
    )
    assert result.eligible is True


def test_filename_pattern_alone_never_excludes():
    result = eligibility.check_content(
        "Quarterly_Update_-_Finance_Team.pdf",
        text="Ordinary business text.",
        page_count=5,
        pdf_metadata={},
    )
    assert result.eligible is True


# -- check_content: ordinary business/personal documents from the real intake set ---------------------------------------------------------------

def test_ordinary_contract_stays_eligible():
    """ANZ Contract.pdf: real producer 'iText... Apryse... ServiceNow', 14 pages."""
    result = eligibility.check_content(
        "ANZ Contract.pdf",
        text="This agreement is entered into between the parties.",
        page_count=14,
        pdf_metadata={"producer": "iText Core 8.0.4 ... ServiceNow"},
    )
    assert result.eligible is True


def test_scanned_personal_document_stays_eligible():
    """Change of Member Details.pdf: real creator 'Adobe InDesign', 4 pages."""
    result = eligibility.check_content(
        "Change of Member Details.pdf",
        text="Please update my member details as follows.",
        page_count=4,
        pdf_metadata={"creator": "Adobe InDesign 19.4 (Macintosh)"},
    )
    assert result.eligible is True


def test_dashed_filename_without_author_shape_does_not_trigger_filename_pattern():
    """03042025 - Enforceable Undertaking - Australia and New Zealand
    Banking Group Ltd.pdf: contains ' - ' but the tail after the last
    occurrence is not a short author-name-shaped string."""
    result = eligibility.check_content(
        "03042025 - Enforceable Undertaking - Australia and New Zealand Banking Group Ltd.pdf",
        text="Regulatory undertaking text.", page_count=12, pdf_metadata={},
    )
    assert result.eligible is True
    assert "filename_pattern" not in result.evidence
