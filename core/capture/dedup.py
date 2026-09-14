"""Capture Workbench — cross-item semantic duplicate detection.

captured_items.source_message_id has a unique index (migration 0130) that
catches exact re-delivery of the SAME message from the SAME channel — a
webhook retry, say. It does NOT catch the harder, more common case: the
same idea/link/note captured twice through DIFFERENT channels (forwarded
via a Telegram voice note, then also typed manually into Command Centre
quick-capture; the same link pasted into Slack and, separately, XO).

That matters here specifically because enrichment_worker.py's hybrid
auto-route (MSN-0200-P2B: 'personal' classification -> appended straight
into today's captains_log_entries) and Capture Promotion Bridge
(MSN-0336: mission/decision/research/reference -> a new intelligence_notes
triage row) both act *automatically* on a captured item — a duplicate
capture that slips through unnoticed risks a doubled captains_log entry,
or two separate officer-triage rows for one idea.

This module runs a duplicate check against a rolling window of recent
captured_items (regardless of their processing_status — an already-routed
item from 3 days ago is exactly the kind of thing worth catching), using
SemHash's one-sided deduplicate() (build an index from the existing
window, then check new items against it) — the cross-item shape mirrors
tools/health-osint/health_signal_synthesis.py's clustering, adapted from
"cluster a whole pending batch" to "check one new arrival against recent
history", since captures land one at a time, often days apart.

A match short-circuits enrichment_worker.enrich_item() BEFORE the LLM
classification call (saves the call) and BEFORE any auto-route/promotion
— the item stays visible in the inbox, flagged via duplicate_of_id/
duplicate_similarity (migration 0204), for a human to actually decide.
Never auto-dismissed — same "never let a probable duplicate quietly
trigger an action" posture as this repo's other curation gates
(health_signal_curation.py's ESCALATE default, etc.).

The recent-item index is built once per batch run (see
enrichment_worker.run_batch), from a window query against captured_items
that is NOT filtered to a particular processing_status — a still-pending
item captured moments earlier in the same batch is a real row already,
so it's indexed too, and two duplicates landing in the same 15-minute
batch are still caught against each other, not just against older
history. The one thing this requires guarding against explicitly: an
item can end up comparing against itself (it's a row in its own recent
window) — find_duplicate() skips a same-id match rather than ever
reporting an item as a duplicate of itself.

Environment note: SemHash's default encoder downloads a small Model2Vec
model from Hugging Face Hub on first use — see health_signal_synthesis.py's
own module docstring for the same disclosed sandbox limitation
(build_recent_index/find_duplicate are written directly against SemHash's
real, installed API, verified via its own dataclass source, but the
embedding call itself could not be exercised end-to-end here).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("capture-dedup")

DEFAULT_WINDOW_DAYS = 14
DEFAULT_WINDOW_LIMIT = 200
DEFAULT_THRESHOLD = 0.88


@dataclass
class DuplicateMatch:
    duplicate_of_id: str
    similarity: float
    matched_text: str


def _item_text(item: dict[str, Any]) -> str:
    return (item.get("raw_text") or item.get("title") or "").strip()


def build_recent_index(recent_items: list[dict[str, Any]]) -> Any | None:
    """Builds one reusable SemHash index from `recent_items` — call once
    per batch run, not once per pending item (see module docstring's
    known-limitation note on why that's the right tradeoff here). Returns
    None when there's nothing usable to index, so callers can treat "no
    index" and "index with nothing in it" the same way (skip the check).
    """
    records = [
        {"id": item["id"], "text": _item_text(item)}
        for item in recent_items
        if _item_text(item)
    ]
    if not records:
        return None

    try:
        from semhash import SemHash

        return SemHash.from_records(records=records, columns=["text"])
    except Exception as exc:  # noqa: BLE001 - covers a missing semhash install and any embedding-model-load failure (e.g. Hugging Face Hub unreachable) alike; dedup must degrade to "skipped", never break the enrichment batch it's called from
        log.warning("Could not build duplicate-detection index (dedup skipped for this batch): %s", exc)
        return None


def find_duplicate(
    index: Any | None,
    new_item: dict[str, Any],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> DuplicateMatch | None:
    """Checks `new_item` against `index` (from build_recent_index).
    Returns None when there's no index, no text to check, or no match —
    never raises. Pure aside from the one `index.deduplicate()` call, so
    this is directly unit-testable with a fake index object.
    """
    if index is None:
        return None
    new_text = _item_text(new_item)
    if not new_text:
        return None

    try:
        result = index.deduplicate(
            records=[{"id": new_item["id"], "text": new_text}],
            threshold=threshold,
        )
    except Exception as exc:  # noqa: BLE001 - a dedup-check failure must never block enrichment; already logged
        log.warning("Duplicate check failed for %s (continuing without it): %s", new_item.get("id"), exc)
        return None

    if not result.filtered:
        return None
    match = result.filtered[0]

    # The recent window this index was built from is not filtered by id,
    # so `new_item` itself may be a member of its own comparison set —
    # never report that as a "duplicate of itself".
    real_matches = [
        (record, score) for record, score in match.duplicates
        if record.get("id") != new_item.get("id")
    ]
    if not real_matches:
        return None

    duplicate_record, score = real_matches[0]
    return DuplicateMatch(
        duplicate_of_id=duplicate_record["id"],
        similarity=float(score),
        matched_text=duplicate_record["text"],
    )
