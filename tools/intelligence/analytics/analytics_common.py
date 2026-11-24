"""Shared helpers for the non-production analytics prototypes.

Offline only: every prototype reads a JSONL export of ``intelligence_events``
(joined to ``intelligence_source_registry.source_name``) and never touches the
database, network or any production service.

Required export columns: event_id, source_name, published_at, collected_at,
canonical_url, raw_title, raw_summary (other columns are optional).

Evidence labels (kept verbatim in every report):
    OBSERVED FACT           - counted or read directly from stored rows
    PLAUSIBLE RELATIONSHIP  - pattern consistent with the data, mechanism not shown
    UNVERIFIED HYPOTHESIS   - needs outside evidence; never asserted
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

OBSERVED = "OBSERVED FACT"
PLAUSIBLE = "PLAUSIBLE RELATIONSHIP"
HYPOTHESIS = "UNVERIFIED HYPOTHESIS"

LABEL_LEGEND = (
    f"Labels: [{OBSERVED}] counted/read from stored rows | "
    f"[{PLAUSIBLE}] consistent with the data, mechanism not shown | "
    f"[{HYPOTHESIS}] needs outside evidence. "
    "Coincident trends are never treated as causation; no organisation is asserted "
    "to depend on any provider without evidence."
)


def parse_ts(value):
    """Parse an ISO-ish timestamp string to an aware UTC datetime (or None)."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip().replace(" ", "T", 1)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if len(text) > 3 and text[-3] in "+-" and ":" not in text[-3:]:
        text += ":00"  # '+00' -> '+00:00'
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def windows(as_of, recent_days=30, prior_days=60):
    """Return ((recent_start, as_of), (prior_start, recent_start))."""
    recent_start = as_of - timedelta(days=recent_days)
    prior_start = recent_start - timedelta(days=prior_days)
    return (recent_start, as_of), (prior_start, recent_start)


def in_window(ts, window):
    return ts is not None and window[0] <= ts < window[1]


def group_by(items, keyfn):
    out = defaultdict(list)
    for item in items:
        out[keyfn(item)].append(item)
    return out


def median(values):
    vals = sorted(values)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def pct(num, den):
    return None if not den else round(100.0 * num / den, 1)
