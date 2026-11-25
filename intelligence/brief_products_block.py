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
MAX_AGE_DAYS = 2   # products refresh daily at 06:20; a finding from a product older than this is omitted rather than shown stale
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


def _live_findings(key, product, today):
    """brief_findings with passed forward-watch deadlines removed.

    Weekly generation replays `brief_findings` for up to MAX_AGE_DAYS, so a forward-watch finding whose exception
    `due_date` is before `today` would otherwise keep claiming 'due within 7 days'. Findings are matched to their
    exception by the text the generator builds (`title (detail)`); findings with no dated exception are kept.
    """
    findings = list((product.get("sections") or {}).get("brief_findings") or [])
    if key != "forward_watch":
        return findings
    expired = set()
    for e in product.get("exceptions") or []:
        try:
            due = date.fromisoformat(str(e.get("due_date"))[:10])
        except Exception as exc:  # noqa: BLE001 - undated or unreadable: never expires
            log.debug("forward_watch exception without readable due_date (%s)", exc)
            continue
        if due < today:
            expired.add(f"{e.get('title')} ({e.get('detail')})")
    return [f for f in findings if f not in expired]


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
        products = {
            r["product_key"]: r
            for r in _latest([r for r in rows or [] if isinstance(r, dict) and r.get("product_key")])
        }
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
            live = _live_findings(key, p, today)
            for f in live[:2]:
                findings.append(f"{LABELS[key]}: {f}")
            if live and sec.get("coverage_note"):
                notes.append(sec["coverage_note"])
        if not findings:
            return []
        lines = ["INTELLIGENCE PRODUCTS"] + [
            f"- {f}" for f in findings[: MAX_LINES - 1]
        ]
        # One caveat per contributing product: a finding from product B must not borrow product A's coverage statement.
        lines.append("Coverage: " + " ".join(dict.fromkeys(notes)))
        return lines[: MAX_LINES + 2] + [""]
    except Exception as exc:  # noqa: BLE001 - additive flag-gated block must never break the brief
        log.warning("Intel products brief block unavailable: %s", exc)
        return []
