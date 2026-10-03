"""Ingest clause text from an official document into a corpus framework file.

Works on plain text so no PDF library is needed — extract first with poppler::

    pdftotext -layout CPS230.pdf /tmp/cps230.txt
    cd platform-runtime
    python -m lib.resilience.ingest APRA-CPS-230 /tmp/cps230.txt --style apra --source-file CPS230.pdf

Styles:
- ``apra``  — numbered paragraphs (``34.  An APRA-regulated entity must ...``); the most
  recent un-numbered heading line is kept as the paragraph's heading.
- ``bcbs``  — ``Principle N:`` blocks.

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

from .corpus import DEFAULT_CORPUS_DIR

_APRA_PARA_RE = re.compile(r"^\s*(\d{1,3})\.\s+(\S.*)$")
_BCBS_PRINCIPLE_RE = re.compile(r"^\s*Principle\s+(\d{1,2})\s*[:.]\s*(.*)$", re.I)
_HEADING_RE = re.compile(r"^\s*([A-Z][A-Za-z ,&/'()-]{3,80})\s*$")
_NOISE_RE = re.compile(r"^\s*(\d+\s*$|page \d+|cps \d+ - \d+|\f)", re.I)


def parse_apra(text: str, framework_id: str) -> list[dict]:
    clauses: list[dict] = []
    heading = ""
    current: dict | None = None
    expected = 1
    for line in text.splitlines():
        if _NOISE_RE.match(line) or not line.strip():
            continue
        para = _APRA_PARA_RE.match(line)
        if para and int(para.group(1)) == expected:
            if current:
                clauses.append(current)
            n = para.group(1)
            current = {"clause_id": f"{framework_id}-para-{n}", "ref": f"para {n}",
                       "heading": heading, "text": para.group(2).strip(),
                       "text_status": "verbatim", "tags": []}
            expected += 1
            continue
        head = _HEADING_RE.match(line)
        if head and not line.rstrip().endswith((".", ";", ",")) and len(line.split()) <= 10:
            heading = head.group(1).strip()
            continue
        if current:
            current["text"] += " " + line.strip()
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


PARSERS = {"apra": parse_apra, "bcbs": parse_bcbs}


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
        "source_sha256": hashlib.sha256(digest_source.read_bytes()).hexdigest(),
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
    print(f"ingested {n} clauses into {args.framework_id} — review the diff before committing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
