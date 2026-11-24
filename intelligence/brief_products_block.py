"""Morning-brief block for the intelligence products (flag INTEL_PRODUCTS_IN_BRIEF, default OFF, read at call time).

Reads the latest `intelligence_products` rows (or, when the table does not exist or is unreachable, the latest generated product
file `portal-product-records-*.json` in INTEL_PRODUCTS_DIR) and renders at most MAX_LINES lines, ONLY for findings the products
themselves flagged as supported by evidence (`sections.brief_findings`): a provider whose recurring pattern passed the evidence
thresholds and trend rule, a forward-watch item due within 7 days, a systemic link or concentration candidate with named evidence.
Nothing qualifies, nothing is stale, or anything fails: returns [] (no filler, no error text). One coverage line is added only
when there is at least one finding.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

FLAG = "INTEL_PRODUCTS_IN_BRIEF"
MAX_LINES = 4
MAX_AGE_DAYS = 8
ORDER = ("forward_watch", "recurring_provider", "systemic_risk")
LABELS = {
    "forward_watch": "Forward watch",
    "recurring_provider": "Recurring provider",
    "systemic_risk": "Systemic link",
}


def enabled():
    return os.environ.get(FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def _from_table():
    from intelligence.intel_products_job import _get

    return _get(
        "intelligence_products",
        "select=product_key,generated_for,as_of,title,summary,sections,exceptions&order=generated_for.desc&limit=12",
    )


def _from_files():
    d = Path(os.environ.get("INTEL_PRODUCTS_DIR", ""))
    if not os.environ.get("INTEL_PRODUCTS_DIR") or not d.is_dir():
        return []
    files = sorted(d.glob("portal-product-records-*.json"))
    if not files:
        return []
    recs = json.loads(files[-1].read_text(encoding="utf-8"))
    stamp = files[-1].stem.rsplit("-", 3)[-3:]
    gen = "-".join(stamp)
    for r in recs:
        r.setdefault("generated_for", gen)
    return recs


def _latest(rows):
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: str(r.get("generated_for")), reverse=True):
        if r.get("product_key") not in seen:
            seen.add(r.get("product_key"))
            out.append(r)
    return out


def brief_lines(today=None, reader=None):
    """Lines for the morning brief; [] unless the flag is on and a finding qualifies. Never raises."""
    try:
        if not enabled():
            return []
        today = today or datetime.now(timezone.utc).date()
        try:
            rows = (reader or _from_table)()
        except Exception as exc:  # noqa: BLE001 - table missing/unreachable: fall back to generated files
            log.info("intelligence_products unavailable (%s); trying files", exc)
            rows = _from_files()
        products = {r["product_key"]: r for r in _latest(rows or [])}
        findings, notes = [], []
        for key in ORDER:
            p = products.get(key)
            if not p:
                continue
            try:
                gen = date.fromisoformat(str(p["generated_for"])[:10])
            except Exception as exc:  # noqa: BLE001 - unreadable date: treat as stale
                log.debug("unreadable generated_for (%s)", exc)
                continue
            if today - gen > timedelta(days=MAX_AGE_DAYS):
                continue
            sec = p.get("sections") or {}
            for f in (sec.get("brief_findings") or [])[:2]:
                findings.append(f"{LABELS[key]}: {f}")
            if sec.get("brief_findings") and sec.get("coverage_note"):
                notes.append(sec["coverage_note"])
        if not findings:
            return []
        lines = ["INTELLIGENCE PRODUCTS"] + [
            f"- {f}" for f in findings[: MAX_LINES - 1]
        ]
        lines.append(f"Coverage: {notes[0]}")
        return lines[: MAX_LINES + 2] + [""]
    except Exception as exc:  # noqa: BLE001 - additive flag-gated block must never break the brief
        log.warning("Intel products brief block unavailable: %s", exc)
        return []
