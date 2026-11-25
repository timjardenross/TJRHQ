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

from intelligence import product_history as ph
from intelligence.reporting_time import age_hours, format_as_of, reporting_date

log = logging.getLogger(__name__)

FLAG = "INTEL_PRODUCTS_IN_BRIEF"
APPEND_FLAG = "INTEL_PRODUCTS_APPEND_V1"   # history-aware reading: current view, freshness states, dated lines (default OFF)
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


def append_enabled():
    return os.environ.get(APPEND_FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def _from_current_view():
    from intelligence.intel_products_job import _get

    return _get(
        "intelligence_products_current",
        "select=product_key,cadence,generated_for,reporting_date,as_of,last_refresh_as_of,last_failed_as_of,"
        "title,summary,sections,exceptions&limit=30",
    )


def _from_table():
    from intelligence.intel_products_job import _get

    return _get(
        "intelligence_products",
        # newest generation first, deep enough that a day with several stored generations cannot crowd a product out
        "select=product_key,generated_for,as_of,title,summary,sections,exceptions&order=as_of.desc&limit=60",
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
    # Newest generation first (as_of, then the date key): several stored generations per day exist after the append-only migration;
    # with one row per day this is the same order as before.
    for r in sorted(rows, key=lambda r: (str(r.get("as_of")), str(r.get("generated_for"))), reverse=True):
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


def _parse_ts(v):
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else None
    except Exception:  # noqa: BLE001 - unreadable timestamp: treated as unavailable by the caller
        return None


def _cadence_rows(rows):
    """{product_key: {cadence: row}}: the view yields one row per (product, cadence); keep the most recently refreshed if repeated."""
    out: dict[str, dict[str, dict]] = {}
    for r in rows or []:
        if not isinstance(r, dict) or not r.get("product_key"):
            continue
        r["_ts"] = _parse_ts(r.get("last_refresh_as_of") or r.get("as_of"))
        r["_failed"] = _parse_ts(r.get("last_failed_as_of")) if r.get("last_failed_as_of") else None
        cad = r.get("cadence") if r.get("cadence") in ("daily", "weekly") else "unknown"
        cur = out.setdefault(r["product_key"], {}).get(cad)
        if cur is None or (r["_ts"] is not None and (cur["_ts"] is None or r["_ts"] > cur["_ts"])):
            out[r["product_key"]][cad] = r
    return out


_USABLE = (ph.Freshness.CURRENT, ph.Freshness.REFRESH_OVERDUE)


def _select(rows, now):
    """Explicit choice per product between its daily, weekly and unknown-cadence rows.

    primary: the row findings come from. Among rows whose freshness is usable (Current / Refresh overdue) the most recently
    refreshed; a scheduled cadence beats 'unknown' on a tie. If none is usable, the most recently refreshed row (its state is then
    reported as a status line).
    extras: other SCHEDULED rows (daily/weekly) that are Stale or Refresh overdue. They are reported too: a current daily row must
    not hide a weekly assessment that stopped refreshing. The legacy 'unknown' row is never an extra.
    Returns ({key: (row, FreshnessResult)}, [(key, row, FreshnessResult)]).
    """
    primary, extras = {}, []
    for key, by_cad in _cadence_rows(rows).items():
        scored = [(r, ph.freshness(now, cad, r["_ts"], r["_failed"]) if r["_ts"] is not None
                   else ph.freshness(now, cad, None, r["_failed"])) for cad, r in by_cad.items()]

        def rank(x):
            r, fr = x
            ts = r["_ts"].timestamp() if r["_ts"] is not None else float("-inf")
            return (fr.state in _USABLE, ts, (r.get("cadence") in ("daily", "weekly")))

        best = max(scored, key=rank)
        primary[key] = best
        for r, fr in scored:
            if r is not best[0] and r.get("cadence") in ("daily", "weekly") and fr.state in (ph.Freshness.STALE, ph.Freshness.REFRESH_OVERDUE, ph.Freshness.UNAVAILABLE):
                extras.append((key, r, fr))
    return primary, extras


def _pick_current(rows):
    """Compatibility wrapper: one row per product, the most recently refreshed (no freshness ranking)."""
    best = {}
    for key, by_cad in _cadence_rows(rows).items():
        best[key] = max(by_cad.values(), key=lambda r: r["_ts"].timestamp() if r["_ts"] is not None else float("-inf"))
    return best


def _age_label(h):
    return "<1 h old" if h < 1 else f"{h:.0f} h old"


def _brief_lines_with_history(now, reader):
    """History-aware variant (INTEL_PRODUCTS_APPEND_V1): freshness states, as-of date and age on every line.

    Current: findings shown with the as-of date and age. Refresh overdue: findings shown, labelled. Stale / Unavailable: no
    findings, one status line so a missing assessment is never mistaken for a quiet one.
    """
    try:
        rows = (reader or _from_current_view)()
    except Exception as exc:  # noqa: BLE001 - view missing/unreachable: generated files, else an explicit status line
        log.info("intelligence_products_current unavailable (%s); trying files", exc)
        try:
            rows = _from_files()
        except Exception as exc2:  # noqa: BLE001
            log.info("product files unreadable (%s)", exc2)
            rows = []
        if not rows:
            return ["INTELLIGENCE PRODUCTS", "- Status: Unavailable (stored products could not be read)", ""]
    products, extras = _select(rows, now)
    if not products:
        return []
    today = reporting_date(now)
    findings, notes, status = [], [], []
    for key in ORDER:
        entry = products.get(key)
        if entry is None:
            status.append(f"{LABELS[key]}: Unavailable (no stored assessment)")
            continue
        p, fr = entry
        if fr.state in (ph.Freshness.UNAVAILABLE, ph.Freshness.STALE):
            when = f", last assessed {format_as_of(p['_ts'])}, {_age_label(age_hours(p['_ts'], now))}" if p["_ts"] else ""
            status.append(f"{LABELS[key]}: {fr.state.value}{when}")
            continue
        tag = f"as of {format_as_of(p['_ts'])}, {_age_label(fr.age_hours)}"
        if fr.state is ph.Freshness.REFRESH_OVERDUE:
            why = f"LAST REFRESH FAILED {format_as_of(p['_failed'])}" if fr.failed_since_success and p.get("_failed") else "REFRESH OVERDUE"
            tag = f"{why}, {tag}"
        live = _live_findings(key, p, today)
        for f in live[:2]:
            findings.append(f"{LABELS[key]} [{tag}]: {f}")
        sec = p.get("sections") or {}
        if live and sec.get("coverage_note"):
            notes.append(sec["coverage_note"])
    for key, p, fr in extras:
        when = f", last assessed {format_as_of(p['_ts'])}, {_age_label(age_hours(p['_ts'], now))}" if p.get("_ts") else ""
        failed = f" (last refresh attempt failed {format_as_of(p['_failed'])})" if fr.failed_since_success and p.get("_failed") else ""
        status.append(f"{LABELS[key]} ({p.get('cadence')}): {fr.state.value}{when}{failed}")
    if not findings and not status:
        return []
    lines = ["INTELLIGENCE PRODUCTS"] + [f"- {f}" for f in findings[:MAX_LINES]]
    lines += [f"- Status: {s}" for s in status]
    if notes:
        lines.append("Coverage: " + " ".join(dict.fromkeys(notes)))
    return lines + [""]


def brief_lines(today=None, reader=None, now=None):
    """Lines for the morning brief; [] unless the flag is on and a finding qualifies. Never raises."""
    try:
        if not enabled():
            return []
        if append_enabled():
            return _brief_lines_with_history(now or datetime.now(timezone.utc), reader)
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
