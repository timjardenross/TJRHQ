"""Cascading exposure view (OFFLINE, default OFF, not wired into any service, brief, schedule or portal registry).

Enabled only by ``CASCADING_EXPOSURE_ENABLED=1``, ``--enable`` or ``enabled=True``. No network, no database, no model.

Given (1) provider incidents detected in a recent-events export and (2) dependency records from
``dependency_evidence`` (``relation_basis`` documented | demonstrated_operational), it produces ONE product in the
same four-section shape as the other intelligence products (Confirmed evidence, Analytical inference, Potential
exposure, Unknowns) so the portal Products tab can show it without redesign.

Four evidence classes are kept apart and never merged or promoted:

  (a) documented            a vendor/registry DOCUMENT states the relationship        -> Potential exposure
  (b) demonstrated          an incident report EXPLICITLY states a downstream effect  -> Confirmed evidence
  (c) analytical inference  patterns/co-reports/trends computed from (a)/(b)/incident counts -> Analytical inference
  (d) unknowns              what was excluded, insufficient, unmeasured or not collected -> Unknowns

What each section may and may not claim is stated in ``SECTION_SCOPE`` and is printed in the product itself.

Reads: status-feed rows (incident detection, same code as the recurring-provider report) and optional context/news
rows (demonstrated statements, news-reported provider incidents). JSONL (optionally .gz): event_id, source_name,
published_at, collected_at, canonical_url, raw_title, raw_summary.

Usage:
    python cascading_exposure.py --enable --status status.jsonl --context news.jsonl --as-of 2026-11-24 --out-dir out
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dependency_evidence as de
import provider_disruption_report as pdr
from analytics_common import parse_ts
from product_common import clean_text, iso_week, load_rows, md_cell, short
from provider_failure import (
    build_incidents,
    detect_backfill_batches,
    is_status_source,
    provider_of,
    publication_gaps,
)

ENV_FLAG = "CASCADING_EXPOSURE_ENABLED"
PRODUCT_KEY = "cascading_exposure"
TITLE = "Cascading exposure"
DOCUMENTED_RECORDS_FILE = (
    HERE / "fixtures" / "cascade" / "documented_dependency_records.json"
)

POTENTIAL_LABEL = "potential exposure, not an observed impact"
RECENT_DAYS = 7  # incidents whose first report is this recent are "live or recent"
LOOKBACK_DAYS = 90
LATE_COLLECT_HOURS = (
    48  # an incident collected later than this after publication is not treated as live
)
PATTERN_DAYS = 30
PATTERN_MIN_STATEMENTS = 2
PATTERN_EPISODE_DAYS = (
    7  # same downstream+upstream pair within this many days is ONE statement
)
COINCIDENCE_HOURS = 36

# deteriorating-reliability read (recurring-provider thresholds are reused from provider_disruption_report)
TREND_RECENT_WEEKS = 4
TREND_MIN_PRIOR_WEEKS = 4
TREND_MIN_INCIDENTS = pdr.MIN_TREND_INCIDENTS
TREND_RATIO = pdr.TREND_RATIO
TREND_MAX_P = 0.05

SECTION_SCOPE = {
    "confirmed_evidence": (
        "MAY claim: this source reported that a failure at the named upstream provider caused impact at the named "
        "downstream party, on the stated date, in the quoted words. MAY NOT claim: that the effect was large, still "
        "continuing, general to the downstream's customers, or that any other organisation is affected; a news item is "
        "a report, not a provider confirmation."
    ),
    "analytical_inference": (
        "MAY claim: a computed read over reported incidents (repeat citation of one upstream, co-reporting, "
        "reported-incident-rate trend), labelled as inference with its thresholds. MAY NOT claim: causation, a "
        "dependency, a resilience ranking, or that a trend reflects provider quality (reporting practice differs)."
    ),
    "potential_exposure": (
        "MAY claim: a document says party X uses provider P, and P has a live or recent reported incident, so X is "
        "potentially exposed. MAY NOT claim: that X was affected, that the document's purpose matches the failed "
        "component, that X's service depends on P to operate, or that anyone outside the listed documents is exposed."
    ),
    "unknowns": (
        "MAY claim: what was found but excluded, what thresholds were not met, and what is not collected. MAY NOT be "
        "read as absence of risk: every item here is missing evidence, not evidence of safety."
    ),
}

DISCLAIMER = pdr.DISCLAIMER


def is_enabled(enabled=None):
    if enabled is not None:
        return bool(enabled)
    return os.environ.get(ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


# ------------------------------------------------------------------ provider identity


def provider_id(source_or_provider_name):
    """Canonical provider id from a feed/provider name using the dependency lexicon, else None. Never guesses."""
    name = provider_of(source_or_provider_name or "")
    name = re.sub(r"\s*\(.*?\)", "", name).strip()
    if name in de._ALIAS_TO_ID:
        return de._ALIAS_TO_ID[name]
    for alias in sorted(de._ALIAS_TO_ID, key=len, reverse=True):
        if name.lower() == alias.lower():
            return de._ALIAS_TO_ID[alias]
    return None


def _pub(row):
    return parse_ts(row.get("published_at"))


def _norm(title):
    t = clean_text(title).lower()
    t = re.sub(r"\s+[-|]\s+[^-|]{3,60}$", "", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# ------------------------------------------------------------------ documented records


def documented_records_from_fixtures(fixture_dir=None, observed_at="2026-11-24"):
    """Re-derive the 47 documented records from the vendored vendor-document fixtures (deterministic, offline)."""
    fx = Path(fixture_dir) if fixture_dir else HERE / "fixtures" / "dependency_evidence"
    spec = [
        (
            "anthropic_subprocessors.md",
            "Anthropic",
            "https://trust.anthropic.com/subprocessors",
        ),
        (
            "cloudflare_subprocessors.md",
            "Cloudflare",
            "https://www.cloudflare.com/gdpr/subprocessors/cloudflare-services/",
        ),
        (
            "openai_subprocessors.md",
            "OpenAI",
            "https://openai.com/policies/sub-processor-list/",
        ),
        (
            "supabase_subprocessors.md",
            "Supabase",
            "https://supabase.com/legal/subprocessor-list/June-1-2026.pdf",
        ),
        (
            "zoom_subprocessors.md",
            "Zoom",
            "https://www.zoom.com/en/trust/subprocessors/",
        ),
    ]
    out = []
    for fname, vendor, url in spec:
        res = de.extract_from_subprocessor_list(
            (fx / fname).read_text(), vendor, url, observed_at, enabled=True
        )
        out += res.records
    res = de.extract_from_vendor_prose(
        (fx / "notion_data_residency_excerpt.txt").read_text(),
        "Notion",
        "https://www.notion.com/help/data-residency",
        observed_at,
        enabled=True,
    )
    return out + res.records


def load_documented_records(path=None):
    p = Path(path) if path else DOCUMENTED_RECORDS_FILE
    data = json.loads(p.read_text(encoding="utf-8"))
    recs = data["records"] if isinstance(data, dict) else data
    bad = [r for r in recs if r.get("relation_basis") != de.BASIS_DOCUMENTED]
    if bad:
        raise ValueError(
            "documented record file may only hold relation_basis=documented records"
        )
    return recs


# ------------------------------------------------------------------ incidents (live or recent)


def detect_status_incidents(status_rows, as_of, recent_days=RECENT_DAYS):
    """Unplanned provider incidents first reported in the last ``recent_days`` (existing incident grouping).

    ``marked_resolved`` is whatever the feed text says; most feeds publish one row per incident, so an unmarked
    incident is NOT proven live. Incidents collected much later than published (bulk ingest) are excluded, counted.
    """
    start = as_of - timedelta(days=LOOKBACK_DAYS)
    rows = [
        r
        for r in status_rows
        if is_status_source(r.get("source_name"))
        and (p := _pub(r))
        and start <= p < as_of + timedelta(days=1)
    ]
    batches = detect_backfill_batches(rows)
    since = as_of - timedelta(days=recent_days)
    out, skipped_late = [], []
    for inc in build_incidents(rows):
        if (
            inc["schedule"] != "unplanned"
            or not inc["first_pub"]
            or not (since <= inc["first_pub"] <= as_of)
        ):
            continue
        in_batch = all(
            (e["source_name"], e["_col"].strftime("%Y-%m-%dT%H:%M")) in batches
            for e in inc["entries"]
            if e["_col"]
        )
        if (
            inc["collect_lag_h"] is not None
            and inc["collect_lag_h"] > LATE_COLLECT_HOURS
        ) or (in_batch and inc["entries"]):
            skipped_late.append(inc)
            continue
        e0 = inc["entries"][0]
        out.append(
            {
                "kind": "status_feed",
                "provider": inc["provider"],
                "provider_id": provider_id(inc["source"]),
                "first_pub": inc["first_pub"],
                "event_id": e0.get("event_id"),
                "title": clean_text(e0.get("raw_title")),
                "url": e0.get("canonical_url"),
                "marked_resolved": inc["resolved"],
            }
        )
    return sorted(
        out, key=lambda i: (i["provider"].lower(), i["first_pub"])
    ), skipped_late


_NEWS_OUTAGE_RE = re.compile(
    rf"(?P<b>{de._ALIAS})(?: [\w’'\-\.]+){{0,3}}? (?:outage|disruption|failure)s?"
)


def detect_news_incidents(rows, as_of, recent_days=RECENT_DAYS):
    """Provider outages REPORTED IN NEWS headlines (non-status sources). Lower grade than a status feed: a headline,
    not a provider statement. Hedged/negated headlines are dropped. One episode per provider per UTC day."""
    since = as_of - timedelta(days=recent_days)
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: _pub(r) or as_of):
        p = _pub(r)
        if is_status_source(r.get("source_name")) or not p or not (since <= p <= as_of):
            continue
        title = clean_text(r.get("raw_title"))
        if de.HEDGE_RE.search(title):
            continue
        for m in _NEWS_OUTAGE_RE.finditer(title):
            pid = de._ALIAS_TO_ID[m.group("b")]
            key = (pid, p.date())
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "kind": "news_headline",
                    "provider": pid,
                    "provider_id": pid,
                    "first_pub": p,
                    "event_id": r.get("event_id"),
                    "title": title,
                    "url": r.get("canonical_url"),
                    "source_name": r.get("source_name"),
                    "marked_resolved": None,
                }
            )
    return out


# ------------------------------------------------------------------ (a) potential exposure from documented records


PURPOSE_SERVICE_PATH = "hosting, delivery or processing purpose as documented"
PURPOSE_OTHER = "other documented purpose (for example support, communications, analytics, authentication)"
_SERVICE_PATH_RE = re.compile(
    r"hosting|infrastructure|content delivery|\bCDN\b|traffic routing|\bcompute\b|storage|real-time|"
    r"AI Gateway|processing|cloud service provider|intelligent features",
    re.IGNORECASE,
)


def purpose_hint(rec):
    """Keyword read of the document's OWN words: does the stated purpose sit in the service path (hosting, delivery,
    processing) or is it something else (support, communications). A hint for the reader, never a materiality score."""
    if rec["relation"] == de.REL_HOSTED_ON or _SERVICE_PATH_RE.search(
        rec["evidence_span"]
    ):
        return PURPOSE_SERVICE_PATH
    return PURPOSE_OTHER


def potential_exposure(incidents, documented, demonstrated=()):
    """For each upstream provider with a live/recent incident: parties that DOCUMENT it (record span + source)."""
    by_to = defaultdict(list)
    for rec in documented:
        if rec["relation_basis"] != de.BASIS_DOCUMENTED:
            raise ValueError("potential_exposure accepts documented records only")
        by_to[rec["provider_to"]].append(rec)
    demo_pairs = {(d["provider_from"], d["provider_to"]) for d in demonstrated}
    inc_by_provider = defaultdict(list)
    for inc in incidents:
        if inc["provider_id"]:
            inc_by_provider[inc["provider_id"]].append(inc)
    out = []
    for pid in sorted(inc_by_provider):
        deps = defaultdict(list)
        for rec in by_to.get(pid, []):
            if rec["provider_from"] != pid:
                deps[rec["provider_from"]].append(rec)
        out.append(
            {
                "upstream": pid,
                "label": POTENTIAL_LABEL,
                "incidents": inc_by_provider[pid],
                "dependents": [
                    {
                        "provider_from": frm,
                        "also_demonstrated": (frm, pid) in demo_pairs,
                        "records": [
                            {
                                "relation": r["relation"],
                                "evidence_span": r["evidence_span"],
                                "source_url": r["source_url"],
                                "source_class": r["source_class"],
                                "document_observed_at": r["observed_at"],
                                "purpose_hint": purpose_hint(r),
                            }
                            for r in sorted(
                                recs,
                                key=lambda x: purpose_hint(x) != PURPOSE_SERVICE_PATH,
                            )
                        ],
                    }
                    for frm, recs in sorted(deps.items())
                ],
            }
        )
    no_provider_id = sorted({i["provider"] for i in incidents if not i["provider_id"]})
    return out, no_provider_id


# ------------------------------------------------------------------ (b) demonstrated cascades


_HEAD_HIT_RE = re.compile(
    rf"^(?P<a>[^,:;]{{3,60}}?) (?:hit|hammered|disrupted|impacted|affected|stalled) by "
    rf"(?:the |an? )?(?:(?:major|global|widespread|massive) )*(?P<b>{de._ALIAS})(?: [\w’'\-\.]+){{0,3}}? "
    r"(?:outage|failure|incident|disruption)"
)


def _strip_publisher(title):
    return re.sub(r"\s+[-|]\s+[^-|]{3,60}$", "", clean_text(title))


def extract_demonstrated(rows, as_of, lookback_days=LOOKBACK_DAYS):
    """Demonstrated cascades: (1) the deterministic ``dependency_evidence`` incident extractor (named affected party in
    the same sentence, or a first-person sentence in the provider's own status feed); (2) a headline rule where the
    affected party is a GROUP as written ("UK banks hit by Google Cloud outage"), carried with the report's own
    summary as evidence and flagged ``affected_kind = group_as_written``. Returns (records, excluded)."""
    start = as_of - timedelta(days=lookback_days)
    sel = [r for r in rows if (p := _pub(r)) and start <= p <= as_of]
    res = de.extract_events(sel, enabled=True)
    records = [dict(r, affected_kind="named_provider") for r in res.records]
    have = {r["event_id"] for r in records}
    excluded = list(res.excluded)
    for r in sel:
        if r.get("event_id") in have:
            continue
        title = _strip_publisher(r.get("raw_title"))
        m = _HEAD_HIT_RE.match(title)
        if not m or de.HEDGE_RE.search(title):
            continue
        a_txt, b = m.group("a").strip(), de._ALIAS_TO_ID[m.group("b")]
        a_id = de._ALIAS_TO_ID.get(a_txt)
        if a_id == b:
            continue
        summary = clean_text(r.get("raw_summary"))
        span = f"{title}. {summary}".strip() if summary else title
        records.append(
            {
                "provider_from": a_id or a_txt,
                "provider_to": b,
                "relation": de.REL_DEPENDS_ON,
                "relation_basis": de.BASIS_DEMONSTRATED,
                "evidence_span": span,
                "source_url": r.get("canonical_url"),
                "source_class": de.CLASS_NEWS_INCIDENT,
                "observed_at": str(r.get("published_at")),
                "event_id": r.get("event_id"),
                "affected_kind": "named_provider" if a_id else "group_as_written",
            }
        )
    for rec in records:
        rec["date"] = (parse_ts(rec["observed_at"]) or as_of).date().isoformat()
    return sorted(records, key=lambda x: (x["date"], x["provider_from"])), excluded


def emerging_pattern(
    records, as_of, days=PATTERN_DAYS, min_statements=PATTERN_MIN_STATEMENTS
):
    """Same upstream named in >= ``min_statements`` SEPARATE downstream incident statements within ``days`` (demonstrated
    only). Statements by the same downstream about the same upstream within PATTERN_EPISODE_DAYS count once."""
    since = as_of - timedelta(days=days)
    by_up = defaultdict(list)
    for rec in records:
        if rec["relation_basis"] != de.BASIS_DEMONSTRATED:
            continue
        d = parse_ts(rec["observed_at"])
        if d and since <= d <= as_of:
            by_up[rec["provider_to"]].append((d, rec))
    out = []
    for up, items in sorted(by_up.items()):
        kept, last = [], {}
        for d, rec in sorted(items, key=lambda x: x[0]):
            k = rec["provider_from"]
            if k in last and (d - last[k]).days < PATTERN_EPISODE_DAYS:
                continue
            last[k] = d
            kept.append((d, rec))
        if len(kept) >= min_statements:
            out.append(
                {
                    "upstream": up,
                    "statements": len(kept),
                    "downstreams": sorted({r["provider_from"] for _, r in kept}),
                    "event_ids": [r.get("event_id") for _, r in kept],
                    "first": kept[0][0].date().isoformat(),
                    "last": kept[-1][0].date().isoformat(),
                }
            )
    return out


# ------------------------------------------------------------------ (c) inference: co-reports and coincidences


def co_reported(rows, as_of, records, lookback_days=LOOKBACK_DAYS):
    """A known provider and ANOTHER provider's outage in the same headline sentence with NO stated cause/effect
    ("Telstra's problems continue with Amazon Web Services outage"). Co-reporting only: relation not stated."""
    start = as_of - timedelta(days=lookback_days)
    have = {r.get("event_id") for r in records}
    out = []
    for r in rows:
        p = _pub(r)
        if not p or not (start <= p <= as_of) or r.get("event_id") in have:
            continue
        title = _strip_publisher(r.get("raw_title"))
        if de.HEDGE_RE.search(title):
            continue
        for m in _NEWS_OUTAGE_RE.finditer(title):
            b = de._ALIAS_TO_ID[m.group("b")]
            before = [
                de._ALIAS_TO_ID[x.group(0)]
                for x in de.ALIAS_RE.finditer(title[: m.start()])
            ]
            before = [a for a in before if a != b]
            if before:
                out.append(
                    {
                        "named_party": before[-1],
                        "outage_of": b,
                        "date": p.date().isoformat(),
                        "event_id": r.get("event_id"),
                        "span": title,
                        "source_name": r.get("source_name"),
                    }
                )
    return out


def temporal_coincidences(rows, as_of, excluded, lookback_days=LOOKBACK_DAYS):
    """An incident statement that blames an UNNAMED upstream but names one of that provider's products
    ("upstream provider affecting the Microsoft 365 connector") while a named provider outage is reported within
    +-COINCIDENCE_HOURS. Coincidence only: the statement itself does not name the upstream."""
    start = as_of - timedelta(days=lookback_days)
    out = []
    for ex in excluded:
        if ex["reason"] != "unnamed_upstream_provider":
            continue
        t0 = parse_ts(ex.get("observed_at"))
        if not t0 or not (start <= t0 <= as_of):
            continue
        named = {
            de._ALIAS_TO_ID[m.group(0)]
            for m in de.ALIAS_RE.finditer(ex["evidence_span"])
        }
        for r in rows:
            p = _pub(r)
            if (
                not p
                or abs((p - t0).total_seconds()) > COINCIDENCE_HOURS * 3600
                or r.get("event_id") == ex.get("event_id")
            ):
                continue
            title = _strip_publisher(r.get("raw_title"))
            if de.HEDGE_RE.search(title):
                continue
            for m in _NEWS_OUTAGE_RE.finditer(title):
                b = de._ALIAS_TO_ID[m.group("b")]
                if b in named:
                    out.append(
                        {
                            "statement_event_id": ex.get("event_id"),
                            "statement_span": ex["evidence_span"],
                            "statement_date": str(ex["observed_at"]),
                            "provider": b,
                            "report_event_id": r.get("event_id"),
                            "report_title": title,
                            "report_date": p.isoformat(),
                        }
                    )
    seen, uniq = set(), []
    for c in out:
        k = (c["statement_event_id"], c["report_event_id"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq


# ------------------------------------------------------------------ (c) inference: deteriorating provider reliability


def _binom_tail(k, n, p):
    """P(X >= k) for X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def _complete_weeks(start, as_of):
    """Monday-start ISO weeks lying fully inside [start, as_of]."""
    d = start.replace(hour=0, minute=0, second=0, microsecond=0)
    d += timedelta(days=(7 - d.weekday()) % 7)
    weeks = []
    while d + timedelta(days=7) <= as_of:
        weeks.append(d)
        d += timedelta(days=7)
    return weeks


def weekly_reliability_reads(status_rows, as_of):
    """Reported unplanned-incident counts per complete ISO week for feeds that meet the recurring-provider thresholds.

    Same thresholds as ``provider_disruption_report`` (>= 20 incidents, >= 10 ISO weeks, bulk share < 20%). Weeks that
    are coverage-confounded (a publication gap, or rows from a bulk-ingest batch published that week) are marked and
    EXCLUDED from the trend. Insufficient feeds get no figure. Never a ranking; feeds are alphabetical."""
    start = as_of - timedelta(days=LOOKBACK_DAYS)
    feeds, _ = pdr.analyse(status_rows, as_of)
    win_rows = [
        r
        for r in status_rows
        if is_status_source(r.get("source_name"))
        and (p := _pub(r))
        and start <= p < as_of
    ]
    batches = detect_backfill_batches(win_rows)
    incidents = build_incidents(win_rows)
    weeks = _complete_weeks(start, as_of)
    reads, insufficient = [], []
    for src in sorted(feeds, key=str.lower):
        f = feeds[src]
        if not f["sufficient"]:
            insufficient.append(
                {"feed": src, "unplanned": len(f["unplanned"]), "reasons": f["reasons"]}
            )
            continue
        gaps = publication_gaps([i for i in incidents if i["source"] == src], as_of)
        bulk_pubs = [
            _pub(r)
            for r in win_rows
            if r["source_name"] == src
            and r.get("collected_at")
            and (src, parse_ts(r["collected_at"]).strftime("%Y-%m-%dT%H:%M")) in batches
        ]
        series = []
        for w0 in weeks:
            w1 = w0 + timedelta(days=7)
            reasons = []
            if any(a < w1 and b > w0 for a, b in gaps):
                reasons.append(
                    "publication gap (no incident published for far longer than the feed's typical interval)"
                )
            if any(p and w0 <= p < w1 for p in bulk_pubs):
                reasons.append("bulk-ingest rows published this week")
            n = sum(1 for i in f["unplanned"] if w0 <= i["first_pub"] < w1)
            series.append({"week": iso_week(w0), "incidents": n, "confounded": reasons})
        clean = [s for s in series if not s["confounded"]]
        read = {
            "feed": src,
            "provider": f["provider"],
            "series": series,
            "confounded_weeks": [s["week"] for s in series if s["confounded"]],
            "label": "not assessed",
            "detail": "",
            "bulk_share": f["bulk_share"],
        }
        recent, prior = clean[-TREND_RECENT_WEEKS:], clean[:-TREND_RECENT_WEEKS]
        nr, npr = (
            sum(s["incidents"] for s in recent),
            sum(s["incidents"] for s in prior),
        )
        if len(recent) < TREND_RECENT_WEEKS or len(prior) < TREND_MIN_PRIOR_WEEKS:
            read["detail"] = (
                f"only {len(clean)} unconfounded complete weeks; needs {TREND_RECENT_WEEKS} recent plus "
                f">= {TREND_MIN_PRIOR_WEEKS} prior"
            )
        elif nr < TREND_MIN_INCIDENTS or npr < TREND_MIN_INCIDENTS:
            read["detail"] = (
                f"{nr} incidents in the last {len(recent)} unconfounded weeks vs {npr} in {len(prior)} earlier; "
                f"needs >= {TREND_MIN_INCIDENTS} in each"
            )
        else:
            rate_r, rate_p = nr / len(recent), npr / len(prior)
            ratio = rate_r / rate_p
            # conditional binomial: under no change, each of the nr+npr incidents falls in the recent block with
            # probability len(recent)/(len(recent)+len(prior)); two one-sided tails
            share = len(recent) / (len(recent) + len(prior))
            p_up = _binom_tail(nr, nr + npr, share)
            p_down = 1 - _binom_tail(nr + 1, nr + npr, share) if nr < nr + npr else 1.0
            if ratio >= TREND_RATIO and p_up <= TREND_MAX_P:
                read["label"] = "reported rate higher"
            elif ratio <= 1 / TREND_RATIO and p_down <= TREND_MAX_P:
                read["label"] = "reported rate lower"
            else:
                read["label"] = "reported rate about the same"
            read["detail"] = (
                f"{rate_r:.1f}/week over {len(recent)} recent unconfounded weeks vs {rate_p:.1f}/week over "
                f"{len(prior)} earlier; ratio {ratio:.2f}; one-sided p {min(p_up, p_down):.3f} "
                f"(label needs ratio >= {TREND_RATIO}x or <= {1 / TREND_RATIO:.2f}x and p <= {TREND_MAX_P})"
            )
        reads.append(read)
    return reads, insufficient


# ------------------------------------------------------------------ product assembly


def _rec_line(rec):
    who = rec["provider_from"] + (
        " (group, as written)" if rec.get("affected_kind") == "group_as_written" else ""
    )
    return (
        f"{rec['date']}: {who} affected by a failure at {rec['provider_to']} [demonstrated, {rec['source_class']}]. "
        f'Evidence span: "{short(rec["evidence_span"], 260)}" ({rec.get("event_id")}; {rec.get("source_url")})'
    )


def analyse(status_rows, context_rows, as_of, documented, recent_days=RECENT_DAYS):
    all_rows = list(status_rows) + list(context_rows)
    status_inc, late = detect_status_incidents(status_rows, as_of, recent_days)
    news_inc = detect_news_incidents(context_rows, as_of, recent_days)
    demonstrated, excluded = extract_demonstrated(all_rows, as_of)
    incidents = status_inc + news_inc
    exposure, no_pid = potential_exposure(incidents, documented, demonstrated)
    reads, insufficient = weekly_reliability_reads(status_rows, as_of)
    return {
        "as_of": as_of,
        "recent_days": recent_days,
        "status_incidents": status_inc,
        "news_incidents": news_inc,
        "late_collected": late,
        "demonstrated": demonstrated,
        "excluded": excluded,
        "pattern": emerging_pattern(demonstrated, as_of),
        "co_reported": co_reported(all_rows, as_of, demonstrated),
        "coincidences": temporal_coincidences(all_rows, as_of, excluded),
        "exposure": exposure,
        "no_provider_id": no_pid,
        "reliability": reads,
        "insufficient": insufficient,
        "documented_count": len(documented),
        "documented_vendors": sorted({r["provider_from"] for r in documented}),
    }


def _inc_line(i):
    resolved = {
        True: "marked resolved in feed text",
        False: "not marked resolved (liveness unverified)",
        None: "news headline",
    }[i["marked_resolved"]]
    return (
        f"{i['first_pub'].date()} {short(i['title'], 80)} ({i['event_id']}; {resolved})"
    )


def build_sections(a):
    asof = a["as_of"]
    confirmed = [f"[Scope] {SECTION_SCOPE['confirmed_evidence']}"]
    for rec in a["demonstrated"]:
        confirmed.append(_rec_line(rec))
    if not a["demonstrated"]:
        confirmed.append(
            "No demonstrated cascade statement was found in the 90-day export."
        )
    confirmed.append(
        f"Incident detection: {len(a['status_incidents'])} unplanned status-feed incidents and {len(a['news_incidents'])} "
        f"news-reported provider outages first reported in the last {a['recent_days']} days."
    )

    inference = [f"[Scope] {SECTION_SCOPE['analytical_inference']}"]
    if a["pattern"]:
        for p in a["pattern"]:
            inference.append(
                f"Emerging pattern (demonstrated statements only): {p['upstream']} named as the upstream in "
                f"{p['statements']} separate downstream incident statements {p['first']} to {p['last']} "
                f"(downstream: {', '.join(p['downstreams'])}; events {', '.join(str(e) for e in p['event_ids'])}). "
                f"Rule: >= {PATTERN_MIN_STATEMENTS} separate statements in {PATTERN_DAYS} days."
            )
    else:
        inference.append(
            f"Emerging pattern: none. No upstream is named in >= {PATTERN_MIN_STATEMENTS} separate downstream incident "
            f"statements within {PATTERN_DAYS} days of {asof.date()} (demonstrated statements only; documented "
            "relationships never count). This is a count over a sparse set, not a finding of no pattern."
        )
    for c in a["co_reported"]:
        inference.append(
            f'Co-reported only: {c["date"]} "{short(c["span"], 150)}" names {c["named_party"]} and an outage of '
            f"{c['outage_of']} without stating cause or effect ({c['event_id']}). Not demonstrated."
        )
    for c in a["coincidences"]:
        inference.append(
            f'Same-time coincidence: a statement blaming an unnamed upstream ("{short(c["statement_span"], 150)}", '
            f"{c['statement_event_id']}) falls within {COINCIDENCE_HOURS}h of a reported {c['provider']} outage "
            f'("{short(c["report_title"], 100)}", {c["report_event_id"]}). The statement does not name {c["provider"]}; '
            "not demonstrated."
        )
    for r in a["reliability"]:
        inference.append(
            f"{r['feed']}: {r['label']} ({r['detail']}). Confounded weeks excluded from the trend: "
            f"{', '.join(r['confounded_weeks']) or 'none'}. Bulk-ingest share {100 * r['bulk_share']:.0f}%. "
            f"{DISCLAIMER} Posting practice differs by provider."
        )
    if not a["reliability"]:
        inference.append(
            "Deteriorating provider reliability: no feed meets the minimum-evidence thresholds."
        )
    inference.append(
        "Feeds are listed alphabetically, never ranked. A rate read reflects what the source publishes."
    )

    exposure = [f"[Scope] {SECTION_SCOPE['potential_exposure']}"]
    for e in a["exposure"]:
        shown = sorted(e["incidents"], key=lambda i: i["first_pub"], reverse=True)[:3]
        incs = "; ".join(_inc_line(i) for i in shown)
        more = f" (+{len(e['incidents']) - 3} older)" if len(e["incidents"]) > 3 else ""
        head = f"Upstream {e['upstream']}: {len(e['incidents'])} live or recent reported incident(s), latest {incs}{more}. "
        if not e["dependents"]:
            exposure.append(
                head
                + f"No party in the {a['documented_count']} documented records names {e['upstream']}; nothing is listed."
            )
            continue
        exposure.append(
            head
            + f"Documented dependents below ({len(e['dependents'])}), each {POTENTIAL_LABEL}."
        )
        for d in e["dependents"]:
            r = d["records"][0]
            extra = (
                f" (+{len(d['records']) - 1} further record(s))"
                if len(d["records"]) > 1
                else ""
            )
            exposure.append(
                f"{d['provider_from']} documents {e['upstream']} ({r['relation']}; {r['purpose_hint']}) [{POTENTIAL_LABEL}]: "
                f'{r["source_class"]} observed {r["document_observed_at"]}: "{short(r["evidence_span"], 200)}" '
                f"({r['source_url']}){extra}."
                + (
                    " REPLAY: this document was fetched after the as-of date, so it is not what was known then."
                    if str(r["document_observed_at"])[:10] > asof.date().isoformat()
                    else ""
                )
                + (
                    " A demonstrated statement also exists for this pair."
                    if d["also_demonstrated"]
                    else ""
                )
            )
    if not a["exposure"]:
        exposure.append(
            "No provider with a live or recent incident is named in the documented records."
        )

    unknowns = [f"[Scope] {SECTION_SCOPE['unknowns']}"]
    unknowns.append(
        f"Documented relationships cover {len(a['documented_vendors'])} publishing vendors "
        f"({', '.join(a['documented_vendors'])}); every other provider has none, so absence from the exposure list "
        "is not absence of dependency."
    )
    unknowns.append(
        "Customer-side dependencies (which Australian organisations use which provider) are not in any record; no "
        "organisation-level exposure is stated."
    )
    unknowns.append(
        "A documented purpose is not matched to the failed component or region of an incident; exposure is provider-level only."
    )
    unknowns.append(
        "Liveness is unverified: feeds mostly publish one row per incident, so 'not marked resolved' is not 'ongoing'; "
        "no collector liveness signal exists. Microsoft, AWS and similar providers have no status feed collected, so "
        "their incidents appear only as news headlines."
    )
    if a["late_collected"]:
        unknowns.append(
            f"{len(a['late_collected'])} recent-window incidents were collected > {LATE_COLLECT_HOURS}h after "
            "publication or in a bulk-ingest batch and are not treated as live."
        )
    if a["no_provider_id"]:
        unknowns.append(
            "Incidents at providers outside the dependency lexicon (no documented record can exist): "
            + ", ".join(a["no_provider_id"])
            + "."
        )
    reasons = defaultdict(list)
    for ex in a["excluded"]:
        reasons[ex["reason"]].append(ex)
    for reason, items in sorted(reasons.items()):
        ex = items[0]
        unknowns.append(
            f'Excluded statements ({reason}): {len(items)}; e.g. "{short(ex["evidence_span"], 140)}" '
            f"({ex.get('event_id')}, {str(ex.get('observed_at'))[:10]})."
        )
    for i in a["insufficient"]:
        unknowns.append(
            f"{i['feed']}: insufficient evidence for a reliability read ({'; '.join(i['reasons'])}); not scored."
        )
    unknowns.append(
        "Recall of the demonstrated-statement extractor is unmeasured; the export is a 90-day sample with a "
        "keyword-prefiltered news set; statements phrased in other forms are missed."
    )
    return {
        "confirmed_evidence": confirmed,
        "analytical_inference": inference,
        "potential_exposure": exposure,
        "unknowns": unknowns,
    }


def render(a, sections, source_note):
    out = [
        f"# Cascading exposure view, generated {a['as_of'].date().isoformat()}",
        "",
        (
            f"Source: {source_note}. Window: {(a['as_of'] - timedelta(days=LOOKBACK_DAYS)).date()} to {a['as_of'].date()}; "
            f"live or recent = first reported in the last {a['recent_days']} days. Offline, read-only, default OFF, "
            "not wired into any service."
        ),
        "",
        (
            f"**{DISCLAIMER}** Documented relationships, demonstrated cascades, analytical inferences and unknowns "
            "are separate classes and are never merged or promoted."
        ),
        "",
    ]
    heads = {
        "confirmed_evidence": "Confirmed evidence (demonstrated cascades)",
        "analytical_inference": "Analytical inference",
        "potential_exposure": "Potential exposure (documented relationships, not observed impact)",
        "unknowns": "Unknowns",
    }
    for key, head in heads.items():
        out += [f"## {head}", ""] + [f"- {md_cell(x)}" for x in sections[key]] + [""]
    out += [
        "## Reported-incident weeks (for the reliability reads)",
        "",
        "| Feed | Week | Reported unplanned incidents | Confounded |",
        "|---|---|---|---|",
    ]
    for r in a["reliability"]:
        for s in r["series"]:
            out.append(
                f"| {r['feed']} | {s['week']} | {s['incidents']} | {md_cell('; '.join(s['confounded']) or '')} |"
            )
    out.append("")
    return "\n".join(out)


def build_product(
    status_rows,
    context_rows,
    as_of,
    source_note="events export (read-only SELECT)",
    documented=None,
    enabled=None,
    recent_days=RECENT_DAYS,
):
    """Portal-shaped product record (same keys as intel_products). Not registered in intel_products.PRODUCT_KEYS."""
    if not is_enabled(enabled):
        return None
    documented = documented if documented is not None else load_documented_records()
    a = analyse(status_rows, context_rows, as_of, documented, recent_days)
    sections = build_sections(a)
    n_exp = sum(len(e["dependents"]) for e in a["exposure"])
    sections["brief_findings"] = []
    sections["coverage_note"] = (
        "Potential exposure rests on vendor documents from "
        f"{len(a['documented_vendors'])} vendors only and states no observed impact. "
        + DISCLAIMER
    )
    return {
        "product_key": PRODUCT_KEY,
        "title": TITLE,
        "summary": f"{len(a['demonstrated'])} demonstrated cascade statements (90d); {n_exp} potential-exposure links for "
        f"{len(a['exposure'])} providers with recent incidents; {len(a['pattern'])} emerging patterns; "
        f"{sum(1 for r in a['reliability'] if r['label'] == 'reported rate higher')} feeds with a higher reported rate.",
        "sections": sections,
        "exceptions": [],  # never raises a decision on its own
        "body_md": render(a, sections, source_note),
        "analysis": a,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--status", action="append", default=[])
    ap.add_argument("--context", action="append", default=[])
    ap.add_argument(
        "--documented", default=None, help="JSON of documented dependency records"
    )
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--recent-days", type=int, default=RECENT_DAYS)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--enable", action="store_true")
    args = ap.parse_args(argv)
    if not is_enabled(args.enable or None):
        print(
            f"cascading_exposure is OFF (set {ENV_FLAG}=1 or pass --enable)",
            file=sys.stderr,
        )
        return 2
    status, context = load_rows(args.status), load_rows(args.context)
    as_of = parse_ts(
        args.as_of if not args.as_of or "T" in args.as_of else args.as_of + "T06:00:00Z"
    ) or datetime.now(timezone.utc)
    prod = build_product(
        status,
        context,
        as_of,
        "export files given on the command line",
        load_documented_records(args.documented),
        True,
        args.recent_days,
    )
    slim = {k: v for k, v in prod.items() if k not in ("body_md", "analysis")}
    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        day = as_of.date().isoformat()
        (out / f"{PRODUCT_KEY}-{day}.md").write_text(prod["body_md"], encoding="utf-8")
        (out / f"{PRODUCT_KEY}-{day}.json").write_text(
            json.dumps(slim, indent=1, default=str), encoding="utf-8"
        )
        print(f"wrote {PRODUCT_KEY} to {out}")
    else:
        print(prod["body_md"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
