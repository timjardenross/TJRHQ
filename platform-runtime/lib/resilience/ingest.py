"""Ingest clause text from an official document into a corpus framework file.

Works on plain text so no PDF library is needed — extract first with poppler::

    pdftotext -layout CPS230.pdf /tmp/cps230.txt
    cd platform-runtime
    python -m lib.resilience.ingest APRA-CPS-230 /tmp/cps230.txt --style apra --source-file CPS230.pdf

Styles:
- ``apra``  — numbered paragraphs (``34.  An APRA-regulated entity must ...``); the most
  recent un-numbered heading line is kept as the paragraph's heading.
- ``apra-guide`` — APRA prudential practice guides (CPG): column-0 paragraphs, boxed
  extracts of the standard skipped.
- ``bcbs``  — Basel ``Principle N:`` statements only (BIS permits brief excerpts, so the
  explanatory paragraphs are not stored).
- ``eu``    — EU regulations (``Article N`` + heading line), e.g. DORA.
- ``pra``   — Bank of England / PRA statements (``2.1`` chapter.paragraph numbering).
- ``nist``  — NIST CSF 2.0 Core (Functions, Categories, Subcategories by official ID).
- ``occ``   — US interagency sound practices (OCC 2020-94): ``3. Section`` + ``a)`` practices.
- ``fca``   — FCA Handbook instrument text (PS21/3 → SYSC 15A): ``15A.2.1  R  text``.

Provenance: ``ingestion.source_digest`` records ``sha256:<hex>`` of the source file.

Licence guard: frameworks whose ``licence`` is ``proprietary`` (paid ISO standards) are
refused unless ``--licensed`` is passed, so paid text isn't committed by accident.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import change_flags
from .corpus import DEFAULT_CORPUS_DIR

_APRA_PARA_RE = re.compile(r"^\s*(\d{1,3})\.\s+(\S.*)$")
_BCBS_PRINCIPLE_RE = re.compile(r"^\s*Principle\s+(\d{1,2})\s*[:.]\s*(.*)$", re.IGNORECASE)
_HEADING_RE = re.compile(r"^\s*([A-Z][A-Za-z ,&/'()-]{3,80})\s*$")
_NOISE_RE = re.compile(r"^\s*(\d+\s*$|page \d+|cps \d+ - \d+|\f)", re.IGNORECASE)


_APRA_FOOTER_RE = re.compile(r"^\s*[A-Z]{2,4}\s*\d{3}\s*[–-]\s*\d+\s*$")
_MONTHS = "(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_MONTH_HEADER_RE = re.compile(
    r"^\s*(?:APRA\s+)?(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*$"
    # CPG page footer: "APRA July 2026   <page>"
    r"|^\s*APRA\s+[A-Z][a-z]+\s+\d{4}\s+\d{1,3}\s*$")
_FOOTNOTE_NUM_RE = re.compile(r"^\s*(\d{1,2})\s*$")
_PRIVATE_USE_RE = re.compile("[\ue000-\uf8ff\u2022]")


# "Level 2 group", "Category C", "paragraph 6": a number after these words is a reference, not a marker.
_XREF_LOOKBEHIND = "".join(f"(?<!{w})" for w in (
    "Level", "Category", "Tier", "paragraph", "Paragraph", "paragraphs", "section", "Section",
    "Part", "Attachment", "Schedule", "Principle", "Article", "Chapter", "Table", "Rule"))


def _strip_footnote_ref(line: str, n: int) -> tuple[str, bool]:
    """Remove the inline marker for footnote ``n`` (``Act. 1``, ``group, 2 it``, glued: ``operations.1``,
    ``group’,2``, ``Board4``).
    A number followed by a month ("on 1 July 2019") is a date, never a marker."""
    new, count = re.subn(rf"(?:(?<=[A-Za-z.,;:)’]){_XREF_LOOKBEHIND}\s+|(?<=[a-z][.,;:)’])|(?<=[a-z]’,)|(?<=[a-z])){n}(?=\s|$)(?!\s+{_MONTHS})",
                         "", line, count=1)
    return new, bool(count)


def parse_apra_guide(text: str, framework_id: str) -> list[dict]:
    """APRA prudential practice guide (CPG) layout: the guide's own paragraphs start at column 0,
    while the boxed extracts of the prudential standard it explains are indented two spaces and
    carry the *standard's* paragraph numbers. Those boxes are skipped (the standard is ingested
    on its own), so they neither break the guide's numbering nor leak into its paragraphs."""
    return parse_apra(text, framework_id, guide=True)


def parse_apra(text: str, framework_id: str, guide: bool = False) -> list[dict]:
    """APRA prudential standard layout: numbered paragraphs under sentence-case headings.

    Handles the real-document furniture: page footers (``CPS 230 – 3``), month/year page
    headers, footnote blocks (a bare sequential number at the page bottom, its text running
    to the page footer) and their inline markers, and bullet glyphs. Paragraph numbers must
    run in sequence, so a stray number in body text can't start a new clause.
    """
    clauses: list[dict] = []
    heading = ""
    current: dict | None = None
    expected = 1
    next_footnote = 1      # next footnote block number expected at a page bottom
    next_ref = 1           # next inline footnote marker expected in body text
    in_footnote = False
    in_table = False       # guide mode: a "Table N" body, whose columns pdftotext interleaves
    for raw in text.splitlines():
        line = _PRIVATE_USE_RE.sub(" ", raw).replace("\f", "")
        if not line.strip():
            continue
        if _APRA_FOOTER_RE.match(line):
            in_footnote = False
            continue
        if _MONTH_HEADER_RE.match(line) or re.match(r"^\s*page \d+", line, re.IGNORECASE):
            in_footnote = False  # page header/footer: any footnote block has ended
            continue
        if guide and re.match(r"^  \S", line):
            continue  # boxed extract of the standard (exactly two-space indent)
        if guide and re.match(r"^Table \d+[.:]", line):
            in_table = True  # tables are excluded; the next paragraph ends one
            continue
        fn = _FOOTNOTE_NUM_RE.match(line)
        if fn and int(fn.group(1)) == next_footnote:
            in_footnote = True
            next_footnote += 1
            continue
        if in_footnote:
            continue
        line, stripped = _strip_footnote_ref(line, next_ref)
        if stripped:
            next_ref += 1
        para = None if (guide and line[:1].isspace()) else _APRA_PARA_RE.match(line)
        if para and int(para.group(1)) == expected:
            if current:
                clauses.append(current)
            n = para.group(1)
            current = {"clause_id": f"{framework_id}-para-{n}", "ref": f"para {n}",
                       "heading": heading, "text": " ".join(para.group(2).split()),
                       "text_status": "verbatim", "tags": []}
            expected += 1
            in_table = False
            continue
        head = _HEADING_RE.match(line)
        # Headings sit at column 0; wrapped body lines are indented under their paragraph.
        if (head and not line[:1].isspace() and not line.rstrip().endswith((".", ";", ",", "-"))
                and len(line.split()) <= 10):
            heading = head.group(1).strip()
            continue
        if current and not in_table:
            # A line ending in "-" wrapped a hyphenated word (APRA-\nregulated): join without a space.
            sep = "" if current["text"].endswith("-") else " "
            current["text"] += sep + " ".join(line.split())
    if current:
        clauses.append(current)
    return clauses


_BCBS_XREF_WORDS = frozenset({"principle", "principles", "paragraph", "paragraphs", "annex", "section"})


def _strip_bcbs_markers(text: str) -> str:
    """Drop footnote markers ("governance structure 11 to establish") — a bare 1-2 digit number
    between a lowercase word and a lowercase word — except after "Principle", "paragraph", etc."""
    def repl(m: re.Match) -> str:
        return m.group(0) if m.group(1).lower() in _BCBS_XREF_WORDS else f"{m.group(1)} "
    text = re.sub(r"\b([A-Za-z]+[,;.]?) \d{1,2} (?=[A-Za-z(])", repl, text)
    return re.sub(r"(?<=[a-z][.;]) \d{1,2}$", "", text)  # marker closing the statement


def parse_bcbs(text: str, framework_id: str) -> list[dict]:
    """Basel Committee principles: the principle *statement* only.

    Each clause runs from "Principle N:" to the first blank line or numbered explanatory
    paragraph ("16. The board…"). BIS documents permit only brief excerpts, so the explanatory
    text is deliberately not stored. Principles must run in sequence (a "Principle 6" cross-
    reference can't start a clause); the short title line just above a principle (e.g.
    "Governance") becomes its heading; footnote markers are removed.
    """
    clauses: list[dict] = []
    current: dict | None = None
    expected = 1
    last_title = ""
    for raw in text.split("\n"):
        line = raw.replace("\f", "")
        stripped = line.strip()
        m = _BCBS_PRINCIPLE_RE.match(line)
        if m and int(m.group(1)) == expected:
            if current:
                clauses.append(current)
            n = m.group(1)
            # No title right above: the principle sits in the previous principle's section.
            heading = last_title or (clauses[-1]["heading"] if clauses else "")
            current = {"clause_id": f"{framework_id}-P{n}", "ref": f"Principle {n}",
                       "heading": heading, "text": m.group(2).strip(), "text_status": "verbatim",
                       "tags": []}
            expected += 1
            continue
        if current is not None:
            if not stripped or re.match(r"^\s*\d{1,3}\.\s", line):
                current["text"] = _strip_bcbs_markers(" ".join(current["text"].split()))
                clauses.append(current)
                current = None
            else:
                current["text"] += " " + stripped
            continue
        if stripped and len(stripped.split()) <= 8 and stripped[0].isupper() and not stripped.endswith((".", ",", ";", ":")):
            last_title = re.sub(r"\s+\d{1,2}$", "", stripped)  # drop a footnote marker on the title
        elif stripped:
            last_title = ""
    if current:
        current["text"] = _strip_bcbs_markers(" ".join(current["text"].split()))
        clauses.append(current)
    return clauses


_EU_ARTICLE_RE = re.compile(r"^\s*Article\s+(\d{1,3}[a-z]?)\s*$")
_EU_STRUCTURE_RE = re.compile(r"^\s*(CHAPTER|TITLE|Section|SECTION)\s+[IVXLC0-9]+\b")
_EU_END_RE = re.compile(r"^\s*This Regulation shall be binding in its entirety", re.IGNORECASE)
_EU_NOISE_RE = re.compile(r"^\s*(L \d+/\d+|EN\s*$|Official Journal of the European Union|\d{1,2}\.\d{1,2}\.\d{4}\s*$)")
_EU_PAGE_HEADER_RE = re.compile(r"Official Journal of the European Union")
# A footnote opens with a citation ("Regulation (EU)…", "OJ L 295…"), never a quoted term:
# definitions read "(34) ‘public authority’ means…".
_EU_FOOTNOTE_START_RE = re.compile(r"^\s*\((\d{1,3})\)\s+(?=[A-Z])")
# An inline footnote marker: "(31)" straight after a word, not at the start of a line.
# After a digit a space is required, so "Article 33(1)" never matches but "May 2021 (30)" does.
_EU_INLINE_REF_RE = re.compile(r"(?:(?<=[A-Za-z.,;:’)\]])\s?|(?<=\d)\s)\((\d{1,3})\)(?=[\s,.;:)]|$)")


_EU_XREF_WORDS = frozenset({"point", "points", "paragraph", "paragraphs", "subparagraph", "subparagraphs",
                            "article", "articles", "and", "or", "to", "of", "in"})


def _is_cross_reference(line: str, start: int) -> bool:
    """True when "(34)" is a cross-reference ("points (34) to (36)"), not a footnote marker."""
    before = line[:start].split()
    return bool(before) and before[-1].lower().strip(",") in _EU_XREF_WORDS


def parse_eu(text: str, framework_id: str) -> list[dict]:
    """EU Official Journal layout (e.g. DORA): one clause per ``Article N``, the line after
    it as the heading. Skips recitals before Article 1, the closing formula, CHAPTER /
    Section lines and all-caps titles, OJ page headers, and footnotes.

    Footnotes are numbered across the whole document, but recitals and definitions also
    start lines with "(1)", "(2)"…, so a line only opens a footnote block when its number is
    the next footnote already *referenced* inline (markers like "Council (31)", accepted
    only in strict sequence). The block runs to the next page header. Inline markers are
    removed from article text.
    """
    clauses: list[dict] = []
    current: dict | None = None
    want_heading = False
    next_ref = 1        # next inline marker expected (strict sequence)
    next_block = 1      # next footnote block expected; must already be referenced
    in_footnote = False
    for raw in text.splitlines():
        line = raw.replace("\f", "")
        stripped = line.strip()
        if not stripped:
            continue
        if _EU_PAGE_HEADER_RE.search(line):
            in_footnote = False
            continue
        fn = _EU_FOOTNOTE_START_RE.match(line)
        if fn and int(fn.group(1)) == next_block and next_block < next_ref:
            in_footnote = True
            next_block += 1
            continue
        if in_footnote:
            continue
        if _NOISE_RE.match(line) or _EU_NOISE_RE.match(line):
            continue
        if _EU_END_RE.match(line):
            break
        # Consume inline markers in sequence (also in recitals, to keep the count right).
        while True:
            m = next((m for m in _EU_INLINE_REF_RE.finditer(line)
                      if int(m.group(1)) == next_ref and not _is_cross_reference(line, m.start())), None)
            if m is None:
                break
            line = line[:m.start()] + line[m.end():]
            next_ref += 1
        stripped = line.strip()
        art = _EU_ARTICLE_RE.match(line)
        if art:
            if current:
                clauses.append(current)
            n = art.group(1)
            current = {"clause_id": f"{framework_id}-art-{n}", "ref": f"Article {n}", "heading": "",
                       "text": "", "text_status": "verbatim", "tags": []}
            want_heading = True
            continue
        if current is None:
            continue  # recitals and preamble
        if _EU_STRUCTURE_RE.match(line) or (stripped.isupper() and len(stripped) < 120):
            continue
        indent = len(line) - len(line.lstrip())
        if want_heading:
            current["heading"] = stripped
            want_heading = False
            continue
        if not current["text"] and indent >= 20:
            current["heading"] += " " + stripped  # headings are centred; a wrapped one continues here
            continue
        sep = "" if current["text"].endswith("-") else " "
        current["text"] = f"{current['text']}{sep}{' '.join(stripped.split())}".strip()
    if current:
        clauses.append(current)
    return [c for c in clauses if c["text"]]


_PRA_PARA_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\s+(\S.*)$")
_PRA_CONTENTS_RE = re.compile(r"^\s*(\d{1,2})\s{2,}([A-Z][^.]{2,120}?)(?:\s{2,}\d{1,3})?\s*$")
_PRA_FOOTNOTE_RE = re.compile(r"^\s*(\d{1,3})\s+\S")
_PRA_END_RE = re.compile(r"^\s*Annex\b")


def _pra_ref_re(n: int) -> re.Pattern:
    """Footnote marker ``n`` glued to a word or punctuation ("Parts,6"), but not the decimal part of
    a number ("Rules 8.6 to", "3.16 for"). After a digit-then-dot it only counts when a new
    sentence or the line end follows ("31 March 2025.19 For a firm's…")."""
    return re.compile(rf"(?:(?<![0-9][.,])(?<=[A-Za-z’'.;,:)\]]){n}(?=\s|$|[.,;:])"
                      rf"|(?<=[0-9]\.){n}(?=\s+[A-Z]|\s*$))")


def parse_pra(text: str, framework_id: str) -> list[dict]:
    """Bank of England / PRA layout (supervisory statements, statements of policy).

    Paragraphs are numbered "chapter.paragraph" (2.1, 2.2 … 3.1) at column 0 and must run in
    sequence. Chapter titles come from the contents table (they are graphics in the body). Footnote
    markers are glued to the preceding word ("Rulebook1", ";3") and are removed in strict sequence;
    a footnote block ("12   text…") is skipped to the next page break, but only once its number
    has been referenced, so a stray number can't swallow body text. Lines are split on "\n" only:
    ``str.splitlines()`` would treat the form feed (page break) that ends a footnote block as a
    line boundary and drop it. Bullet glyphs are removed and
    parsing stops at the trailing "Annex" of document updates.
    """
    # Contents table: everything before paragraph 1.1. Chapter 1 may be listed without its number,
    # and a long title wraps so its first line has no page number.
    chapters: dict[str, str] = {}
    for line in text.split("\n"):
        line = line.replace("\f", "")
        if re.match(r"^1\.1\s", line):
            break
        m = _PRA_CONTENTS_RE.match(line)
        if m and m.group(1) not in chapters:
            chapters[m.group(1)] = " ".join(m.group(2).split())
        elif re.match(r"^\s*Introduction\s{2,}\d{1,3}\s*$", line):
            chapters.setdefault("1", "Introduction")
    clauses: list[dict] = []
    current: dict | None = None
    cur_ch, cur_p = 1, 0
    next_ref = next_block = 1
    in_footnote = False
    started = False
    for raw in text.split("\n"):
        if "\f" in raw:
            in_footnote = False
        line = _PRIVATE_USE_RE.sub(" ", raw).replace("\f", "")
        stripped = line.strip()
        if not stripped:
            continue
        para = _PRA_PARA_RE.match(line)
        if para:
            ch, pn = int(para.group(1)), int(para.group(2))
            if (ch == cur_ch and pn == cur_p + 1) or (ch == cur_ch + 1 and pn == 1 and started):
                started = True
                in_footnote = False
                if current:
                    clauses.append(current)
                cur_ch, cur_p = ch, pn
                body, n = para.group(3), f"{ch}.{pn}"
                while (m := _pra_ref_re(next_ref).search(body)):
                    body = body[:m.start()] + body[m.end():]
                    next_ref += 1
                current = {"clause_id": f"{framework_id}-para-{n}", "ref": f"para {n}",
                           "heading": chapters.get(str(ch), ""), "text": " ".join(body.split()),
                           "text_status": "verbatim", "tags": []}
                continue
        if not started:
            continue
        if _PRA_END_RE.match(line):
            break
        fn = _PRA_FOOTNOTE_RE.match(line)
        if fn and int(fn.group(1)) == next_block and next_block < next_ref and not line[:1].isspace():
            in_footnote = True
            next_block += 1
            continue
        if in_footnote:
            continue
        while (m := _pra_ref_re(next_ref).search(line)):
            line = line[:m.start()] + line[m.end():]
            next_ref += 1
        if current:
            sep = "" if current["text"].endswith("-") else " "
            current["text"] += sep + " ".join(line.split())
    if current:
        clauses.append(current)
    return clauses


_NIST_FUNCTION_RE = re.compile(r"^\s*(GOVERN|IDENTIFY|PROTECT|DETECT|RESPOND|RECOVER) \(([A-Z]{2})\):\s*(.*)$")
_NIST_CATEGORY_RE = re.compile(r"^\s*•\s+(.+?) \(([A-Z]{2}\.[A-Z]{2})\):\s*(.*)$")
_NIST_SUBCATEGORY_RE = re.compile(r"^\s*o\s+([A-Z]{2}\.[A-Z]{2}-\d{2}):\s*(.*)$")
_NIST_FURNITURE_RE = re.compile(r"^\s*(\d{1,3}|NIST CSWP 29\b.*|[A-Z][a-z]+ \d{1,2}, \d{4})\s*$")


def parse_nist(text: str, framework_id: str) -> list[dict]:
    """NIST CSF 2.0 Core: Functions ("GOVERN (GV): …"), Categories ("• Organizational Context
    (GV.OC): …") and Subcategories ("o GV.OC-01: …"), keyed by their official identifiers, with
    page numbers, running headers and dates removed. Only the first occurrence of each Function
    block is read, i.e. the Core itself, not later mentions in tables or appendices."""
    clauses: list[dict] = []
    seen: set[str] = set()
    current: dict | None = None
    function_name = category_name = ""
    in_core = False
    for raw in text.split("\n"):
        line = raw.replace("\f", "")
        if not line.strip() or _NIST_FURNITURE_RE.match(line):
            continue
        fm, cm, sm = _NIST_FUNCTION_RE.match(line), _NIST_CATEGORY_RE.match(line), _NIST_SUBCATEGORY_RE.match(line)
        if fm or cm or sm:
            key = (fm and fm.group(2)) or (cm and cm.group(2)) or sm.group(1)
            if key in seen:
                current = None
                continue
            if fm:
                in_core = True
            if not in_core:
                continue
            if current:
                clauses.append(current)
            seen.add(key)
            if fm:
                function_name = f"{fm.group(1).title()} ({fm.group(2)})"
                current = {"clause_id": f"{framework_id}-{key}", "ref": key, "heading": function_name,
                           "text": fm.group(3).strip(), "text_status": "verbatim", "tags": ["function"]}
            elif cm:
                category_name = f"{cm.group(1).strip()} ({key})"
                current = {"clause_id": f"{framework_id}-{key}", "ref": key, "heading": category_name,
                           "text": cm.group(3).strip(), "text_status": "verbatim", "tags": ["category"]}
            else:
                current = {"clause_id": f"{framework_id}-{key}", "ref": key, "heading": category_name,
                           "text": sm.group(2).strip(), "text_status": "verbatim", "tags": ["subcategory"]}
            continue
        if current is not None:
            # Continuation lines of the Core are indented; prose after the Core is not.
            if not line[:1].isspace() and current["tags"] != ["function"]:
                clauses.append(current)
                current = None
                continue
            current["text"] += " " + " ".join(line.split())
    if current:
        clauses.append(current)
    for c in clauses:
        c["text"] = " ".join(c["text"].split())
    return clauses


_OCC_SECTION_RE = re.compile(r"^\s*(\d)\.\s+([A-Z][A-Za-z ,-]+?)\s*$")
_OCC_ITEM_RE = re.compile(r"^\s*([a-z])\)\s+(\S.*)$")
_OCC_FOOTNOTE_RE = re.compile(r"^\s{0,3}(\d{1,3})\s*$")
_OCC_PAGE_RE = re.compile(r"^\s{12,}\d{1,3}\s*$")


def parse_occ(text: str, framework_id: str) -> list[dict]:
    """US interagency sound-practices paper (OCC 2020-94): numbered sections ("3. Business
    Continuity Management"), each a list of lettered practices ("c) The firm tests ...").

    One clause per practice (``s3-c``); section introductions aren't requirements and are dropped.
    Footnote blocks (a bare sequential number near column 0, running to the centred page number)
    and their inline markers ("risk appetite 8 for") are stripped. Parsing stops at Appendix A,
    whose two-column table pdftotext can't keep grouped by category.
    """
    clauses: list[dict] = []
    current: dict | None = None
    section, heading, letter = 0, "", ""
    next_fn = next_ref = 1
    in_footnote = False
    for raw in text.split("\n"):
        if "\f" in raw:
            in_footnote = False
            raw = raw.replace("\f", "")
        if re.match(r"^\s*Appendix A\s*$", raw):
            break
        if not raw.strip():
            continue
        if _OCC_PAGE_RE.match(raw):
            in_footnote = False
            continue
        fn = _OCC_FOOTNOTE_RE.match(raw)
        if fn and int(fn.group(1)) == next_fn:
            in_footnote, next_fn = True, next_fn + 1
            continue
        if in_footnote:
            continue
        line = raw
        while True:  # markers can cluster on one line; strip them in sequence
            stripped = re.sub(rf"(?<=[^\s\d]) {next_ref}(?=\s|$)", "", line, count=1)
            if stripped == line:
                break
            line, next_ref = stripped, next_ref + 1
        sec = _OCC_SECTION_RE.match(line)
        if sec and int(sec.group(1)) == section + 1:
            if current:
                clauses.append(current)
            current, section, heading, letter = None, section + 1, sec.group(2).strip(), ""
            continue
        item = _OCC_ITEM_RE.match(line)
        expected = chr(ord(letter) + 1) if letter else "a"
        if section and item and item.group(1) == expected:
            if current:
                clauses.append(current)
            letter = expected
            current = {"clause_id": f"{framework_id}-s{section}-{letter}", "ref": f"section {section}({letter})",
                       "heading": heading, "text": " ".join(item.group(2).split()),
                       "text_status": "verbatim", "tags": []}
            continue
        if current:
            sep = "" if current["text"].endswith("-") else " "
            current["text"] += sep + " ".join(line.split())
    if current:
        clauses.append(current)
    return clauses


_FCA_START_RE = re.compile(r"^\s*15A\s+Operational resilience\s*$")
_FCA_END_RE = re.compile(r"^\s*Insert the following new transitional provision")
_FCA_SECTION_RE = re.compile(r"^\s*15A\.(\d{1,2})\s+(\S.*?)\s*$")
_FCA_PROVISION_RE = re.compile(r"^\s*(15A\.\d{1,2}\.\d{1,2})\s+([RG])\s+(\S.*)$")
_FCA_FURNITURE_RE = re.compile(r"^\s*(Page \d+ of \d+|FCA \d{4}/\d+)\s*$")


def parse_fca(text: str, framework_id: str) -> list[dict]:
    """FCA Handbook instrument (e.g. PS21/3's annex inserting SYSC 15A): provisions numbered
    ``15A.2.1  R  text`` under ``15A.2  Section title`` and an optional sub-heading
    ("Impact tolerances"); the most specific of the two becomes the clause heading.

    Only the inserted chapter is read: from its ``15A  Operational resilience`` title to the
    transitional-provisions insert, so the policy statement's feedback chapters (which quote the
    rules) and the amended neighbouring chapters are skipped. ``R`` (rule) vs ``G`` (guidance)
    is kept as a tag, because only rules bind.
    """
    clauses: list[dict] = []
    current: dict | None = None
    heading = ""
    text_col = 0
    started = False
    for line in text.replace("\f", "\n").split("\n"):
        if not started:
            started = bool(_FCA_START_RE.match(line))
            continue
        if _FCA_END_RE.match(line):
            break
        if not line.strip() or _FCA_FURNITURE_RE.match(line):
            continue
        prov = _FCA_PROVISION_RE.match(line)
        if prov:
            if current:
                clauses.append(current)
            num, kind = prov.group(1), prov.group(2)
            text_col = prov.start(3)
            current = {"clause_id": f"{framework_id}-{num}{kind}", "ref": f"SYSC {num}{kind}",
                       "heading": heading, "text": " ".join(prov.group(3).split()),
                       "text_status": "verbatim", "tags": ["rule" if kind == "R" else "guidance"]}
            continue
        sec = _FCA_SECTION_RE.match(line)
        if sec and not re.search(r"\d", sec.group(2)):
            if current:
                clauses.append(current)
            current, heading = None, sec.group(2)
            continue
        if line.strip() == "…":
            continue
        indent = len(line) - len(line.lstrip())
        if current is None and len(line.split()) <= 8:
            heading = " ".join(line.split())  # sub-heading straight after a section title
            continue
        if current and indent < text_col:
            # Left of the provision's text column: a sub-heading ("Impact tolerances"), not a wrap.
            clauses.append(current)
            current, heading = None, " ".join(line.split())
            continue
        if current:
            sep = "" if current["text"].endswith("-") else " "
            current["text"] += sep + " ".join(line.split())
    if current:
        clauses.append(current)
    return clauses


PARSERS = {"apra": parse_apra, "apra-guide": parse_apra_guide, "bcbs": parse_bcbs, "eu": parse_eu, "pra": parse_pra, "nist": parse_nist,
           "occ": parse_occ, "fca": parse_fca}


def _framework_path(framework_id: str, corpus_dir: Path) -> Path:
    for path in corpus_dir.glob("*.json"):
        if json.loads(path.read_text(encoding="utf-8")).get("framework_id") == framework_id:
            return path
    raise SystemExit(f"framework {framework_id!r} not found in {corpus_dir} — add its metadata file first")


def merge_clauses(existing: list[dict], parsed: list[dict]) -> list[dict]:
    """Parsed clauses replace existing ones by ID; existing headings and tags are kept
    when the parse didn't find them (e.g. hand-written BCBS principle headings)."""
    by_id = {c["clause_id"]: c for c in existing}
    merged = []
    for c in parsed:
        old = by_id.pop(c["clause_id"], {})
        merged.append({**c, "heading": c["heading"] or old.get("heading", ""),
                       "tags": c["tags"] or old.get("tags", [])})
    merged.extend(by_id.values())
    return merged


def ingest(framework_id: str, text_path: Path, style: str, *, source_file: Path | None = None,
           licensed: bool = False, corpus_dir: Path = DEFAULT_CORPUS_DIR) -> int:
    path = _framework_path(framework_id, corpus_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("licence") == "proprietary" and not licensed:
        raise SystemExit(f"{framework_id} is a proprietary standard — pass --licensed only if you hold a licence "
                         "that permits storing its text here; otherwise keep summaries.")

    parsed = PARSERS[style](text_path.read_text(encoding="utf-8"), framework_id)
    if not parsed:
        raise SystemExit(f"no clauses parsed from {text_path} with style {style!r}")

    digest_source = source_file if source_file and source_file.exists() else text_path
    data["clauses"] = merge_clauses(data.get("clauses", []), parsed)
    data["ingestion"] = {
        "method": f"pdftotext+{style}",
        # "sha256:" prefix names the algorithm and keeps detect-secrets from reading a bare hex
        # digest as a high-entropy secret (JSON can't carry an allowlist pragma).
        "source_digest": "sha256:" + hashlib.sha256(digest_source.read_bytes()).hexdigest(),
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(parsed)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("framework_id")
    ap.add_argument("text_file", type=Path)
    ap.add_argument("--style", choices=sorted(PARSERS), required=True)
    ap.add_argument("--source-file", type=Path, help="original PDF, hashed for provenance")
    ap.add_argument("--licensed", action="store_true")
    ap.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    args = ap.parse_args(argv)
    n = ingest(args.framework_id, args.text_file, args.style, source_file=args.source_file,
               licensed=args.licensed, corpus_dir=args.corpus_dir)
    closed = change_flags.resolve_framework(args.framework_id, note=f"re-ingested from {args.text_file.name}")
    print(f"ingested {n} clauses into {args.framework_id} — review the diff before committing")
    if closed:
        print(f"closed {closed} open change flag(s) for {args.framework_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
