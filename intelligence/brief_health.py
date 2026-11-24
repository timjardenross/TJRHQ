"""Health lane for the Morning brief (flag BRIEF_HEALTH_V1[_MORNING], default OFF).

The V1 brief carried no health content: it only read already-triaged signals, and nothing is triaged. Generic health feeds are mostly
off-topic for the monitored conditions, so this lane selects by monitored term (config/health_watchlist.json) and always shows
safety-flagged signals. Deterministic, no model calls, and it never raises: a lane that cannot be built says so instead of looking quiet.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

MASTER_FLAG = "BRIEF_HEALTH_V1"
MORNING_FLAG = "BRIEF_HEALTH_V1_MORNING"
_TRUE = ("1", "true", "yes", "on")
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "health_watchlist.json"

LOOKBACK_DAYS = 14                 # research moves slowly: a day's window is mostly empty
STALE_COLLECTION_DAYS = 4          # the freshest loaded signal older than this: say collection looks stale
FRESH_HOURS = 48                   # 'new' means collected in the last two days; older items only fill a quiet morning
MAX_MATCHED = 5
MAX_OLDER = 3
MAX_SAFETY = 3
PAGE_SIZE = 500
MAX_PAGES = 6


def enabled() -> bool:
    """True only on an explicit opt-in for the morning lane (or the master flag)."""
    def on(name):
        return os.getenv(name, "").strip().lower() in _TRUE
    return on(MASTER_FLAG) or on(MORNING_FLAG)


@dataclass(frozen=True)
class Condition:
    name: str
    match: re.Pattern


class Watchlist(tuple):
    """The conditions (a tuple, so it iterates as before) plus the title pattern that drops animal studies."""
    exclude: re.Pattern | None = None


def load_watchlist(path: str | None = None) -> Watchlist:
    cfg = json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
    wl = Watchlist(Condition(name, re.compile("|".join(f"(?:{t})" for t in c["terms"]), re.IGNORECASE))
                   for name, c in cfg["conditions"].items() if c.get("terms"))
    if cfg.get("exclude_title"):
        wl.exclude = re.compile("|".join(f"(?:{t})" for t in cfg["exclude_title"]), re.IGNORECASE)
    return wl


def load_signals(sb_get, *, now: datetime | None = None, days: int = LOOKBACK_DAYS) -> list[dict]:
    """Page through health_signals (PostgREST caps a page). Fails soft: [] on any error."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: dict[str, dict] = {}
    try:
        for page in range(MAX_PAGES):
            rows = sb_get("health_signals",
                          f"collected_at=gte.{since}&suppressed=eq.false&order=collected_at.desc"
                          f"&limit={PAGE_SIZE}&offset={page * PAGE_SIZE}"
                          "&select=signal_id,title,description,health_domain,signal_type,study_design,sample_size,rank_score,"
                          "safety_relevance,fda_flagged,severity,collected_at,published_at,canonical_url,health_source_registry(source_name)")
            for r in rows or []:
                out[str(r.get("signal_id"))] = r
            if not rows or len(rows) < PAGE_SIZE:
                break
    except Exception:
        log.warning("health signals unavailable", exc_info=True)
        return []
    return list(out.values())


@dataclass
class Pick:
    condition: str | None            # None for a safety signal that matched no condition
    title: str
    source: str
    kind: str                        # plain-language kind of evidence ("randomised trial", "registered trial, not yet recruiting" ...)
    safety: bool
    rank: float
    fresh: bool


_STUDY_WORDS = {"rct": "randomised trial", "meta_analysis": "review of many studies", "observational": "observational study",
                "systematic_review": "systematic review", "cohort": "cohort study", "case_control": "case-control study",
                "case_report": "case report"}
_TRIAL_STATUS = {"NOT_YET_RECRUITING": "not yet recruiting", "RECRUITING": "now recruiting", "ENROLLING_BY_INVITATION": "recruiting by invitation",
                 "ACTIVE_NOT_RECRUITING": "under way", "COMPLETED": "completed"}


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _kind(row: dict) -> str:
    """Say what sort of evidence this is, in words. A registry entry is a plan or an in-progress trial, not a finding."""
    desc = (row.get("description") or "").strip()
    m = re.match(r"Status:\s*([A-Z_]+)", desc)
    n = row.get("sample_size")
    try:
        n = int(str(n).strip()) if n is not None and not isinstance(n, bool) else 0
    except ValueError:
        n = 0
    people = f", {n} people" if n > 0 else ""
    if m:
        status = _TRIAL_STATUS.get(m.group(1))
        return f"registered trial, {status}{people}" if status else f"registered trial{people}"
    design = str(row.get("study_design") or "").strip().lower()
    word = _STUDY_WORDS.get(design, design.replace("_", " ") if design else "study")
    return word if design == "meta_analysis" else f"{word}{people}"


def _parse_time(value) -> datetime | None:
    """A database or ISO timestamp as an aware UTC datetime, or None. Naive values are read as UTC."""
    text = str(value or "").strip().replace(" ", "T").replace("Z", "+00:00")
    if re.search(r"[+-]\d{2}$", text):                # '+00' (Postgres) -> '+00:00'
        text += ":00"
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _pick(row: dict, condition: str | None, safety: bool, now: datetime) -> Pick:
    src = (row.get("health_source_registry") or {}).get("source_name") or "Unknown source"
    when = _parse_time(row.get("collected_at"))
    fresh = when is not None and now - when <= timedelta(hours=FRESH_HOURS)
    return Pick(condition, re.sub(r"\s+", " ", row.get("title") or "").strip(), src, _kind(row), safety, float(row.get("rank_score") or 0), fresh)


def select(rows: list[dict], conditions: tuple[Condition, ...], now: datetime | None = None) -> tuple[list[Pick], list[Pick]]:
    """(matched, safety). A signal appears once; a safety-flagged signal goes to the safety list even when it also matches a term.
    Matched signals are ordered fresh first (rank, then newest), then older ones."""
    now = now or datetime.now(timezone.utc)
    seen: set[str] = set()
    matched: list[Pick] = []
    safety: list[Pick] = []
    newest_first = sorted(rows, key=lambda r: str(r.get("collected_at") or ""), reverse=True)
    for r in sorted(newest_first, key=lambda r: -float(r.get("rank_score") or 0)):   # stable: rank first, newest among equals
        key = _norm(r.get("title"))
        if not key or key in seen:
            continue
        text = f"{r.get('title') or ''} {r.get('description') or ''}"
        exclude = getattr(conditions, "exclude", None)
        cond = None if (exclude and exclude.search(r.get("title") or "")) else next((c.name for c in conditions if c.match.search(text)), None)
        flagged = bool(r.get("safety_relevance") or r.get("fda_flagged"))
        if flagged:
            seen.add(key)
            safety.append(_pick(r, cond, True, now))
        elif cond:
            seen.add(key)
            matched.append(_pick(r, cond, False, now))
    matched.sort(key=lambda p: not p.fresh)          # stable: fresh first, rank order kept inside each group
    return matched, safety[:MAX_SAFETY]


def _short(title: str, n: int = 120) -> str:
    return title if len(title) <= n else title[: n - 1].rstrip() + "…"


def format_lane(matched: list[Pick], safety: list[Pick], stale: bool = False) -> list[str]:
    fresh = [p for p in matched if p.fresh][:MAX_MATCHED]
    older = [p for p in matched if not p.fresh][:MAX_OLDER]
    head = "HEALTH WATCH (your monitored conditions)"
    if not fresh and not older and not safety:
        note = " Health collection looks stale, so this may not mean nothing happened." if stale else ""
        return [head, f"- Nothing new in your monitored conditions.{note}"]
    out = [head]
    for p in safety:
        tag = f" ({p.condition})" if p.condition else ""
        out.append(f"- SAFETY{tag}: {_short(p.title)} — {p.source}")
    for p in fresh:
        out.append(f"- {p.condition}: {_short(p.title)} — {p.kind} ({p.source})")
    if not fresh and older:
        out.append("- Nothing new in the last two days. Most recent in your monitored conditions:")
        for p in older:
            out.append(f"  - {p.condition}: {_short(p.title)} — {p.kind} ({p.source})")
    return out


def health_lines(sb_get, now: datetime | None = None) -> list[str]:
    """The lane as plain text lines, or [] when the flag is off. Never raises; a lane that cannot be built says so."""
    if not enabled():
        return []
    try:
        now = now or datetime.now(timezone.utc)
        rows = load_signals(sb_get, now=now)
        if not rows:
            return ["HEALTH WATCH", "- Unavailable: no recent health signals could be loaded, so nothing here should be read as quiet."]
        matched, safety = select(rows, load_watchlist(), now)
        newest = max((w for w in (_parse_time(r.get("collected_at")) for r in rows) if w), default=None)
        stale = newest is None or now - newest > timedelta(days=STALE_COLLECTION_DAYS)
        return format_lane(matched, safety, stale)
    except Exception:
        log.warning("health lane unavailable", exc_info=True)
        return ["HEALTH WATCH", "- Unavailable (the health lane failed); nothing here should be read as quiet."]
