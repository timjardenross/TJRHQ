"""Regulatory corpus loader for the Operational Resilience Advisor (crosswalk mode).

The corpus is one JSON file per framework under ``knowledge/regulatory-corpus/``.
Each file carries framework metadata plus a list of clauses with stable IDs.
Clause text is only ever filled from a primary source by ``lib.resilience.ingest``;
``text_status`` records how much we actually hold:

- ``verbatim``      — text extracted from the official document
- ``summary``       — our own summary (e.g. paid ISO standards)
- ``heading_only``  — clause number + heading, no text yet

The validator uses ``text_status`` to cap confidence: a mapping can only be HIGH
when the cited clause's text is held verbatim.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORPUS_DIR = REPO_ROOT / "knowledge" / "regulatory-corpus"

TEXT_STATUSES = {"verbatim", "summary", "heading_only"}


@dataclass(frozen=True)
class Clause:
    clause_id: str
    framework_id: str
    ref: str
    heading: str
    text: str
    text_status: str
    tags: tuple[str, ...] = ()

    def label(self) -> str:
        return f"{self.ref} — {self.heading}" if self.heading else self.ref


@dataclass
class Framework:
    framework_id: str
    title: str
    issuer: str
    jurisdiction: str
    role: str
    status: str
    effective_date: str
    source_url: str
    licence: str
    notes: str = ""
    ingestion: dict = field(default_factory=dict)
    clauses: list[Clause] = field(default_factory=list)


@dataclass
class Corpus:
    frameworks: dict[str, Framework]
    clauses: dict[str, Clause]
    fingerprint: str

    def framework(self, framework_id: str) -> Framework | None:
        return self.frameworks.get(framework_id)

    def clause(self, clause_id: str) -> Clause | None:
        return self.clauses.get(clause_id)

    def coverage(self) -> dict[str, dict[str, int]]:
        """Per-framework count of clauses by text_status — what the agent can really cite."""
        out: dict[str, dict[str, int]] = {}
        for fid, fw in self.frameworks.items():
            counts = dict.fromkeys(sorted(TEXT_STATUSES), 0)
            for c in fw.clauses:
                counts[c.text_status] += 1
            out[fid] = counts
        return out


def _parse_framework(data: dict, source: Path) -> Framework:
    fid = data["framework_id"]
    clauses: list[Clause] = []
    for raw in data.get("clauses", []):
        status = raw.get("text_status", "heading_only")
        if status not in TEXT_STATUSES:
            raise ValueError(f"{source.name}: clause {raw.get('clause_id')} has unknown text_status {status!r}")
        if status == "verbatim" and not raw.get("text"):
            raise ValueError(f"{source.name}: clause {raw['clause_id']} is marked verbatim but has no text")
        clauses.append(Clause(
            clause_id=raw["clause_id"],
            framework_id=fid,
            ref=raw.get("ref", raw["clause_id"]),
            heading=raw.get("heading", ""),
            text=raw.get("text", ""),
            text_status=status,
            tags=tuple(raw.get("tags", [])),
        ))
    return Framework(
        framework_id=fid,
        title=data["title"],
        issuer=data.get("issuer", ""),
        jurisdiction=data.get("jurisdiction", ""),
        role=data.get("role", "comparative"),
        status=data.get("status", "in_force"),
        effective_date=data.get("effective_date", ""),
        source_url=data.get("source_url", ""),
        licence=data.get("licence", ""),
        notes=data.get("notes", ""),
        ingestion=data.get("ingestion", {}),
        clauses=clauses,
    )


def load_corpus(corpus_dir: Path | str | None = None) -> Corpus:
    """Load every ``*.json`` framework file. Raises on duplicate framework or clause IDs."""
    directory = Path(corpus_dir) if corpus_dir else DEFAULT_CORPUS_DIR
    frameworks: dict[str, Framework] = {}
    clauses: dict[str, Clause] = {}
    digest = hashlib.sha256()

    for path in sorted(directory.glob("*.json")):
        raw_bytes = path.read_bytes()
        digest.update(path.name.encode() + b"\0" + raw_bytes)
        fw = _parse_framework(json.loads(raw_bytes), path)
        if fw.framework_id in frameworks:
            raise ValueError(f"duplicate framework_id {fw.framework_id!r} in {path.name}")
        frameworks[fw.framework_id] = fw
        for c in fw.clauses:
            if c.clause_id in clauses:
                raise ValueError(f"duplicate clause_id {c.clause_id!r} in {path.name}")
            clauses[c.clause_id] = c

    if not frameworks:
        log.warning("[resilience.corpus] no framework files found in %s", directory)
    return Corpus(frameworks=frameworks, clauses=clauses, fingerprint=digest.hexdigest()[:16])
