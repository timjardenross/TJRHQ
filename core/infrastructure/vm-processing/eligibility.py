"""Content Eligibility Engine — USS-TJR-MSN-0206B.

Keeps recreational reading (ebooks, novels, puzzle/self-help books) and
junk/placeholder files out of the Knowledge Library review queue. Two check
points, matching the two points in the pipeline where enough information
exists to decide:

  - check_filename(): extension + filename pattern, run before extraction —
    catches EPUB/MOBI/AZW (unsupported_media) and temp/placeholder files
    (temporary_document) with zero parsing cost.
  - check_content(): extracted text + PDF metadata + page count, run after
    extraction/OCR — scores recreational-content signals (ISBN, ebook
    producer tooling, fiction/genre metadata, book structure, page count,
    author-style filenames) and excludes once independent signals agree.

Calibrated against the real MSN-0205E OneDrive intake set: correctly
excludes all 12 known/discovered ebook-pattern PDFs (calibre- and Internet
Archive-produced books, ISBN-bearing books) while leaving 25 ordinary
business/personal documents eligible — including two government reports
that print an ISBN in their front matter (national-baseline-report-for-
mentally-healthy-workplaces.pdf, national-digital-health-strategy-roadmap-
2023-2028.pdf), which is why ISBN alone never excludes on its own: a real
reference document with an ISBN must not be silently hidden from the
Captain's review queue over a false-positive book match. A single weak
signal (page count alone, filename pattern alone) never excludes on its own
for the same reason — false-excluding a real document is worse than a book
slipping through for manual exclusion later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

UNSUPPORTED_MEDIA_EXTENSIONS = {"epub", "mobi", "azw", "azw3", "fb2", "djvu"}

TEMPORARY_FILENAME_EXTENSIONS = {"crdownload", "part", "download", "tmp"}
TEMPORARY_FILENAME_STEMS = {"untitled", "new document", "document1", "draft"}

ISBN_RE = re.compile(
    r"ISBN[-\s]*(?:1[03])?[:\s]*(?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx]", re.IGNORECASE
)
CHAPTER_RE = re.compile(r"^\s*chapter\s+\S+", re.IGNORECASE | re.MULTILINE)
TOC_RE = re.compile(r"table of contents", re.IGNORECASE)
FICTION_KEYWORDS = ("fiction", "novel", "short stories", "literary fiction")
EBOOK_PRODUCER_TOOLS = ("calibre", "internet archive")
LASTNAME_FIRSTNAME_RE = re.compile(r"^[A-Z][a-zA-Z'-]+,\s*[A-Z][a-zA-Z.'-]+")
AUTHOR_NAME_TAIL_RE = re.compile(r"^(?:[A-Z][A-Za-z.]*\s?){1,4}$")

CONTENT_SCAN_CHARS = 8000  # front matter (title/copyright page) is near the start
PAGE_COUNT_THRESHOLD = 100
RECREATIONAL_SCORE_THRESHOLD = 3

# Score weights — calibrated so no single weak signal crosses the threshold
# alone (see module docstring for the false-positive case that drove this).
SCORE_EBOOK_PRODUCER_TOOL = 3
SCORE_ISBN = 2
SCORE_FICTION_KEYWORD = 2
SCORE_BOOK_STRUCTURE = 2
SCORE_AUTHOR_METADATA = 1
SCORE_PAGE_COUNT = 1
SCORE_FILENAME_PATTERN = 1


@dataclass
class EligibilityResult:
    eligible: bool
    reason: str = None  # 'recreational_content' | 'unsupported_media' | 'temporary_document'
    detail: str = None
    evidence: dict = field(default_factory=dict)


def _stem_and_ext(filename: str):
    if "." in filename:
        stem, _, ext = filename.rpartition(".")
        return stem, ext.lower()
    return filename, ""


def check_filename(filename: str) -> EligibilityResult:
    """Fast, pre-extraction check on filename/extension alone."""
    stem, ext = _stem_and_ext(filename)

    if ext in UNSUPPORTED_MEDIA_EXTENSIONS:
        return EligibilityResult(
            False, "unsupported_media",
            f"file extension '.{ext}' is not a supported document format",
            {"extension": ext},
        )

    if ext in TEMPORARY_FILENAME_EXTENSIONS or filename.startswith("~$") or stem.strip().lower() in TEMPORARY_FILENAME_STEMS:
        return EligibilityResult(
            False, "temporary_document",
            f"filename '{filename}' matches a temporary/placeholder pattern",
            {"filename": filename},
        )

    return EligibilityResult(True)


def _filename_author_tail(stem: str) -> str:
    for delim in ("_-_", " - "):
        if delim in stem:
            _, _, tail = stem.rpartition(delim)
            return tail.replace("_", " ").strip()
    return ""


def _looks_like_author_name(tail: str) -> bool:
    return bool(tail) and len(tail) <= 40 and bool(AUTHOR_NAME_TAIL_RE.match(tail))


def check_content(filename: str, text: str, page_count: int = None, pdf_metadata: dict = None) -> EligibilityResult:
    """Content-based check, run after extraction/OCR — scores
    recreational-content signals and excludes once enough independent
    signals agree (see module docstring for the scoring rationale)."""
    pdf_metadata = pdf_metadata or {}
    text = text or ""
    score = 0
    evidence = {}

    creator_producer = f"{pdf_metadata.get('creator', '')} {pdf_metadata.get('producer', '')}".lower()
    matched_tool = next((tool for tool in EBOOK_PRODUCER_TOOLS if tool in creator_producer), None)
    if matched_tool:
        score += SCORE_EBOOK_PRODUCER_TOOL
        evidence["ebook_producer_tool"] = matched_tool

    if ISBN_RE.search(text[:CONTENT_SCAN_CHARS]):
        score += SCORE_ISBN
        evidence["isbn_found"] = True

    subject_and_keywords = f"{pdf_metadata.get('subject', '')} {pdf_metadata.get('keywords', '')}".lower()
    matched_fiction_kw = next((kw for kw in FICTION_KEYWORDS if kw in subject_and_keywords), None)
    if matched_fiction_kw:
        score += SCORE_FICTION_KEYWORD
        evidence["fiction_keyword"] = matched_fiction_kw

    scan_text = text[:CONTENT_SCAN_CHARS]
    if len(CHAPTER_RE.findall(scan_text)) >= 3 and TOC_RE.search(scan_text):
        score += SCORE_BOOK_STRUCTURE
        evidence["book_structure"] = "table of contents + 3+ chapter markers"

    author = str(pdf_metadata.get("author") or "")
    if LASTNAME_FIRSTNAME_RE.match(author):
        score += SCORE_AUTHOR_METADATA
        evidence["author_metadata_pattern"] = author

    if page_count and page_count >= PAGE_COUNT_THRESHOLD:
        score += SCORE_PAGE_COUNT
        evidence["page_count"] = page_count

    stem, _ = _stem_and_ext(filename)
    author_tail = _filename_author_tail(stem)
    if _looks_like_author_name(author_tail):
        score += SCORE_FILENAME_PATTERN
        evidence["filename_pattern"] = author_tail

    if score >= RECREATIONAL_SCORE_THRESHOLD:
        return EligibilityResult(
            False, "recreational_content",
            f"recreational-content score {score} (threshold {RECREATIONAL_SCORE_THRESHOLD})",
            evidence,
        )

    return EligibilityResult(True, evidence=evidence)
