#!/usr/bin/env python3
"""Docling pre-processor for the knowledge-ingestion pipeline.

USS-TJR-MSN-0366 Stream 3 (Stage 2A: New Open-Source Tool Adoption).

`tools/supabase/ingest_knowledge.py` walks known repo-governance paths
(ADRs, architecture docs, crew/specialist files, ...) and expects
already-plain .md/.txt content — it already has a Docling extraction hook
wired in (see its `_docling_extract` import), but nothing in this repo
ever fed it a PDF/DOCX/HTML file, because `iter_files()` only globs
`.md`/`.txt`. This script is that missing pre-processor: it targets the
real backlog of PDF/Word/HTML documents that currently need manual
extraction before they can enter the knowledge base at all (see GAP 5,
`knowledge/OSS-Gap-Solutions-2026-08-23.md` — "814-document review
backlog... Knowledge pipeline manual"). It runs each document through
Docling (`core/knowledge/docling_processor.py`) for structured-markdown
extraction, chunks the result with the *same* chunker
`ingest_knowledge.py` uses (imported, not reimplemented), and writes into
the *same* `knowledge_documents` / `document_chunks` tables via the *same*
`SupabaseClient` wrapper — reusing this repo's existing chunking and
Supabase plumbing rather than inventing new ones, per MSN-0366's brief.

Must run under the isolated docling venv, NOT platform-runtime/.venv —
`core/knowledge/docling_processor.py`'s docstring and
`core/knowledge/requirements-docling.txt` explain why (torch/transformers
footprint). SupabaseClient itself is pure-stdlib (urllib only), so running
this whole script under the docling venv's interpreter costs nothing
extra:

    platform-runtime/.venv-docling/bin/python3 tools/supabase/docling_ingest.py <path> [<path> ...]

Review gate, and an honest gap: `knowledge_documents`
(core/infrastructure/supabase/migrations/0001_knowledge_prototype.sql) has
no review/status column of its own. The only real pre-approval review
queue in this codebase lives on a different table entirely
(`processing_documents.status`, MSN-0205C) — a separate personal-files
staging area (Mac Collector Agent), not repo/governance knowledge, and not
the table this mission named as the write target.
`ingest_knowledge.py`'s existing rows (ADRs, architecture docs, ...) are
written straight into `knowledge_documents` because they're already-
reviewed, repo-committed governance content — there was never a gate to
reuse. Docling-extracted backlog documents are not that: they're raw
automated extractions of previously-unprocessed files, so this script
marks every row it writes with `metadata.review_status = "pending_review"`
plus a `needs-review` tag (mirroring the `review_decision`/`needs_review`
vocabulary already used on `processing_documents`, migration 0043) rather
than silently landing them with the same implied trust as the governance
corpus. Nothing in the LCARS Knowledge Library UI reads that flag today —
recorded as a real follow-on gap in this mission's knowledge record, not
solved here.
"""

from __future__ import annotations

import argparse
import hashlib
import sys as _sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in _sys.path:
    _sys.path.insert(0, str(_HERE))
from _local_import_supabase import import_sibling

SupabaseClient = import_sibling("supabase_client").SupabaseClient
_ingest_knowledge = import_sibling("ingest_knowledge")
chunks = _ingest_knowledge.chunks
title_for = _ingest_knowledge.title_for

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))
from core.knowledge.docling_processor import extract_document

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".doc", ".html", ".htm", ".pptx", ".xlsx"}


def iter_files(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = (ROOT / value).resolve()
        if not path.exists():
            print(f"  (skip) not found: {value}")
            continue
        if path.is_file():
            found.append(path)
            continue
        for child in sorted(path.rglob("*")):
            if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES:
                found.append(child)
    return list(dict.fromkeys(found))


def source_path_for(path: Path) -> str:
    """Repo-relative when inside ROOT (matches ingest_knowledge.py's
    source_path shape); absolute otherwise (e.g. a sample outside the
    repo tree) so the unique constraint still has something stable."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def tags_for(path: Path) -> list[str]:
    tags = {"docling", "needs-review", "backlog-extraction"}
    fmt = path.suffix.lower().lstrip(".")
    if fmt:
        tags.add(fmt)
    return sorted(tags)


def process_one(client: SupabaseClient | None, path: Path, dry_run: bool) -> dict[str, Any] | None:
    print(f"--- {path.name} ---")
    extracted = extract_document(path)
    if extracted is None:
        print("  docling extraction failed (see log above) — skipped.")
        return None

    content = extracted["text"]
    tables = extracted.get("tables", [])
    doc_meta = extracted.get("metadata", {})
    relative = source_path_for(path)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    chunk_texts = chunks(content)

    print(f"  extracted {len(content)} chars, {len(tables)} table(s)"
          f"{' [layout_fallback: native text-layer PDF pipeline, no ML layout/table model]' if doc_meta.get('layout_fallback') else ''}")
    print(f"  chunked into {len(chunk_texts)} chunk(s) (max 1800 chars, 200 overlap)")

    if dry_run or client is None:
        print("  dry-run: not writing to Supabase.")
        return {
            "source_path": relative,
            "char_count": len(content),
            "table_count": len(tables),
            "chunk_count": len(chunk_texts),
            "layout_fallback": doc_meta.get("layout_fallback", False),
        }

    document_row = {
        "title": title_for(path, content),
        "source_path": relative,
        "document_type": "Unknown",  # backlog extraction, pending human categorisation
        "content": content,
        "metadata": {
            "sha256": digest,
            "bytes": len(content.encode("utf-8")),
            "extractor": "docling",
            "table_count": len(tables),
            "layout_fallback": doc_meta.get("layout_fallback", False),
            "review_status": "pending_review",
            "original_format": path.suffix.lower(),
        },
        "tags": tags_for(path),
    }
    document = client.upsert("knowledge_documents", [document_row], "source_path")[0]

    client.delete("document_chunks", {"document_id": f"eq.{document['id']}"})
    chunk_rows = [
        {
            "document_id": document["id"],
            "chunk_index": index,
            "chunk_text": text,
            "metadata": {
                "source_path": relative,
                "document_type": "Unknown",
                "extractor": "docling",
            },
        }
        for index, text in enumerate(chunk_texts)
    ]
    inserted = client.insert("document_chunks", chunk_rows) if chunk_rows else []
    print(f"  wrote knowledge_documents id={document['id']} + {len(inserted)} document_chunks row(s), "
          f"review_status=pending_review")

    # Best-effort event-bus publish, matching ingest_knowledge.py's own
    # non-blocking contract exactly.
    try:
        from core.platform.event_bus import publish_event
        publish_event(
            "knowledge.document_ingested", domain="knowledge",
            source="docling-ingest", linked_documents=[document["id"]],
            recommended_action=relative,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort event-bus publish; a bus outage must never block a successful ingest
        print(f"[docling_ingest] Failed to publish document_ingested event: {exc}", file=_sys.stderr)

    return {
        "document_id": document["id"],
        "source_path": relative,
        "char_count": len(content),
        "table_count": len(tables),
        "chunk_count": len(inserted),
        "layout_fallback": doc_meta.get("layout_fallback", False),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="File or directory paths to ingest (PDF/DOCX/HTML/PPTX/XLSX).")
    parser.add_argument("--dry-run", action="store_true", help="Extract and chunk only; skip Supabase writes.")
    args = parser.parse_args()

    files = iter_files(args.paths)
    print(f"Discovered {len(files)} candidate backlog file(s).")

    client = None
    if not args.dry_run:
        try:
            client = SupabaseClient()
        except Exception as exc:
            print(f"Supabase not configured ({exc}) — running as dry-run instead.")
            args.dry_run = True

    results = []
    for path in files:
        outcome = process_one(client, path, args.dry_run)
        if outcome is not None:
            results.append(outcome)

    total_chunks = sum(r.get("chunk_count", 0) for r in results)
    total_tables = sum(r.get("table_count", 0) for r in results)
    print(f"\nDone. {len(results)}/{len(files)} document(s) processed, "
          f"{total_chunks} total chunk(s), {total_tables} total table(s) extracted.")


if __name__ == "__main__":
    main()
