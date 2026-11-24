"""Shared helpers for the offline intelligence products (disruption report, systemic view, forward watch).

OFFLINE, read-only, default OFF, not wired into any service. Reads JSONL (optionally .gz) exports in the same
shape as the P1-P3 prototypes: event_id, source_name, published_at, collected_at, canonical_url, raw_title,
raw_summary (optional: sector, geography, event_type, organisation).
"""

from __future__ import annotations

import gzip
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ENABLE_ENV = "INTEL_PRODUCTS_ENABLED"


def require_enabled(flag=False):
    """Products are default OFF: pass --enable (or set INTEL_PRODUCTS_ENABLED=1) to run a generator."""
    if flag or os.environ.get(ENABLE_ENV, "0") == "1":
        return True
    print(
        f"Disabled by default. Re-run with --enable (or {ENABLE_ENV}=1). Offline, read-only; reads only the "
        "files given with --input.",
        file=sys.stderr,
    )
    return False


def load_rows(paths):
    rows = []
    for p in paths:
        opener = gzip.open if str(p).endswith(".gz") else open
        with opener(p, "rt", encoding="utf-8") as fh:
            rows.extend(json.loads(line) for line in fh if line.strip())
    return rows


_ENT = re.compile(r"&(?:#(\d+)|#x([0-9a-fA-F]+)|(amp|lt|gt|quot|nbsp|apos));")
_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "nbsp": " ", "apos": "'"}


def clean_text(text):
    """Unescape the HTML entities that appear in feed text (e.g. '&#60;p&#62;' or '&amp;')."""
    if not text:
        return ""

    def rep(m):
        if m.group(1):
            return chr(int(m.group(1)))
        if m.group(2):
            return chr(int(m.group(2), 16))
        return _NAMED[m.group(3)]

    out = _ENT.sub(rep, text)
    out = _ENT.sub(rep, out)  # feeds are sometimes double escaped
    out = re.sub(r"<[^>]+>", " ", out)
    return re.sub(r"\s+", " ", out).strip()


def short(text, n=110):
    text = clean_text(text)
    return text if len(text) <= n else text[: n - 1].rstrip() + "..."


def md_cell(text):
    return str(text).replace("|", "/").replace("\n", " ")


def iso_week(dt):
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"
