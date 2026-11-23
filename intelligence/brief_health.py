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
MAX_MATCHED = 5
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
    design: str
    safety: bool
    rank: float


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _pick(row: dict, condition: str | None, safety: bool) -> Pick:
    n = row.get("sample_size")
    design = " · ".join(x for x in (str(row.get("study_design") or "").strip(), f"n={n}" if n else "") if x)
    src = (row.get("health_source_registry") or {}).get("source_name") or "Unknown source"
    return Pick(condition, re.sub(r"\s+", " ", row.get("title") or "").strip(), src, design, safety, float(row.get("rank_score") or 0))


def select(rows: list[dict], conditions: tuple[Condition, ...]) -> tuple[list[Pick], list[Pick]]:
    """(matched, safety). A signal appears once; a safety-flagged signal goes to the safety list even when it also matches a term."""
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
            safety.append(_pick(r, cond, True))
        elif cond:
            seen.add(key)
            matched.append(_pick(r, cond, False))
    return matched[:MAX_MATCHED], safety[:MAX_SAFETY]


def _short(title: str, n: int = 120) -> str:
    return title if len(title) <= n else title[: n - 1].rstrip() + "…"


def format_lane(matched: list[Pick], safety: list[Pick], total: int) -> list[str]:
    head = f"HEALTH WATCH (monitored conditions; last {LOOKBACK_DAYS} days, {total} signals checked)"
    if not matched and not safety:
        return [head, "- Nothing new in your monitored conditions."]
    out = [head]
    for p in safety:
        tag = f"{p.condition}; " if p.condition else ""
        out.append(f"- SAFETY — {tag}{_short(p.title)} ({p.source})")
    for p in matched:
        design = f"; {p.design}" if p.design else ""
        out.append(f"- {p.condition} — {_short(p.title)} ({p.source}{design})")
    return out


def health_lines(sb_get, now: datetime | None = None) -> list[str]:
    """The lane as plain text lines, or [] when the flag is off. Never raises; a lane that cannot be built says so."""
    if not enabled():
        return []
    try:
        rows = load_signals(sb_get, now=now)
        if not rows:
            return ["HEALTH WATCH", "- Unavailable: no recent health signals could be loaded, so nothing here should be read as quiet."]
        matched, safety = select(rows, load_watchlist())
        return format_lane(matched, safety, len(rows))
    except Exception:
        log.warning("health lane unavailable", exc_info=True)
        return ["HEALTH WATCH", "- Unavailable (the health lane failed); nothing here should be read as quiet."]
