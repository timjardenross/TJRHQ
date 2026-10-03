"""Ingest clause text from an official document into a corpus framework file.

Works on plain text so no PDF library is needed — extract first with poppler::

    pdftotext -layout CPS230.pdf /tmp/cps230.txt
    cd platform-runtime
    python -m lib.resilience.ingest APRA-CPS-230 /tmp/cps230.txt --style apra --source-file CPS230.pdf

Styles:
- ``apra``  — numbered paragraphs (``34.  An APRA-regulated entity must ...``); the most
  recent un-numbered heading line is kept as the paragraph's heading.
- ``bcbs``  — ``Principle N:`` blocks.
- ``eu``    — EU regulations (``Article N`` + heading line), e.g. DORA.

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
_MONTH_HEADER_RE = re.compile(
    r"^\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*$")
_FOOTNOTE_NUM_RE = re.compile(r"^\s*(\d{1,2})\s*$")
_PRIVATE_USE_RE = re.compile("[\ue000-\uf8ff\u2022]")


def _strip_footnote_ref(line: str, n: int) -> tuple[str, bool]:
    """Remove the inline marker for footnote ``n`` (``Act. 1``, ``group, 2 it``)."""
    new, count = re.subn(rf"(?<=[A-Za-z.,;:)’])\s+{n}(?=\s|$)", "", line, count=1)
    return new, bool(count)


def parse_apra(text: str, framework_id: str) -> list[dict]:
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
    for raw in text.splitlines():
        line = _PRIVATE_USE_RE.sub(" ", raw).replace("\f", "")
        if not line.strip():
            continue
        if _APRA_FOOTER_RE.match(line):
            in_footnote = False
            continue
        if _MONTH_HEADER_RE.match(line) or re.match(r"^\s*page \d+", line, re.IGNORECASE):
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
        para = _APRA_PARA_RE.match(line)
        if para and int(para.group(1)) == expected:
            if current:
                clauses.append(current)
            n = para.group(1)
            current = {"clause_id": f"{framework_id}-para-{n}", "ref": f"para {n}",
                       "heading": heading, "text": " ".join(para.group(2).split()),
                       "text_status": "verbatim", "tags": []}
            expected += 1
            continue
        head = _HEADING_RE.match(line)
        # Headings sit at column 0; wrapped body lines are indented under their paragraph.
        if (head and not line[:1].isspace() and not line.rstrip().endswith((".", ";", ",", "-"))
                and len(line.split()) <= 10):
            heading = head.group(1).strip()
            continue
        if current:
            # A line ending in "-" wrapped a hyphenated word (APRA-\nregulated): join without a space.
            sep = "" if current["text"].endswith("-") else " "
            current["text"] += sep + " ".join(line.split())
    if current:
        clauses.append(current)
    return clauses


def parse_bcbs(text: str, framework_id: str) -> list[dict]:
    clauses: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if _NOISE_RE.match(line) or not line.strip():
            continue
        m = _BCBS_PRINCIPLE_RE.match(line)
        if m:
            if current:
                clauses.append(current)
            n = m.group(1)
            current = {"clause_id": f"{framework_id}-P{n}", "ref": f"Principle {n}",
                       "heading": "", "text": m.group(2).strip(), "text_status": "verbatim", "tags": []}
            continue
        if current:
            current["text"] += " " + line.strip()
    if current:
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


PARSERS = {"apra": parse_apra, "bcbs": parse_bcbs, "eu": parse_eu}


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
