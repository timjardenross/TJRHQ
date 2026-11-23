"""Topic & Theme Layer for the Morning brief (Phase 2), flag-gated and default OFF.

The V1 evidence picture is about INCIDENTS. This lane covers what the Captain cares about that is not an incident: which developments
and running themes in the watched topics (AI & chips, tech outages, cyber, cloud, telco & payments, AI policy, work & AI adoption) are
moving. It reads the same stored reports, groups them by named entity and theme, and says why each line is shown.

Deterministic, no model calls. Everything here is pure except `load_reports`, which pages through an injected PostgREST getter and
fails soft. The topics, people and companies live in config/theme_watchlist.json.

Rules (all counted on NEWS reports only; content/wellness feeds never count):
  * story   : a named entity (or a group of entities that appear in the same reports) with >= 6 reports from >= 2 publishers in the last
              24h that is >= 2x its own prior-3-day daily average ("spike"), or >= 10 reports from >= 3 publishers ("sustained").
  * running : a theme with 5-80 reports from >= 3 publishers over >= 2 days in the last 7 days AND new items in the last 48h; shown with
              up to two recent event headlines, one per publisher.
  * time    : a report's PUBLISHED time (as V1 does), falling back to collection time; so an old article re-collected today is not new.
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from intelligence import event_detection as ed
from intelligence import weekly_evidence as we

log = logging.getLogger(__name__)

MASTER_FLAG = "BRIEF_THEMES_V1"
MORNING_FLAG = "BRIEF_THEMES_V1_MORNING"
_TRUE = ("1", "true", "yes", "on")
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "theme_watchlist.json"

# ── tunables (the surfacing rule) ───────────────────────────────────────────────────────────────────────────────
RECENT_HOURS = 24
BASELINE_DAYS = 3                 # "what changed since the last few days" (a 7-day mean hides a return after an earlier surge)
SPIKE_MIN_REPORTS, SPIKE_MIN_PUBLISHERS, SPIKE_RATIO = 6, 2, 2.0
SUSTAINED_MIN_REPORTS, SUSTAINED_MIN_PUBLISHERS = 10, 3
RUNNING_MIN_REPORTS, RUNNING_MAX_REPORTS, RUNNING_MIN_PUBLISHERS, RUNNING_MIN_DAYS = 5, 80, 3, 2
RUNNING_NEW_HOURS = 48
MAX_STORY_LINES, MAX_RUNNING_LINES = 4, 3
LOAD_HOURS = 192                  # 8 days: 7-day running window plus the baseline
PAGE_SIZE, MAX_PAGES = 1000, 8

_STOP_CAPS = frozenset(["The", "A", "An", "And", "Or", "Of", "To", "In", "On", "For", "With", "As", "At", "By", "From", "After", "Before", "Over", "Under", "Live", "Breaking", "Why", "How", "What", "When", "Who", "Which", "More", "Most", "New", "This", "That", "US", "UK", "AU"])
_GENERIC = frozenset(["australia", "australian", "australians", "trump", "china", "chinese", "america", "american", "europe", "european", "government", "federal", "labor", "coalition", "sydney", "melbourne", "brisbane", "perth", "adelaide", "bloomberg", "reuters", "wall", "street", "financial", "times", "news", "states", "united", "president", "minister", "prime", "albanese", "company", "group", "nsw", "victoria", "queensland", "india", "japan", "russia", "ukraine", "israel", "iran"])
_NOISE_TITLE = re.compile(r"(?i)scheduled maintenance|planned maintenance|capacity expansion|network infrastructure upgrade|maintenance window"
                          r"|\b(?:AFL|NRL|A-League|draft)\b|stadium|sponsor")
_EVENT_VERBS = re.compile(r"(?i)\b(?:reinstat\w+|rehir\w+|re-?appoint\w+|raises?|raised|announc\w+|launch\w+|acquir\w+|buys?|bought|warns?|cuts?|fires?|resign\w*"
                          r"|ipo|outage|breach\w*|hit|hits|falls?|fell|soars?|surges?|plunges?|names?|returns?|approv\w+|bans?|sues?|agrees?|deal|ousted?|quits?"
                          r"|jumps?|slumps?|rolls? out|unveils?|restor\w+|disrupt\w+|down)\b")
_SOFT = re.compile(r"(?i)^(?:live:|opinion|analysis|explainer|why |how |what |could |should |is |are |will |does |do )|\?|;"
                   r"|\b(?:analyst|discusses|etf iq|open interest|credit heads|podcast|the download|newsletter|morning mail|explained)\b|\bwhat (?:it|this) means\b")
_KIND_WEIGHT = {we.PRIMARY: 3, we.MAINSTREAM: 2, we.SPECIALIST: 2, we.AGGREGATOR: 1}
_EXCLUDED_KINDS = frozenset({we.CONTENT})


def enabled() -> bool:
    """True only on an explicit opt-in for the morning lane (or the master flag)."""
    def on(name):
        return os.getenv(name, "").strip().lower() in _TRUE
    return on(MASTER_FLAG) or on(MORNING_FLAG)


# ── watchlist ────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Theme:
    name: str
    pillar: str
    match: re.Pattern
    entity: re.Pattern


def _compile(cfg: dict) -> re.Pattern:
    parts = [r"(?i:\b" + re.escape(e) + r"\b)" for e in cfg.get("entities", [])]
    parts += [r"\b" + re.escape(a) + r"\b" for a in cfg.get("acronyms", [])]
    parts += [r"(?i:" + p + ")" for p in cfg.get("phrases", [])]
    return re.compile("|".join(parts)) if parts else re.compile(r"(?!x)x")


def _entity_pattern(cfg: dict) -> re.Pattern:
    ents = cfg.get("entities", [])
    return re.compile("|".join(r"(?i:\b" + re.escape(e) + r"\b)" for e in ents)) if ents else re.compile(r"(?!x)x")


@lru_cache(maxsize=4)
def load_watchlist(path: str | None = None) -> tuple[Theme, ...]:
    data = json.loads(Path(path or CONFIG_PATH).read_text())["themes"]
    return tuple(Theme(name, cfg.get("pillar", ""), _compile(cfg), _entity_pattern(cfg)) for name, cfg in data.items())


# ── loading ──────────────────────────────────────────────────────────────────────────────────────────────────────
def load_reports(sb_get, *, hours: int = LOAD_HOURS, now: datetime | None = None) -> list[dict]:
    """Page through intelligence_events (PostgREST caps a page, so one big limit is not safe). Fails soft: [] on any error."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: dict[str, dict] = {}
    try:
        for page in range(MAX_PAGES):
            rows = sb_get("intelligence_events",
                          f"collected_at=gte.{since}&suppressed=eq.false&signal_status=neq.DUPLICATE&order=collected_at.desc"
                          f"&limit={PAGE_SIZE}&offset={page * PAGE_SIZE}"
                          "&select=event_id,raw_title,raw_summary,geography,collected_at,published_at,canonical_url,intelligence_source_registry(source_name)")
            for r in rows or []:
                reg = r.get("intelligence_source_registry") or {}
                eid = str(r.get("event_id"))
                out[eid] = {"id": eid, "title": r.get("raw_title") or "", "summary": r.get("raw_summary") or "",
                            "source": reg.get("source_name") or "", "geography": r.get("geography") or "",
                            "collected_at": r.get("collected_at"), "published_at": r.get("published_at"), "url": r.get("canonical_url")}
            if not rows or len(rows) < PAGE_SIZE:
                break
    except Exception:
        log.warning("theme reports unavailable", exc_info=True)
        return []
    return list(out.values())


# ── the lane ─────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class StoryLine:
    theme: str
    names: list[str]
    reports: int
    publishers: int
    per_day: float
    ratio: float
    why: str                       # "spike" | "sustained"
    lead_title: str
    lead_source: str


@dataclass
class RunningLine:
    theme: str
    reports: int
    publishers: int
    new_48h: int
    picks: list[tuple[str, str]] = field(default_factory=list)       # (source, title)


@dataclass
class Lane:
    stories: list[StoryLine] = field(default_factory=list)
    running: list[RunningLine] = field(default_factory=list)
    news_reports: int = 0
    themed_reports: int = 0

    @property
    def empty(self) -> bool:
        return not self.stories and not self.running


def _entities(title: str) -> set[str]:
    ents = set()
    for m in re.finditer(r"\b[A-Z][a-zA-Z]{2,}\b", title or ""):
        w = m.group(0)
        if w in _STOP_CAPS:
            continue
        ents.add(w.lower())
    return {e for e in ents if e not in _GENERIC}


def _prepare(reports: list[dict], now: datetime, themes: tuple[Theme, ...]) -> list[dict]:
    pool = []
    for r in reports:
        ts = ed._report_time(r)
        if ts is None or ts > now + timedelta(hours=1) or ts < now - timedelta(days=8):
            continue
        source = r.get("source") or ""
        kind = we.source_kind(source)
        title = r.get("title") or ""
        if kind in _EXCLUDED_KINDS or _NOISE_TITLE.search(title):
            continue
        hit = [t.name for t in themes if t.match.search(title)]
        if not hit:
            continue
        pool.append({"id": r["id"], "title": title, "source": source, "kind": kind, "ts": min(ts, now),
                     "publisher": we.publisher_family(source, title), "themes": hit, "ents": _entities(title)})
    return pool


def _pick_lead(rs: list[dict], names: set[str], theme: Theme) -> dict:
    """The headline that says what happened: names the story's watchlist entities, has an event verb, is not a question/opinion/market
    chatter piece, comes from a mainstream/primary source, sensible length; the earliest wins ties (the breaking headline)."""
    def key(r):
        t = r["title"]
        watched = len({m.group(0).lower() for m in theme.entity.finditer(t)})
        score = 3.0 * min(2, len(r["ents"] & names)) + 3.0 * min(2, watched)
        score += 2.0 if _EVENT_VERBS.search(t) else 0.0
        score -= 3.0 if _SOFT.search(t) else 0.0
        score -= 2.0 if len(t) > 110 else 0.0
        score += _KIND_WEIGHT.get(r["kind"], 1) * 0.5
        return (-score, r["ts"].timestamp())
    return min(rs, key=key)


def build_lane(reports: list[dict], now: datetime, themes: tuple[Theme, ...] | None = None) -> Lane:
    themes = themes if themes is not None else load_watchlist()
    pool = _prepare(reports, now, themes)
    lane = Lane(news_reports=len(reports), themed_reports=len(pool))
    day0 = now - timedelta(hours=RECENT_HOURS)
    for theme in themes:
        sub = [r for r in pool if theme.name in r["themes"]]
        recent = [r for r in sub if r["ts"] > day0]
        base = [r for r in sub if day0 - timedelta(days=BASELINE_DAYS) <= r["ts"] <= day0]
        by_entity = defaultdict(list)
        for r in recent:
            for e in r["ents"]:
                by_entity[e].append(r)
        # entities that appear in largely the same reports are ONE story ('nvidia' + 'huang'); merge first, then test the union
        groups: list[dict] = []
        for e in sorted((e for e, rs in by_entity.items() if len(rs) >= 3), key=lambda e: -len(by_entity[e])):
            ids = {r["id"] for r in by_entity[e]}
            for g in groups:
                if len(ids & g["ids"]) / max(1, min(len(ids), len(g["ids"]))) >= 0.6:
                    g["ents"].append(e)
                    g["ids"] |= ids
                    break
            else:
                groups.append({"ents": [e], "ids": set(ids)})
        cands = []
        for g in groups:
            names = set(g["ents"])
            rs = [r for r in recent if r["ents"] & names]
            pubs = {r["publisher"] for r in rs}
            per_day = sum(1 for r in base if r["ents"] & names) / float(BASELINE_DAYS)
            ratio = len(rs) / (per_day + 1.0)
            if len(pubs) >= SPIKE_MIN_PUBLISHERS and len(rs) >= SPIKE_MIN_REPORTS and ratio >= SPIKE_RATIO:
                cands.append((g["ents"], rs, pubs, per_day, ratio, "spike"))
            elif len(pubs) >= SUSTAINED_MIN_PUBLISHERS and len(rs) >= SUSTAINED_MIN_REPORTS:
                cands.append((g["ents"], rs, pubs, per_day, ratio, "sustained"))
        cands.sort(key=lambda c: (-len(c[2]), -len(c[1])))
        for ents, rs, pubs, per_day, ratio, why in cands[:3]:
            lead = _pick_lead(rs, set(ents), theme)
            lane.stories.append(StoryLine(theme.name, [e.title() for e in ents[:3]], len(rs), len(pubs), per_day, ratio, why,
                                          lead["title"], lead["source"]))
        week = [r for r in sub if r["ts"] >= now - timedelta(days=7)]
        new48 = [r for r in week if r["ts"] >= now - timedelta(hours=RUNNING_NEW_HOURS)]
        pubs_week = {r["publisher"] for r in week}
        days_week = {r["ts"].date() for r in week}
        if (RUNNING_MIN_REPORTS <= len(week) <= RUNNING_MAX_REPORTS and len(pubs_week) >= RUNNING_MIN_PUBLISHERS
                and len(days_week) >= RUNNING_MIN_DAYS and new48):
            def pkey(r):
                t = r["title"]
                return ((-2.0 if _EVENT_VERBS.search(t) else 0.0) + (3.0 if _SOFT.search(t) else 0.0) - 0.5 * _KIND_WEIGHT.get(r["kind"], 1),
                        -r["ts"].timestamp())
            picks, seen = [], set()
            for r in sorted(new48, key=pkey):
                if r["publisher"] in seen:
                    continue
                seen.add(r["publisher"])
                picks.append((r["source"], r["title"]))
                if len(picks) == 2:
                    break
            lane.running.append(RunningLine(theme.name, len(week), len(pubs_week), len(new48), picks))
    lane.stories.sort(key=lambda s: (-s.publishers, -s.reports))
    lane.stories = lane.stories[:MAX_STORY_LINES]
    lane.running.sort(key=lambda r: -r.new_48h)
    lane.running = lane.running[:MAX_RUNNING_LINES]
    return lane


def _short(title: str, n: int = 110) -> str:
    title = re.sub(r"\s+", " ", title or "").strip()
    return title if len(title) <= n else title[: n - 1].rstrip() + "…"


def format_lane(lane: Lane) -> list[str]:
    head = "DEVELOPMENTS & THEMES (your watched topics; last 24h against the prior 3 days)"
    if lane.empty:
        return [head, "- Nothing new in your watched topics."]
    out = [head]
    for s in lane.stories:
        tag = f"▲{s.ratio:.0f}x the prior-3-day average of {s.per_day:.1f}/day" if s.why == "spike" else "sustained high volume"
        out.append(f"- {s.theme} — {' / '.join(s.names)}: {s.reports} reports from {s.publishers} publishers ({tag}). Lead: {s.lead_source}: {_short(s.lead_title)}")
    for r in lane.running:
        heads = " | ".join(f"{src}: {_short(title, 80)}" for src, title in r.picks)
        out.append(f"- {r.theme} (running theme: {r.reports} reports from {r.publishers} publishers this week, {r.new_48h} new in 48h) — {heads}")
    return out


def theme_lines(sb_get, now: datetime | None = None) -> list[str]:
    """The morning lane as plain text lines, or [] when the flag is off. Never raises; a lane that cannot be built says so."""
    if not enabled():
        return []
    try:
        now = now or datetime.now(timezone.utc)
        reports = load_reports(sb_get, now=now)
        if not reports:
            return ["DEVELOPMENTS & THEMES", "- Unavailable: no recent reports could be loaded, so nothing here should be read as quiet."]
        return format_lane(build_lane(reports, now))
    except Exception:
        log.warning("theme lane unavailable", exc_info=True)
        return ["DEVELOPMENTS & THEMES", "- Unavailable (the theme lane failed); nothing here should be read as quiet."]
