#!/usr/bin/env python3
"""Load USS TJR markdown/text knowledge files into Supabase."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys as _sys
from pathlib import Path
from typing import Iterable

if str(Path(__file__).resolve().parent) not in _sys.path:
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
from _local_import_supabase import import_sibling

SupabaseClient = import_sibling("supabase_client").SupabaseClient


ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".md", ".txt"}
DEFAULT_PATHS = [
    "core/governance/architecture-decision-records",
    "knowledge/Architectural-Decisions.md",
    "knowledge/architecture",
    "core/architecture",
    "specialists",
    "core/crew",
]


def iter_files(paths: Iterable[str]) -> Iterable[Path]:
    for value in paths:
        path = (ROOT / value).resolve()
        if not path.exists():
            continue
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            yield path
            continue
        for child in sorted(path.rglob("*")):
            if child.is_file() and child.suffix in TEXT_SUFFIXES:
                yield child


def document_type(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    name = path.name.lower()
    if "architecture-decision-records" in relative or name.startswith("adr-"):
        return "ADR"
    if relative == "knowledge/Architectural-Decisions.md":
        return "ADR"
    if "/architecture/" in f"/{relative}" or relative.startswith("core/architecture"):
        return "Architecture"
    if relative.startswith("specialists/") or relative.startswith("core/crew"):
        return "Crew"
    if relative.startswith("Missions/") or relative.startswith("missions/"):
        return "Mission"
    if "capabilit" in relative.lower():
        return "Capability"
    if relative.startswith("knowledge/"):
        return "Knowledge Base"
    return "Unknown"


def title_for(path: Path, content: str) -> str:
    match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return path.stem.replace("-", " ").replace("_", " ").strip()


def tags_for(path: Path, doc_type: str, content: str) -> list[str]:
    tags = {doc_type.lower().replace(" ", "-")}
    relative = path.relative_to(ROOT).as_posix().lower()
    for token in ["supabase", "command", "specialist", "mission", "knowledge", "architecture"]:
        if token in relative or token in content.lower():
            tags.add(token)
    return sorted(tags)


def chunks(content: str, max_chars: int = 1800, overlap: int = 200) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
    result: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            result.append(current)
        if len(paragraph) <= max_chars:
            current = paragraph
        else:
            for start in range(0, len(paragraph), max_chars - overlap):
                result.append(paragraph[start : start + max_chars])
            current = ""
    if current:
        result.append(current)
    return result or [content[:max_chars]]


def load_specialists(client: SupabaseClient) -> None:
    defaults = [
        ("Chief of Staff", "Chief of Staff", ["Mission", "Crew", "Knowledge Base"], ["ADR"]),
        ("Chief Engineer", "Chief Engineer", ["ADR", "Architecture", "Capability", "Knowledge Base"], []),
        ("UX Designer", "UX Designer", ["Architecture", "Crew", "Knowledge Base"], ["ADR"]),
        ("Knowledge Manager", "Knowledge Manager", ["ADR", "Architecture", "Crew", "Mission", "Capability", "Knowledge Base"], []),
        ("Code Review Specialist", "Code Review Specialist", ["ADR", "Architecture", "Capability"], ["Crew"]),
    ]
    specialists = client.upsert(
        "specialists",
        [
            {"name": name, "role": role, "metadata": {"source": "USS-TJR-MSN-0004 seed"}, "tags": ["prototype"]}
            for name, role, _, _ in defaults
        ],
        "role",
    )
    by_role = {row["role"]: row["id"] for row in specialists}
    permissions = []
    for _, role, allowed, restricted in defaults:
        permissions.append(
            {
                "specialist_id": by_role[role],
                "allowed_document_types": allowed,
                "restricted_document_types": restricted,
                "metadata": {"model": "prototype"},
            }
        )
    client.upsert("specialist_permissions", permissions, "specialist_id")


def ingest(paths: list[str], dry_run: bool) -> None:
    files = list(dict.fromkeys(iter_files(paths)))
    print(f"Discovered {len(files)} candidate knowledge files.")
    if dry_run:
        counts: dict[str, int] = {}
        for path in files:
            doc_type = document_type(path)
            counts[doc_type] = counts.get(doc_type, 0) + 1
        print(f"Dry run document type counts: {counts}")
        return

    client = SupabaseClient()
    load_specialists(client)
    for path in files:
        content = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(ROOT).as_posix()
        doc_type = document_type(path)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        document = client.upsert(
            "knowledge_documents",
            [
                {
                    "title": title_for(path, content),
                    "source_path": relative,
                    "document_type": doc_type,
                    "content": content,
                    "metadata": {"sha256": digest, "bytes": len(content.encode("utf-8"))},
                    "tags": tags_for(path, doc_type, content),
                }
            ],
            "source_path",
        )[0]
        client.delete("document_chunks", {"document_id": f"eq.{document['id']}"})
        chunk_rows = [
            {
                "document_id": document["id"],
                "chunk_index": index,
                "chunk_text": text,
                "metadata": {"source_path": relative, "document_type": doc_type},
            }
            for index, text in enumerate(chunks(content))
        ]
        client.insert("document_chunks", chunk_rows)
        print(f"Loaded {relative} as {doc_type} with {len(chunk_rows)} chunks.")

        # MSN-0329 Phase 4: canonical Captain Brief pipeline event — the
        # Knowledge domain's one real choke point (every ingested/updated
        # document funnels through this upsert). Non-blocking, matches
        # publish_event()'s own contract.
        try:
            import sys as _sys
            from pathlib import Path as _Path
            _repo_root = _Path(__file__).resolve().parents[2]
            if str(_repo_root) not in _sys.path:
                _sys.path.insert(0, str(_repo_root))
            from core.platform.event_bus import publish_event
            publish_event(
                "knowledge.document_ingested", domain="knowledge",
                source="ingest-knowledge", linked_documents=[document["id"]],
                recommended_action=relative,
            )
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", dest="paths", help="Repo path to ingest. Can be repeated.")
    parser.add_argument("--dry-run", action="store_true", help="Discover files without writing to Supabase.")
    args = parser.parse_args()
    ingest(args.paths or DEFAULT_PATHS, args.dry_run)


if __name__ == "__main__":
    main()
