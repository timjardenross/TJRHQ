"""Longitudinal analysis and emerging trends (wk-trends/0.1.0-prototype) -- OFFLINE, default OFF, not wired into any live path.

Weekly trend measures computed over the stored intelligence events, by INCIDENT (``intelligence.event_detection``), bucketed by the
report's own publication date (never the collection date). Because collection itself changed during the history (feed ceilings, new
sources, outages, a published_at repair), every output carries:

  * a volume denominator (reports published that week, and reports collected that week, by source class);
  * a per-week coverage record (active sources by class, sources that appeared or went silent, dated coverage changes, known broken
    sources, week reliability);
  * two bases -- ``all`` sources and a ``constant`` set of sources that were collecting at a steady rate throughout the window --
    and a ``coverage_confounded`` flag on any trend that spans a coverage change and does not hold in the constant set.

Measures: incident counts by sector and by Australian relevance; restoration duration where a dated restoration report exists; repeated
disruption of one named subject (3+ episodes inside 28 days); emerging terms/entities against a trailing baseline with a minimum-
evidence rule. Nothing here asserts causation, and a rule that cannot be met reports "insufficient evidence" instead of a number.

Pure module: takes already-gathered dicts, reads no database, writes nothing.
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from itertools import chain, pairwise
from statistics import median

from intelligence import event_detection as ed
from intelligence import weekly_evidence as we

METHOD_VERSION = "wk-trends/0.1.0-prototype"
FLAG = "INTELLIGENCE_LONGITUDINAL_TRENDS"
_TRUE = ("1", "true", "yes", "on")


def enabled() -> bool:
    """True only on an explicit opt-in. Nothing in the platform calls this module unless the flag is set."""
    return os.getenv(FLAG, "").strip().lower() in _TRUE


# -- Parameters (all stated in every output so a reader can see what was assumed) ------------------------------------------

PARAMS = {
    "week": "Monday 00:00 UTC to Sunday 23:59 UTC, bucketed by the report's own verified publication time",
    "baseline_weeks": 6,             # trailing eligible weeks pooled as the emerging-term baseline
    "min_baseline_weeks": 4,
    "min_baseline_incidents": 30,
    "min_week_incidents": 10,
    "min_term_incidents": 4,         # minimum-evidence rule: incidents carrying the term this week
    "min_term_publishers": 3,        # ... reported by this many independent publisher families
    "min_term_days": 2,              # ... on at least this many distinct publication days
    "min_ratio": 3.0,                # share this week / smoothed baseline share
    "max_p": 0.001,                  # one-sided binomial tail (many terms are tested, so the bar is strict)
    "repeat_min_episodes": 3,
    "repeat_window_days": 28,
    "repeat_min_gap_hours": 12,      # status-page episodes; a news-headed episode needs repeat_news_gap_hours (follow-ups run for days)
    "repeat_news_gap_hours": 96,
    "restoration_max_days": 14,
    "restoration_min_n": 3,          # medians below this many evidenced restorations are withheld
    "constant_min_week_share": 0.9,  # a constant-coverage source collected in >=90% of the window's weeks
    "constant_max_rate_step": 2.0,   # ... and its weekly volume did not step by more than 2x across a rate-change date
    "volume_anomaly_low": 0.6,       # a week below 60% (or above 160%) of its regime median is flagged unreliable
    "volume_anomaly_high": 1.6,
    "undated_share_max": 0.10,
}

# Feeds that catalogue natural events rather than service incidents: kept in the volume denominator, excluded from incident measures.
EXCLUDED_FROM_INCIDENTS = frozenset({"Geoscience Australia Earthquakes"})
# Event types that count as a service-affecting incident. Natural-hazard notices and vulnerability advisories are counted separately.
SERVICE_TYPES = ("outage", "cyber_incident", "service_disruption", "supply_shortfall", "water_quality", "physical")
DISRUPTION_TYPES = ("outage", "service_disruption", "cyber_incident")

# Dated collection changes. `kind`: rate (collection volume of existing sources stepped), timestamp (published_at semantics changed),
# sources (sources added/repaired), outage (a window of reduced collection), start (collection began).
# Dates are evidenced in the repository history, the registry and the stored events themselves (see docs/ for the audit).
COVERAGE_CHANGES = (
    {"date": "2026-07-12", "kind": "start", "note": "First stored events: collection began (the 6 and 13 July weeks are ramp-up)."},
    {"date": "2026-08-09", "kind": "sources", "note": "Status-page sources registered (Twilio, OpenAI, Supabase, Vercel, ...); AEMO Market Notices repaired from 10 Aug."},
    {"date": "2026-09-06", "kind": "rate", "note": "Per-run feed ceiling raised: ABC, Bloomberg, BBC, FT, Guardian volume stepped about 4x (about 45 to about 200 items a day); six sources added (Google News x4, iTnews, ARN)."},
    {"date": "2026-09-26", "end": "2026-09-27", "kind": "outage", "note": "Reduced collection on 26 and 27 Sep (about 55-65% of a normal day)."},
    {"date": "2026-10-02", "end": "2026-10-04", "kind": "outage", "note": "No reports collected at all on 2, 3 and 4 Oct (collection gap)."},
    {"date": "2026-11-06", "kind": "sources", "confounds": False,
     "note": "AEMO NEMweb Market Notices retired (duplicate of AEMO Market Notices, which continues): recorded, not a coverage reduction."},
    {"date": "2026-11-24", "kind": "timestamp", "note": "RSS published_at repair (+10h, 34,238 rows; 487 rows not corrected) and a further feed-ceiling increase (#703). The 23 Nov week is partial."},
)
RELIABILITY_KINDS = ("start", "rate", "timestamp", "outage")   # a change of one of these kinds makes its own week unreliable

# Known broken or silent sources, derived from the stored events (last/first event dates) and the source-health table (0 successful runs
# since at least 2026-10-19 for ASIC News Centre, ASD Publications, Telstra Service Alerts; OAIC feeds failing since 2026-11-09).
KNOWN_BROKEN = (
    {"source": "ASIC News Centre", "from": "2026-09-08", "note": "Only 4 events (24 Aug to 7 Sep), none since; 0 successful health checks in the retained history."},
    {"source": "ASIC Enforcement Activity", "from": "2026-07-12", "note": "No events ever stored; health checks all failing."},
    {"source": "OAIC Breach Notifications", "from": "2026-08-11", "note": "No events after 10 Aug; health checks failing from 9 Nov."},
    {"source": "OAIC Privacy Determinations & News", "from": "2026-08-30", "note": "No events after 29 Aug; health checks failing from 9 Nov."},
    {"source": "Financial Newswire", "from": "2026-07-20", "to": "2026-08-30", "note": "Zero events for six weeks, then resumed."},
    {"source": "Geoscience Australia Earthquakes", "from": "2026-07-20", "to": "2026-08-02", "note": "Zero events for two weeks, then resumed."},
    {"source": "AEMO NEMweb Market Notices", "from": "2026-11-06", "note": "Retired; AEMO Market Notices continues."},
)


# -- Time ------------------------------------------------------------------------------------------------------------------

def change_overlaps(c: dict, a: date, b: date) -> bool:
    """True when the dated coverage change (a single day, or date..end) overlaps the inclusive range a..b."""
    lo = date.fromisoformat(c["date"])
    hi = date.fromisoformat(c.get("end") or c["date"])
    return lo <= b and hi >= a


def week_start(d) -> date:
    if isinstance(d, datetime):
        d = d.astimezone(timezone.utc).date() if d.tzinfo else d.date()
    return d - timedelta(days=d.weekday())


def _iso(d: date) -> str:
    return d.isoformat()


def week_range(first: date, last: date) -> list[date]:
    out, w = [], week_start(first)
    while w <= week_start(last):
        out.append(w)
        w += timedelta(days=7)
    return out


def publication_time(event: dict) -> datetime | None:
    """The report's OWN publication time, or None. A row without a parseable published time, or one dated later than its collection
    (plus 1h skew), is undated: it is never placed in a week by its collection time."""
    return we._parse_ts(event.get("published_at")) if ed._time_verified(event) else None


def source_class(source: str) -> str:
    return we.source_kind(source or "")


# -- Input -----------------------------------------------------------------------------------------------------------------

def events_from_rows(rows) -> list[dict]:
    """Rows are [id, source, geography, collected_at, published_at, title, summary, suppressed, event_type, sector]
    (the shape of the read-only export)."""
    out = []
    for r in rows:
        out.append({"id": str(r[0]), "source": r[1], "geography": r[2] or "", "collected_at": r[3], "published_at": r[4],
                    "title": r[5] or "", "summary": r[6] or "", "suppressed": bool(r[7]) if len(r) > 7 else False})
    return out


# -- Volume denominators and coverage record -------------------------------------------------------------------------------

def volume_denominators(events: list[dict], weeks: list[date]) -> dict[str, dict]:
    """Per week: reports collected, reports published (verified publication time), undated, and each by source class."""
    wk = {_iso(w): {"collected": 0, "published": 0, "undated": 0, "collected_by_class": Counter(), "published_by_class": Counter()} for w in weeks}
    for e in events:
        c = we._parse_ts(e.get("collected_at"))
        cls = source_class(e.get("source"))
        if c is not None and _iso(week_start(c)) in wk:
            b = wk[_iso(week_start(c))]
            b["collected"] += 1
            b["collected_by_class"][cls] += 1
            if publication_time(e) is None:
                b["undated"] += 1
        p = publication_time(e)
        if p is not None and _iso(week_start(p)) in wk:
            b = wk[_iso(week_start(p))]
            b["published"] += 1
            b["published_by_class"][cls] += 1
    for b in wk.values():
        b["collected_by_class"] = dict(sorted(b["collected_by_class"].items()))
        b["published_by_class"] = dict(sorted(b["published_by_class"].items()))
    return wk


def source_weekly_counts(events: list[dict]) -> dict[str, Counter]:
    out: dict[str, Counter] = defaultdict(Counter)
    for e in events:
        c = we._parse_ts(e.get("collected_at"))
        if c is not None:
            out[e.get("source") or ""][_iso(week_start(c))] += 1
    return out


def coverage_record(events: list[dict], weeks: list[date], *, data_start: date, data_end: date,
                    changes=COVERAGE_CHANGES, broken=KNOWN_BROKEN) -> dict[str, dict]:
    """Per week: active sources by class (>=1 report collected), sources first seen, sources last seen (went silent), dated coverage
    changes, known-broken sources, and whether the week is a partial one."""
    per_src = source_weekly_counts(events)
    first_seen = {s: min(c) for s, c in per_src.items()}
    last_seen = {s: max(c) for s, c in per_src.items()}
    rec = {}
    last_week = _iso(week_start(data_end))
    for w in weeks:
        k = _iso(w)
        end = w + timedelta(days=6)
        active = [s for s, c in per_src.items() if c.get(k)]
        by_class = Counter(source_class(s) for s in active)
        rec[k] = {
            "active_sources": len(active),
            "active_by_class": dict(sorted(by_class.items())),
            "new_sources": sorted(s for s in active if first_seen[s] == k and k != _iso(week_start(data_start))),
            "went_silent": sorted(s for s in per_src if last_seen[s] == _iso(w - timedelta(days=7)) and last_seen[s] != last_week),
            "changes": [c for c in changes if change_overlaps(c, w, end)],
            "known_broken": sorted(b["source"] for b in broken
                                   if date.fromisoformat(b["from"]) <= end and (b.get("to") is None or date.fromisoformat(b["to"]) >= w)),
            "partial": w < data_start or end > data_end,
        }
    return rec


def week_reliability(volume: dict[str, dict], coverage: dict[str, dict], changes=COVERAGE_CHANGES, params=PARAMS) -> dict[str, dict]:
    """A week is UNRELIABLE for trend comparison when it is partial, contains a start/rate/timestamp/outage change, is a volume outlier
    within its rate regime, or has too large a share of undated reports."""
    rate_dates = sorted(date.fromisoformat(c["date"]) for c in changes if c["kind"] in ("rate", "start"))
    keys = sorted(volume)

    def regime(k):
        return sum(1 for d in rate_dates if d <= date.fromisoformat(k) + timedelta(days=6))
    by_regime: dict[int, list[int]] = defaultdict(list)
    for k in keys:
        if not coverage[k]["partial"] and not any(c["kind"] in RELIABILITY_KINDS for c in coverage[k]["changes"]):
            by_regime[regime(k)].append(volume[k]["collected"])
    med = {r: median(v) for r, v in by_regime.items() if v}
    out = {}
    for k in keys:
        why = []
        if coverage[k]["partial"]:
            why.append("partial week")
        for c in coverage[k]["changes"]:
            if c["kind"] in RELIABILITY_KINDS:
                why.append(f"coverage change {c['date']} ({c['kind']})")
        m = med.get(regime(k))
        if m and not coverage[k]["partial"]:
            ratio = volume[k]["collected"] / m
            if ratio < params["volume_anomaly_low"] or ratio > params["volume_anomaly_high"]:
                why.append(f"collected volume {ratio:.2f}x its regime median")
        if coverage[k].get("zero_collection_days"):
            why.append("no reports collected on " + ", ".join(coverage[k]["zero_collection_days"]))
        n = volume[k]["collected"]
        if n and volume[k]["undated"] / n > params["undated_share_max"]:
            why.append(f"{volume[k]['undated']}/{n} reports undated")
        out[k] = {"reliable": not why, "reasons": why}
    return out


def derive_zero_collection_days(events: list[dict], start: date, end: date, *, floor: int = 60) -> list[tuple[str, int]]:
    """Days in [start, end] on which fewer than `floor` reports were collected across ALL sources (a normal day is 200 to 500): a
    collection outage, not a quiet news day. Derived from the data, so a gap nobody recorded still marks its week unreliable."""
    per_day: Counter = Counter()
    for e in events:
        c = we._parse_ts(e.get("collected_at"))
        if c is not None:
            per_day[c.date()] += 1
    out, d = [], start
    while d <= end:
        if per_day.get(d, 0) < floor:
            out.append((d.isoformat(), per_day.get(d, 0)))
        d += timedelta(days=1)
    return out


def derive_silent_gaps(events: list[dict], *, min_events: int = 10, min_gap_days: int = 14) -> list[dict]:
    """Evidence-based broken-source finder: per source, the collection gaps longer than `min_gap_days` (and any silence running to the end
    of the data), computed from collection times. Used to check KNOWN_BROKEN against the data."""
    times: dict[str, list[datetime]] = defaultdict(list)
    for e in events:
        c = we._parse_ts(e.get("collected_at"))
        if c:
            times[e.get("source") or ""].append(c)
    end = max((t[-1] for t in (sorted(v) for v in times.values())), default=None)
    out = []
    for s, v in times.items():
        v.sort()
        if len(v) < min_events:
            continue
        for a, b in pairwise(v):
            if (b - a).days >= min_gap_days:
                out.append({"source": s, "gap_from": a.date().isoformat(), "gap_to": b.date().isoformat(), "days": (b - a).days})
        if end and (end - v[-1]).days >= min_gap_days:
            out.append({"source": s, "gap_from": v[-1].date().isoformat(), "gap_to": None, "days": (end - v[-1]).days})
    return sorted(out, key=lambda g: (g["source"], g["gap_from"]))


def constant_sources(events: list[dict], window: list[date], *, changes=COVERAGE_CHANGES, params=PARAMS) -> dict:
    """Sources that were collecting at a steady rate throughout `window` (complete weeks only): collected in at least
    `constant_min_week_share` of the weeks, present from the first week to the last, and with no volume step larger than
    `constant_max_rate_step` across a rate change that falls inside the window."""
    per_src = source_weekly_counts(events)
    keys = [_iso(w) for w in window]
    rate_dates = [date.fromisoformat(c["date"]) for c in changes if c["kind"] == "rate"
                  and window[0] < date.fromisoformat(c["date"]) <= window[-1] + timedelta(days=6)]
    keep, drop = [], {}
    for s, c in sorted(per_src.items()):
        seen = [k for k in keys if c.get(k)]
        if not seen:
            continue
        reason = None
        if len(seen) < params["constant_min_week_share"] * len(keys):
            reason = f"collected in {len(seen)}/{len(keys)} weeks"
        elif not (c.get(keys[0]) and c.get(keys[-1])):
            reason = "not collecting in the first or last window week"
        else:
            for d in rate_dates:
                pre = [c.get(k, 0) for k in keys if date.fromisoformat(k) + timedelta(days=6) < d]
                post = [c.get(k, 0) for k in keys if date.fromisoformat(k) > d]
                if len(pre) >= 3 and len(post) >= 3:
                    a, b = median(pre), median(post)
                    ratio = (b / a) if a else math.inf
                    if ratio > params["constant_max_rate_step"] or ratio < 1 / params["constant_max_rate_step"]:
                        reason = f"weekly volume stepped {ratio:.1f}x across {d.isoformat()}"
        if reason:
            drop[s] = reason
        else:
            keep.append(s)
    return {"sources": keep, "excluded": drop, "window": [keys[0], keys[-1]]}


# -- Incidents -------------------------------------------------------------------------------------------------------------

_STATUS_FEED_RX = re.compile(r"^(?P<svc>.+?)\s+status(?:\b|$)", re.IGNORECASE)
_SUBJECT_ALIAS = {"amazon web services": "aws", "commonwealth bank": "cba", "nsw health": "nsw health"}


def _feed_subject(source: str) -> str | None:
    sm = _STATUS_FEED_RX.match(source or "")
    if sm and "google news" not in (source or "").lower():
        svc = re.sub(r"\(.*?\)", "", sm.group("svc")).strip().lower()
        return _SUBJECT_ALIAS.get(svc, svc) or None
    return None


def incident_subject(group: ed.Group, head: ed.Candidate | None = None) -> str | None:
    """The named service or organisation an incident is about, from a controlled vocabulary only (the detector's organisation
    lexicon, or the name of a status-page feed), read from the incident's HEADLINE report first so a correlator merge of two
    services cannot relabel the episode. None when no such name is present: unnamed incidents never form a repeat."""
    ordered = ([head] if head is not None else []) + [m for m in group.members if m is not head]
    for m in ordered[:1]:
        if not m.commentary and _feed_subject(m.source):
            return _feed_subject(m.source)
    for m in ordered[:1]:
        hits = [_SUBJECT_ALIAS.get(h.group(0).lower(), h.group(0).lower()) for h in ed._ORG_LEX.finditer(ed.core_title(m.title))]
        if hits:
            return hits[0]
    counts = Counter()
    for m in ordered:
        if m.commentary:
            continue
        fs = _feed_subject(m.source)
        if fs:
            counts[fs] += 1
        for hit in ed._ORG_LEX.finditer(ed.core_title(m.title)):
            counts[_SUBJECT_ALIAS.get(hit.group(0).lower(), hit.group(0).lower())] += 1
    return counts.most_common(1)[0][0] if counts else None


# Headlines that are about an outage without reporting a NEW disruption: planned work, aftermath, inquiries, market reaction, advice.
_NOT_NEW_RX = re.compile(
    r"\b(?:planned|scheduled|upgrades?|maintenance|review|inquiry|inquest|senate|blames?|blamed|repurchase|buy-?back|pay rise|"
    r"as it happened|chaos|red flags|stand down|understaffed|underfunded|aftermath|advice|compensation|lessons|"
    r"after the \w+ (?:network )?outage|july (?:mobile |network )?outage|share price|asx)\b|^after\b", re.IGNORECASE)
_OUTLET_STOP = frozenset({"news", "headlines", "abc", "australian", "broadcasting", "corporation", "times", "post", "weekly", "daily",
                          "herald", "telegraph", "nightly", "guardian", "reuters", "bloomberg", "beinsure", "yahoo", "mirage"})
# Words that carry no topic: kept out of the emerging-term test so a quiet baseline cannot make them look new.
_GENERIC = frozenset({"another", "major", "being", "government", "communication", "communications", "home", "watch", "news", "latest",
                      "first", "second", "third", "series", "report", "reports", "reported", "says", "warns", "issue", "issues",
                      "hits", "after", "amid", "across", "widespread", "massive", "global", "national", "nationwide", "tech",
                      "service", "services", "system", "systems", "network", "customers", "people", "australia", "australian",
                      "expos", "exposed", "exposes", "exposing", "affected", "affects", "update", "live", "breaking", "claims",
                      "investigates", "investigating", "investigation", "continues", "still", "down", "restored", "failure"})

_FEED_VOCAB = ed._rx(tuple(chain.from_iterable(ed.EVENT_TYPES.values())) + tuple(ed.CONSEQUENCE))


def _strip_outlets(title: str) -> str:
    t = ed.core_title(title)
    for _ in range(2):                                   # "... - ABC News & Headlines - Australian Broadcasting Corporation"
        t2 = ed.core_title(t)
        if t2 == t:
            break
        t = t2
    return t


def _entity_terms(title: str) -> set[str]:
    """Organisation/proper-noun entities from the title with every outlet suffix removed and outlet or generic words dropped."""
    return {o for o in ed._orgs(_strip_outlets(title)) if not set(o.split()) & (_OUTLET_STOP | _GENERIC)}


def _terms(title: str) -> set[str]:
    words = [w for w in ed._WORDS.findall(_strip_outlets(title).lower())
             if w not in ed._STOP and w not in _OUTLET_STOP and w not in _GENERIC and len(w) > 3]
    return {we._stem(w) for w in words if not _FEED_VOCAB.fullmatch(w) and we._stem(w) not in _GENERIC}


def build_incidents(events: list[dict], *, now: datetime | None = None) -> list[dict]:
    """Run the existing incident detection over `events` and return one record per incident that counts for trend measures: a
    non-commentary, non-vulnerability, non-hazard report that STATES (or reports unconfirmed) an incident. Warnings, forecasts,
    retrospectives, commentary, natural-hazard notices and vulnerability advisories are not counted here."""
    usable = [e for e in events if (e.get("source") or "") not in EXCLUDED_FROM_INCIDENTS]
    cands = [c for c in (ed.detect_candidate(e) for e in usable) if c.is_candidate]
    now = now or max((we._parse_ts(e.get("collected_at")) for e in usable if e.get("collected_at")), default=None)
    by_id = {str(e["id"]): e for e in usable}
    out = []
    for g in ed.correlate(cands):
        d = ed.decide(g, now=now)
        originals = [m for m in g.members if not m.commentary]
        if not originals or d.event_type in ("vulnerability", "hazard", "other"):
            continue
        if d.impact_status not in ("stated", "unconfirmed") or d.event_type not in SERVICE_TYPES:
            continue
        pubs = []
        for m in g.members:
            p = publication_time(by_id[m.event_id])
            if p is not None:
                pubs.append((p, m))
        pubs.sort(key=lambda x: x[0])
        sectors = Counter(s for m in originals for s in m.sectors)
        tier = lambda s: ed.SECTOR_TIER.get(s, 3)
        sector = min(sectors, key=lambda s: (tier(s), -sectors[s], s)) if sectors else "unclassified"
        why = ed.australian_relevance(g)
        if why is None:
            au = "editorial" if ed.australian_editorial_relevance(g) else "none"
        else:
            au = "dependency" if why.startswith("plausible dependency") else "operational"
        restored = [(p, m) for p, m in pubs if not m.commentary and ed._affirmative_restored(m.title)
                    and p >= pubs[0][0]]
        out.append({
            "incident_id": g.incident_id, "headline": d.headline.title, "event_type": d.event_type, "impact_status": d.impact_status,
            "sector": sector, "au_relevance": au, "au_reason": why, "priority": d.priority,
            "members": len(g.members), "member_ids": [m.event_id for m in g.members],
            "publishers": sorted({m.family for m in originals}), "independent_publishers": g.independent_publishers,
            "source_classes": sorted({source_class(m.source) for m in originals}),
            "first_published": pubs[0][0].isoformat() if pubs else None,
            "week": _iso(week_start(pubs[0][0])) if pubs else None,
            "restored_at": restored[0][0].isoformat() if restored else None,
            "restoration_evidence": {"id": restored[0][1].event_id, "title": restored[0][1].title, "source": restored[0][1].source} if restored else None,
            "subject": incident_subject(g, d.headline),
            "head_source": d.headline.source,
            "new_disruption": not _NOT_NEW_RX.search(d.headline.title),
            "terms": sorted(set().union(*(_terms(m.title) for m in originals)) | {o for m in originals for o in _entity_terms(m.title)}),
        })
    return out


# -- Measures --------------------------------------------------------------------------------------------------------------

def incident_counts(incidents: list[dict], weeks: list[date]) -> dict[str, dict]:
    res = {_iso(w): {"total": 0, "by_sector": Counter(), "by_au": Counter(), "by_type": Counter()} for w in weeks}
    for i in incidents:
        b = res.get(i["week"])
        if b is None:
            continue
        b["total"] += 1
        b["by_sector"][i["sector"]] += 1
        b["by_au"][i["au_relevance"]] += 1
        b["by_type"][i["event_type"]] += 1
    for b in res.values():
        for k in ("by_sector", "by_au", "by_type"):
            b[k] = dict(sorted(b[k].items(), key=lambda kv: (-kv[1], kv[0])))
    return res


def restoration_durations(incidents: list[dict], weeks: list[date], params=PARAMS) -> dict[str, dict]:
    """Where a dated restoration report exists: restoration time minus the incident's first publication. Only outage-class incidents
    are eligible; implausible spans (negative, or beyond `restoration_max_days`) are dropped and counted."""
    res = {_iso(w): {"outage_incidents": 0, "with_restoration_evidence": 0, "dropped_implausible": 0, "hours": []} for w in weeks}
    for i in incidents:
        b = res.get(i["week"])
        if b is None or i["event_type"] not in ("outage", "service_disruption"):
            continue
        b["outage_incidents"] += 1
        if i["restored_at"] and i["first_published"]:
            dt = (datetime.fromisoformat(i["restored_at"]) - datetime.fromisoformat(i["first_published"])).total_seconds() / 3600
            if 0 < dt <= params["restoration_max_days"] * 24:
                b["with_restoration_evidence"] += 1
                b["hours"].append(round(dt, 1))
            else:
                b["dropped_implausible"] += 1
    for b in res.values():
        h = sorted(b.pop("hours"))
        b["median_hours"] = round(median(h), 1) if len(h) >= params["restoration_min_n"] else None
        b["note"] = None if b["median_hours"] is not None else f"insufficient evidence (n={len(h)}, need {params['restoration_min_n']})"
        b["n_durations"] = len(h)
    return res


def repeat_disruptions(incidents: list[dict], params=PARAMS) -> list[dict]:
    """Same named subject, `repeat_min_episodes`+ distinct disruption episodes inside `repeat_window_days`. Episodes are incidents
    (already merged by the correlator) whose starts are at least `repeat_min_gap_hours` apart. Reported once per subject per
    window, at the week of the latest episode."""
    by_subj: dict[str, list[dict]] = defaultdict(list)
    for i in incidents:
        if i["subject"] and i["event_type"] in DISRUPTION_TYPES and i["first_published"] and i.get("new_disruption", True):
            by_subj[i["subject"]].append(i)
    out = []
    for subj, items in by_subj.items():
        items.sort(key=lambda x: x["first_published"])
        eps = []
        for i in items:
            t = datetime.fromisoformat(i["first_published"])
            gap = params["repeat_min_gap_hours"] if "status" in (i.get("head_source") or "").lower() else params["repeat_news_gap_hours"]
            if eps and (t - datetime.fromisoformat(eps[-1]["first_published"])).total_seconds() < gap * 3600:
                continue
            eps.append(i)
        n = params["repeat_min_episodes"]
        window = timedelta(days=params["repeat_window_days"])
        cluster = None                      # the open record for this subject; later qualifying windows that overlap it extend it
        for k in range(n - 1, len(eps)):
            win = eps[k - n + 1:k + 1]
            t0, t1 = (datetime.fromisoformat(win[0]["first_published"]), datetime.fromisoformat(win[-1]["first_published"]))
            if t1 - t0 > window:
                continue
            if cluster is not None and t0 <= datetime.fromisoformat(cluster["last"]):
                cluster["_eps"] = {e["incident_id"]: e for e in list(cluster["_eps"].values()) + win}
                cluster["last"], cluster["week"] = win[-1]["first_published"], win[-1]["week"]
            else:
                cluster = {"subject": subj, "week": win[-1]["week"], "first": win[0]["first_published"], "last": win[-1]["first_published"],
                           "_eps": {e["incident_id"]: e for e in win}}
                out.append(cluster)
    for c in out:
        eps_ = sorted(c.pop("_eps").values(), key=lambda e: e["first_published"])
        c["first"], c["episodes"] = eps_[0]["first_published"], len(eps_)
        last_t = datetime.fromisoformat(eps_[-1]["first_published"])
        c["episodes_in_final_window"] = sum(1 for e in eps_ if last_t - datetime.fromisoformat(e["first_published"]) <= window)
        c["evidence"] = [{"incident_id": e["incident_id"], "published": e["first_published"], "type": e["event_type"],
                          "headline": e["headline"], "independent_publishers": e["independent_publishers"]} for e in eps_]
    return sorted(out, key=lambda r: (r["week"], r["subject"]))


def binom_tail(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), computed in log space (n can be in the thousands)."""
    if k <= 0:
        return 1.0
    if k > n or not 0 < p < 1:
        return 0.0 if k > n else 1.0
    lp, lq = math.log(p), math.log1p(-p)
    logs = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq for i in range(k, n + 1)]
    top = max(logs)
    return min(1.0, math.exp(top) * sum(math.exp(x - top) for x in logs))


def emerging_terms(incidents: list[dict], weeks: list[date], eligible: dict[str, bool], params=PARAMS) -> list[dict]:
    """Terms/entities whose share of a week's incidents rises against a pooled trailing baseline of up to `baseline_weeks` ELIGIBLE
    weeks, subject to the minimum-evidence rule (count, independent publishers, distinct days, baseline size) and a strict tail
    probability. Unreliable weeks are neither tested nor used as baseline."""
    by_week: dict[str, list[dict]] = defaultdict(list)
    for i in incidents:
        if i["week"]:
            by_week[i["week"]].append(i)
    keys = [_iso(w) for w in weeks]
    out = []
    for idx, k in enumerate(keys):
        if not eligible.get(k):
            continue
        base = [b for b in keys[:idx] if eligible.get(b)][-params["baseline_weeks"]:]
        cur = by_week.get(k, [])
        n_cur = len(cur)
        n_base = sum(len(by_week.get(b, [])) for b in base)
        if len(base) < params["min_baseline_weeks"] or n_base < params["min_baseline_incidents"] or n_cur < params["min_week_incidents"]:
            continue
        base_counts = Counter(t for b in base for i in by_week.get(b, []) for t in set(i["terms"]))
        cur_inc: dict[str, list[dict]] = defaultdict(list)
        for i in cur:
            for t in set(i["terms"]):
                cur_inc[t].append(i)
        for term, inc in cur_inc.items():
            if len(inc) < params["min_term_incidents"]:
                continue
            pubs = {p for i in inc for p in i["publishers"]}
            days = {i["first_published"][:10] for i in inc}
            if len(pubs) < params["min_term_publishers"] or len(days) < params["min_term_days"]:
                continue
            p0 = (base_counts.get(term, 0) + 0.5) / (n_base + 1)
            ratio = (len(inc) / n_cur) / p0
            tail = binom_tail(len(inc), n_cur, p0)
            if ratio >= params["min_ratio"] and tail <= params["max_p"]:
                out.append({"week": k, "term": term, "incidents": len(inc), "week_incidents": n_cur,
                            "baseline_incidents_with_term": base_counts.get(term, 0), "baseline_incidents": n_base,
                            "baseline_weeks": base, "ratio": round(ratio, 1), "p": float(f"{tail:.2g}"),
                            "publishers": len(pubs), "days": len(days),
                            "evidence": [{"incident_id": i["incident_id"], "published": i["first_published"], "headline": i["headline"]}
                                         for i in sorted(inc, key=lambda x: x["first_published"])]})
    return sorted(out, key=lambda r: (r["week"], -r["ratio"], r["term"]))


# -- Orchestration ---------------------------------------------------------------------------------------------------------

def analyse(events: list[dict], weeks: list[date], *, volume: dict, reliability: dict, label: str) -> dict:
    """Trend measures for ONE set of events (all sources, or the constant-source subset) over `weeks`."""
    incidents = build_incidents(events)
    keys = [_iso(w) for w in weeks]
    eligible = {k: reliability[k]["reliable"] for k in keys}
    inc = [i for i in incidents if i["week"] in set(keys)]
    return {"basis": label, "events": len(events), "incidents": inc,
            "undated_incidents": sum(1 for i in incidents if i["week"] is None),
            "counts": incident_counts(inc, weeks), "restoration": restoration_durations(inc, weeks),
            "repeats": [r for r in repeat_disruptions(incidents) if r["week"] in set(keys)],
            "emerging": emerging_terms(inc, weeks, eligible)}


def _spans_change(week_a: str, week_b: str, changes=COVERAGE_CHANGES, used: list[str] | None = None) -> list[dict]:
    """Coverage changes that can confound a comparison running from week_a to week_b. A PERSISTENT change (rate, sources, timestamp,
    start) confounds any comparison it falls inside. A TRANSIENT one (an outage) confounds only the weeks it touches, and those weeks
    are excluded from baselines, so with `used` (the weeks actually compared) it matters only if it touches one of them. A change
    marked ``confounds: False`` is recorded but never confounds."""
    a, b = date.fromisoformat(week_a), date.fromisoformat(week_b) + timedelta(days=6)
    out = []
    for c in changes:
        if not c.get("confounds", True):
            continue
        if c["kind"] == "outage" and used is not None:
            hit = any(change_overlaps(c, date.fromisoformat(w), date.fromisoformat(w) + timedelta(days=6)) for w in used)
        else:
            hit = change_overlaps(c, a, b)
        if hit:
            out.append(c)
    return out


def build_trends(events: list[dict], *, window: tuple[str, str], data_start: str, data_end: str, force: bool = False,
                 changes=COVERAGE_CHANGES) -> dict:
    """The full longitudinal result for the complete weeks in `window` (inclusive Monday dates): coverage record, volume denominators,
    week reliability, the constant-source set, and the measures on both bases with confounding labels. Refuses to run unless the
    feature flag is on (or `force`)."""
    if not (force or enabled()):
        return {"enabled": False, "reason": f"{FLAG} is off", "method": METHOD_VERSION}
    ds, de = date.fromisoformat(data_start), date.fromisoformat(data_end)
    weeks = week_range(date.fromisoformat(window[0]), date.fromisoformat(window[1]))
    vol = volume_denominators(events, weeks)
    cov = coverage_record(events, weeks, data_start=ds, data_end=de, changes=changes)
    zero_days = derive_zero_collection_days(events, ds, de)
    for k, c in cov.items():
        c["zero_collection_days"] = [d for d, _ in zero_days if k <= d <= (date.fromisoformat(k) + timedelta(days=6)).isoformat()]
    rel = week_reliability(vol, cov, changes)
    const = constant_sources(events, weeks, changes=changes)
    cset = set(const["sources"])
    all_res = analyse(events, weeks, volume=vol, reliability=rel, label="all")
    const_res = analyse([e for e in events if e.get("source") in cset], weeks, volume=vol, reliability=rel, label="constant")
    const_vol = volume_denominators([e for e in events if e.get("source") in cset], weeks)
    const_terms = {(r["week"], r["term"]) for r in const_res["emerging"]}
    for r in all_res["emerging"]:
        spans = _spans_change(r["baseline_weeks"][0], r["week"], changes, used=[*r["baseline_weeks"], r["week"]])
        r["coverage_changes_in_span"] = [c["date"] for c in spans]
        r["holds_in_constant_sources"] = (r["week"], r["term"]) in const_terms
        r["label"] = ("coverage-confounded" if spans and not r["holds_in_constant_sources"]
                      else "supported-in-constant-sources" if r["holds_in_constant_sources"] else "all-sources-only")
    for r in const_res["emerging"]:
        spans = _spans_change(r["baseline_weeks"][0], r["week"], changes, used=[*r["baseline_weeks"], r["week"]])
        r["coverage_changes_in_span"] = [c["date"] for c in spans]
        r["label"] = "constant-sources" + (" (span contains a coverage change in a source outside the set)" if spans else "")
    const_repeat_keys = {(r["subject"], r["week"]) for r in const_res["repeats"]}
    all_repeat_keys = {(r["subject"], r["week"]) for r in all_res["repeats"]}
    for r in const_res["repeats"]:
        r["holds_in_all_sources"] = (r["subject"], r["week"]) in all_repeat_keys
        r["label"] = "constant-sources"
    for r in all_res["repeats"]:
        spans = _spans_change(_iso(week_start(datetime.fromisoformat(r["first"]))), r["week"], changes)
        r["coverage_changes_in_span"] = [c["date"] for c in spans]
        r["holds_in_constant_sources"] = (r["subject"], r["week"]) in const_repeat_keys
        r["label"] = ("coverage-confounded" if spans and not r["holds_in_constant_sources"]
                      else "supported-in-constant-sources" if r["holds_in_constant_sources"] else "all-sources-only")
    return {"enabled": True, "method": METHOD_VERSION, "params": PARAMS, "window": list(window),
            "data_range": [data_start, data_end], "weeks": [_iso(w) for w in weeks],
            "volume": vol, "constant_volume": const_vol, "coverage": cov, "reliability": rel, "constant_sources": const,
            "coverage_changes": list(changes), "zero_collection_days": zero_days, "known_broken": list(KNOWN_BROKEN),
            "silent_gaps_derived": derive_silent_gaps(events), "all": all_res, "constant": const_res}
