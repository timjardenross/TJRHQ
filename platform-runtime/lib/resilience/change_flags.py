"""Regulatory change flags: mark corpus frameworks that may be out of date.

The intelligence pipeline already collects APRA and BIS publications into
``intelligence_events``. This module matches those events against each corpus
framework's ``watch`` rules (``knowledge/regulatory-corpus/*.json``):

    "watch": {"sources": ["APRA"], "patterns": ["\\bCP[SG]\\s*230\\b", ...]}

An event flags a framework when its ``source_name`` starts with one of the
``sources`` *and* its title or summary matches one of the ``patterns``
(case-insensitive). A framework with no ``sources`` is never flagged — there is
no feed for that issuer yet, and ``coverage`` says so.

Flags are append-only JSONL (same shape as ``audit.py``): a ``flag`` record when
a matching event is first seen, and a ``resolution`` record when the Captain
dismisses it or re-ingests the framework. A flag with no resolution is open.
Open flags are surfaced in every crosswalk that touches the framework, as a
validator note and a verification item — they never block a crosswalk.

Path: ``RESILIENCE_CHANGE_FLAGS`` env var, default
``data/resilience-crosswalk/change_flags.jsonl``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .corpus import REPO_ROOT, Corpus, Framework

DEFAULT_FLAGS_PATH = REPO_ROOT / "data" / "resilience-crosswalk" / "change_flags.jsonl"
RESOLUTIONS = {"dismissed", "reingested"}


@dataclass(frozen=True)
class ChangeFlag:
    flag_id: str
    framework_id: str
    title: str
    source_name: str
    url: str
    published_at: str
    flagged_at: str

    def short(self) -> str:
        date = (self.published_at or self.flagged_at)[:10]
        return f"{self.title} ({self.source_name}, {date})"


def flags_path() -> Path:
    override = os.getenv("RESILIENCE_CHANGE_FLAGS")
    return Path(override) if override else DEFAULT_FLAGS_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _compiled(fw: Framework) -> tuple[tuple[str, ...], tuple[re.Pattern, ...]]:
    sources = tuple(s.lower() for s in fw.watch.get("sources", []))
    patterns = tuple(re.compile(p, re.IGNORECASE) for p in fw.watch.get("patterns", []))
    return sources, patterns


def match_event(event: dict, corpus: Corpus) -> list[str]:
    """Framework IDs this intelligence event may affect."""
    source = (event.get("source_name") or "").lower()
    text = " ".join(filter(None, (event.get("raw_title"), event.get("raw_summary"))))
    if not source or not text:
        return []
    hits = []
    for fid, fw in corpus.frameworks.items():
        sources, patterns = _compiled(fw)
        if not sources or not patterns:
            continue
        if any(source.startswith(s) for s in sources) and any(p.search(text) for p in patterns):
            hits.append(fid)
    return hits


def _flag_id(framework_id: str, event: dict) -> str:
    key = event.get("canonical_url") or event.get("event_id") or event.get("raw_title") or ""
    return "cf-" + hashlib.sha256(f"{framework_id}\0{key}".encode()).hexdigest()[:12]


def _published_after_ingestion(event: dict, fw: Framework) -> bool:
    """Skip events older than the framework's last ingestion — that text already reflects them."""
    ingested = (fw.ingestion or {}).get("ingested_at")
    published = event.get("published_at") or event.get("collected_at")
    if not ingested or not published:
        return True
    return str(published) > str(ingested)


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append(records: list[dict], path: Path) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def scan(events: list[dict], corpus: Corpus, path: Path | None = None) -> list[ChangeFlag]:
    """Record a flag for every (framework, event) pair not seen before. Returns the new flags."""
    target = path or flags_path()
    seen = {r["flag_id"] for r in _read(target) if r.get("type") == "flag"}
    new: list[dict] = []
    for event in events:
        for fid in match_event(event, corpus):
            if not _published_after_ingestion(event, corpus.frameworks[fid]):
                continue
            flag_id = _flag_id(fid, event)
            if flag_id in seen:
                continue
            seen.add(flag_id)
            new.append({
                "type": "flag", "flag_id": flag_id, "framework_id": fid,
                "title": (event.get("raw_title") or "")[:300],
                "source_name": event.get("source_name") or "",
                "url": event.get("canonical_url") or "",
                "published_at": str(event.get("published_at") or ""),
                "event_id": event.get("event_id") or "",
                "flagged_at": _now(),
            })
    _append(new, target)
    return [_to_flag(r) for r in new]


def _to_flag(r: dict) -> ChangeFlag:
    return ChangeFlag(flag_id=r["flag_id"], framework_id=r["framework_id"], title=r.get("title", ""),
                      source_name=r.get("source_name", ""), url=r.get("url", ""),
                      published_at=r.get("published_at", ""), flagged_at=r.get("flagged_at", ""))


def open_flags(path: Path | None = None, framework_ids: list[str] | None = None) -> list[ChangeFlag]:
    records = _read(path or flags_path())
    resolved = {r["flag_id"] for r in records if r.get("type") == "resolution"}
    out = [_to_flag(r) for r in records
           if r.get("type") == "flag" and r["flag_id"] not in resolved]
    if framework_ids is not None:
        wanted = set(framework_ids)
        out = [f for f in out if f.framework_id in wanted]
    return out


def resolve(flag_id: str, resolution: str, note: str = "", path: Path | None = None) -> bool:
    """Close an open flag. Returns False if the flag doesn't exist or is already closed."""
    if resolution not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of {sorted(RESOLUTIONS)}")
    target = path or flags_path()
    if flag_id not in {f.flag_id for f in open_flags(target)}:
        return False
    _append([{"type": "resolution", "flag_id": flag_id, "resolution": resolution,
              "note": note, "resolved_at": _now()}], target)
    return True


def resolve_framework(framework_id: str, note: str = "", path: Path | None = None) -> int:
    """Mark every open flag for a framework as re-ingested (call after a fresh ingest)."""
    target = path or flags_path()
    closed = 0
    for f in open_flags(target, [framework_id]):
        closed += resolve(f.flag_id, "reingested", note, target)
    return closed


def unwatched(corpus: Corpus) -> list[str]:
    """Frameworks with no intelligence source watching them."""
    return sorted(fid for fid, fw in corpus.frameworks.items() if not fw.watch.get("sources"))
