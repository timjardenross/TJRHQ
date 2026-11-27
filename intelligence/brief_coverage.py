"""Coverage block for the Morning brief (flag BRIEF_COVERAGE_V1[_MORNING], default OFF).

States what the brief could and could not see, in plain words, so a quiet section is not mistaken for a quiet world. Three things matter:
sources that normally report but sent nothing in the last 24 hours, feeds that have been failing for days (their silence is not good
news), and the official warnings active in the Emergency Alert Hub (official wording, never paraphrased). A status page that is quiet
because nothing is wrong is NOT a gap: only a source that reported regularly in the prior days and then stopped is. Counts are not
shown; the block says "normal" or names the sources. Deterministic and fail-soft: a figure that cannot be loaded says so, never zero.
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

MASTER_FLAG = "BRIEF_COVERAGE_V1"
MORNING_FLAG = "BRIEF_COVERAGE_V1_MORNING"
_TRUE = ("1", "true", "yes", "on")
PAGE_SIZE = 1000
MAX_PAGES = 8
MAX_NAMED = 6
BASELINE_DAYS = 6                  # the days before the last 24 hours
NORMALLY_ACTIVE_MIN = 5            # reports in the baseline for a source to count as 'normally reports'
THIN_RATIO = 0.5                   # today below this share of a normal day is 'thin'
FAILING_DAYS = 3
FAILING_MIN_CHECKS = 3             # a feed is failing only if it has been checked at least this often and every check was bad
MIN_BASELINE_EVENTS = 6            # fewer baseline reports than this (from resilience sources) is too little history to judge a day
MIN_BASELINE_SOURCES = 2           # ... and so is fewer than this many sources reporting in the baseline
MIN_HEALTH_SHARE = 0.5             # feed health is 'incomplete' if fewer than this share of active resilience sources have enough checks
_BAD_STATUS = frozenset({"failed", "degraded", "stale"})
# registry categories that are not part of the resilience picture: a quiet or failing wellness feed is not a coverage gap
NOT_RESILIENCE_CATEGORIES = frozenset({"wellness", "thought_leadership"})

# Official severity wording, most severe first (matches intelligence/brief/external_domains.py)
_SEVERITY_ORDER = (("emergency_warning", "Emergency Warning"), ("watch_and_act", "Watch and Act"), ("advice", "Advice"), ("unknown", "Unknown"))
_KNOWN_SEVERITIES = frozenset(k for k, _ in _SEVERITY_ORDER)


def enabled() -> bool:
    def on(name):
        return os.getenv(name, "").strip().lower() in _TRUE
    return on(MASTER_FLAG) or on(MORNING_FLAG)


def _paged(sb_get, table: str, query: str, select: str) -> list[dict]:
    """All rows across pages. A loader failure or an empty table both come back empty; callers treat that as 'could not load'."""
    out: list[dict] = []
    for page in range(MAX_PAGES):
        rows = sb_get(table, f"{query}&limit={PAGE_SIZE}&offset={page * PAGE_SIZE}&select={select}")
        out += rows or []
        if not rows or len(rows) < PAGE_SIZE:
            break
    return out


def _names(names: list[str]) -> str:
    names = sorted(names)
    extra = len(names) - MAX_NAMED
    return ", ".join(names[:MAX_NAMED]) + (f" and {extra} more" if extra > 0 else "")


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value) -> datetime | None:
    text = str(value or "").strip().replace(" ", "T").replace("Z", "+00:00")
    if len(text) > 3 and text[-3] in "+-" and text[-2:].isdigit() and ":" not in text[-6:]:
        text += ":00"
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def collection_lines(sb_get, now: datetime) -> list[str]:
    try:
        registry = sb_get("intelligence_source_registry", "active=eq.true&select=source_id,source_name,category&limit=1000")
        events = _paged(sb_get, "intelligence_events",
                        f"collected_at=gte.{_stamp(now - timedelta(days=BASELINE_DAYS + 1))}&suppressed=eq.false&order=collected_at.desc",
                        "source_id,collected_at")
        truncated = len(events) >= MAX_PAGES * PAGE_SIZE
        if not registry or not events:
            return ["- Collection: could not be checked, so do not read the sections below as quiet."]
        names = {str(r["source_id"]): r["source_name"] for r in registry if (r.get("category") or "") not in NOT_RESILIENCE_CATEGORIES}
        cut = now - timedelta(hours=24)
        today, base = Counter(), Counter()
        for e in events:
            when = _parse(e.get("collected_at"))
            if when is None:
                continue
            (today if when > cut else base)[str(e.get("source_id"))] += 1
        health = _failing_sources(sb_get, now, names)
        failing, health_complete = health if health is not None else (None, True)
        quiet = [names[sid] for sid, n in base.items() if sid in names and n >= NORMALLY_ACTIVE_MIN and today[sid] == 0
                 and names[sid] not in (failing or [])]
        base_r = {sid: n for sid, n in base.items() if sid in names}
        enough_history = sum(base_r.values()) >= MIN_BASELINE_EVENTS and len(base_r) >= MIN_BASELINE_SOURCES
        normal_day = sum(base.values()) / float(BASELINE_DAYS)
        thin = enough_history and sum(today.values()) < THIN_RATIO * normal_day
        out = []
        if not enough_history:
            out.append("- Not enough collection history to judge today.")
            quiet = []
        if truncated:
            out.append("- Collection counts may be incomplete.")
        if not health_complete:
            out.append("- Feed health data is incomplete, so failing feeds may be missing here.")
        if thin:
            out.append("- Collection is thin today: well below a normal day, so quiet sections may just be missing reports.")
        if quiet:
            out.append(f"- Normally active but quiet in the last 24 hours: {_names(quiet)}.")
        if failing:
            out.append(f"- Feeds failing for days (their silence is not good news): {_names(failing)}.")
        if failing is None:
            out.append("- Feed health could not be checked.")
        if not out:
            out.append("- Collection is normal today across your sources.")
        return out
    except Exception:
        log.warning("coverage collection lines unavailable", exc_info=True)
        return ["- Collection: could not be checked, so do not read the sections below as quiet."]


def _failing_sources(sb_get, now: datetime, names: dict[str, str]) -> tuple[list[str], bool] | None:
    """(names of active sources whose every recent check was bad, whether enough sources were checked to trust the answer);
    None when the health table could not be read."""
    try:
        rows = _paged(sb_get, "intelligence_source_health", f"checked_at=gte.{_stamp(now - timedelta(days=FAILING_DAYS))}", "source_id,status,content_valid")
    except Exception:
        log.warning("coverage health read failed", exc_info=True)
        return None
    if not rows:
        return None
    checks, bad = Counter(), Counter()
    for r in rows:
        sid = str(r.get("source_id"))
        checks[sid] += 1
        bad[sid] += (r.get("status") or "").lower() in _BAD_STATUS or r.get("content_valid") is False
    checked = sum(1 for sid in names if checks[sid] >= FAILING_MIN_CHECKS)
    complete = bool(names) and checked >= MIN_HEALTH_SHARE * len(names)
    return [names[sid] for sid in checks if sid in names and checks[sid] >= FAILING_MIN_CHECKS and bad[sid] == checks[sid]], complete


def warnings_line(load_alerts) -> str:
    """Active official warnings in plain words. `load_alerts` raises on failure (store.load_active_emergency_alerts does)."""
    try:
        alerts = load_alerts(limit=500)
    except Exception:
        log.warning("coverage warnings line unavailable", exc_info=True)
        return "- Official warnings: could not be read from the Emergency Alert Hub; absence here is not an all-clear."
    if not alerts:
        return "- Official warnings: none active."
    by_sev: dict[str, set] = {}
    for a in alerts:
        sev = (a.get("severity") or "unknown").strip().lower()
        by_sev.setdefault(sev if sev in _KNOWN_SEVERITIES else "unknown", set()).add(a.get("jurisdiction"))
    states = sorted({a.get("jurisdiction") for a in alerts if a.get("jurisdiction")})
    top, label = next(((k, lbl) for k, lbl in _SEVERITY_ORDER if k in by_sev and k != "unknown"), (None, None))
    where = f" in {', '.join(states)}" if states else ""
    if top is None:
        return f"- Official warnings are active{where}, none with a stated severity."
    top_states = sorted(s for s in by_sev[top] if s)
    most = f"Most serious: {label}" + (f" ({', '.join(top_states)})" if top_states else "") + "."
    tail = " Some have no stated severity." if "unknown" in by_sev else ""
    return f"- Official warnings are active{where}. {most}{tail}"


CALIBRATION_STALE_HOURS = 25   # nightly at 05:00, so by the 07:00 brief a row from the night before (26 h) was not redone
_CALIBRATION_FAILED = frozenset({"bootstrap_default_llm_unavailable", "bootstrap_default_after_llm_reject"})


def calibration_lines(sb_get, now: datetime) -> list[str]:
    """One line when outage-report calibration is degraded for a monitored (active Downdetector) service, else [].
    A service still collecting its first weeks of history is not degraded."""
    unreadable = ["- Outage report detection: calibration state could not be checked."]
    try:
        # Inactive rows are asked for too: the brief's reader turns a failed read into [], so an empty answer must mean
        # "could not look", not "nothing monitored".
        registered = sb_get("intelligence_source_registry", "source_type=eq.downdetector&select=source_name,active&limit=200")
        if not registered:
            return unreadable
        names = {r["source_name"] for r in registered
                 if r.get("active", True) and str(r.get("source_name") or "").lower().startswith("downdetector au")}
        if not names:
            return []
        rows = sb_get("downdetector_learned_thresholds", "select=source_name,threshold_source,computed_at&limit=200")
        if not rows:
            return unreadable
        retained = generic = 0
        for row in rows:
            if row.get("source_name") not in names:
                continue
            source = row.get("threshold_source")
            if source in _CALIBRATION_FAILED:
                generic += 1
            elif source == "llm_learned":
                when = _parse(row.get("computed_at"))
                retained += when is None or now - when > timedelta(hours=CALIBRATION_STALE_HOURS)
        if not retained + generic:
            return []
        parts = ([f"{retained} on an earlier retained level"] if retained else []) + (
            [f"{generic} on the generic level"] if generic else [])
        line = (f"- Outage report detection: calibration degraded for {retained + generic} of {len(names)} "
                f"monitored services ({', '.join(parts)}).")
        return [line]
    except Exception:
        log.warning("coverage calibration line unavailable", exc_info=True)
        return unreadable


def coverage_lines(sb_get, load_alerts, now: datetime | None = None) -> list[str]:
    """The block as plain text lines, or [] when the flag is off. Never raises."""
    if not enabled():
        return []
    try:
        now = now or datetime.now(timezone.utc)
        return ["COVERAGE (what this brief could see)", *collection_lines(sb_get, now), *calibration_lines(sb_get, now),
                warnings_line(load_alerts)]
    except Exception:
        log.warning("coverage block unavailable", exc_info=True)
        return ["COVERAGE", "- Could not be checked, so do not read the sections below as quiet."]
