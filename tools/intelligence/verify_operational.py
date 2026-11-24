#!/usr/bin/env python3
"""Operational verification for docs/INTELLIGENCE-CAPABILITY-CHECKLIST.md.

A capability is Operational only when it is running in production AND has been observed working. This command turns the
repetitive "observed working" queries into one repeatable run. It is read-only and never edits the checklist.

Workflow (no database credentials are needed by this tool):
    1. python3 tools/intelligence/verify_operational.py --print-sql            # SELECT-only statements, one per name
       (run each through the Supabase connector / psql and save the rows)
    2. save {"<query name>": [<row>, ...], ...} as results.json                 # key "_meta" is optional, see below
       (if a brief exists, also run the follow-up from:  --print-sql --results results.json)
    3. python3 tools/intelligence/verify_operational.py --results results.json [--json] [--deployed-at ISO]

Verdicts (per capability, from its checks):
    PASS                 every check passed and each carries evidence rows
    FAIL                 at least one check observed a defect
    NOT_YET_OBSERVABLE   evidence is missing, the code has not run in production yet, or the signature cannot occur yet
A check can only PASS with evidence rows; missing results, an empty export or evidence that predates the release can
never produce a PASS. 'Verified' (PASS) and 'not yet observable' are always listed separately.

Optional input (not in the database; supply when you have it):
    "deadman_journal": [{"line": "..."}]   from  journalctl -u intelligence-scheduler | grep -i 'deadman\\|MISSED BRIEF'
    "_meta": {"window_events_complete": false}   set when window_events was narrowed (see --subset)
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "platform-runtime")]

PASS, FAIL, NYO = "PASS", "FAIL", "NOT_YET_OBSERVABLE"
CHECKLIST = REPO / "docs" / "INTELLIGENCE-CAPABILITY-CHECKLIST.md"

# Code merged to main (release #717, 24 Nov 2026 17:26 AEDT). Evidence from before this moment says nothing about the new code.
DEFAULT_DEPLOYED_AT = "2026-11-24T06:26:32Z"
FIRECRAWL_CEILING = 1700            # intelligence/ingestion/external_fetch_budget.py
OLD_FEED_CAP, NVD_RUN_CAP = 20, 100  # intelligence/config.py: MAX_ITEMS_PER_SOURCE (old per-feed cap), NVD_MAX_ITEMS_PER_RUN
WINDOW_LIMIT = 3000
OK_RATIO_MIN = 0.90
PROVENANCE_COLUMNS = ("publisher_domain", "publisher_family")  # populated only once the provenance flag is on (others default)

# Authoritative sources: (label, registry name regex)
AUTHORITATIVE = [("ASIC News Centre", r"^ASIC News Centre$"), ("ASIC Enforcement Activity", r"^ASIC Enforcement Activity$"),
                 ("Optus National Outage Register", r"^Optus National Outage Register$"), ("RBA Media Releases", r"^RBA Media Releases$"),
                 ("ATO Online Services for Agents Status", r"^ATO Online Services for Agents"), ("OAIC", r"OAIC")]


# ── SQL (all SELECT-only) ──────────────────────────────────────────────────────────────────────────────────────
def build_queries(sweep_hour: int = 19, deployed_at: str = DEFAULT_DEPLOYED_AT, subset: bool = False) -> dict[str, str]:
    h = int(sweep_hour)
    sweep_days = (f"with d as (select (date_trunc('day', now() - interval '{h} hours') + interval '{h} hours') - (n * interval '1 day') s "
                  f"from generate_series(0,4) n)")
    summary_col = "''" if subset else "left(coalesce(e.raw_summary,''),300)"   # --subset also drops summaries to keep the export small
    where_subset = ("and (s.source_name ilike '%outage register%' or e.published_at < b.gen - make_interval(hours => b.h) "
                    "or e.raw_title ~* '(outage|down|disruption|breach|ransomware|cyber|attack|offline|failure|incident)') " if subset else "")
    return {
        "as_of": "select now() as as_of",
        "sweep_days": f"{sweep_days} select d.s as sweep_start, count(h.health_id) as checks, count(distinct h.source_id) as sources, "
                      f"count(h.health_id) filter (where h.status = 'ok') as ok, count(h.health_id) filter (where h.status <> 'ok') as not_ok "
                      f"from d left join intelligence_source_health h on h.checked_at >= d.s and h.checked_at < d.s + interval '3 hours' "
                      f"group by d.s order by d.s desc",
        "sweep_items": f"{sweep_days} select d.s as sweep_start, count(e.event_id) as items, count(distinct e.source_id) as sources "
                       f"from d left join intelligence_events e on e.collected_at >= d.s and e.collected_at < d.s + interval '3 hours' "
                       f"group by d.s order by d.s desc",
        "sweep_failures": f"with t as (select (date_trunc('day', now() - interval '{h} hours') + interval '{h} hours') s) "
                          f"select r.source_name, h.status, h.items_retrieved, h.content_valid, left(coalesce(h.error_message,''),120) as error "
                          f"from intelligence_source_health h join intelligence_source_registry r using (source_id), t "
                          f"where h.checked_at >= t.s and h.checked_at < t.s + interval '3 hours' and h.status <> 'ok' order by r.source_name limit 60",
        "heartbeats": "select checked_at, status, detail, left(coalesce(error_message,''),160) as error_message from domain_heartbeats "
                      "where domain_key = 'intelligence_collection' and checked_at > now() - interval '5 days' order by checked_at desc limit 40",
        "sources": "with h as (select source_id, count(*) filter (where checked_at > now() - interval '7 days') checks7, "
                   "count(*) filter (where checked_at > now() - interval '7 days' and status <> 'ok') bad7, "
                   "count(*) filter (where checked_at > now() - interval '72 hours') checks72, "
                   "count(*) filter (where checked_at > now() - interval '72 hours' and status = 'ok') ok72, "
                   "max(checked_at) last_check, max(checked_at) filter (where status = 'ok') last_ok "
                   "from intelligence_source_health where checked_at > now() - interval '14 days' group by 1), "
                   "lh as (select distinct on (source_id) source_id, status last_status, items_retrieved last_items, content_valid last_valid, "
                   "left(coalesce(error_message,''),100) last_error from intelligence_source_health where checked_at > now() - interval '14 days' "
                   "order by source_id, checked_at desc), "
                   "ev as (select source_id, count(*) filter (where collected_at > now() - interval '24 hours') n24, "
                   "count(*) filter (where collected_at > now() - interval '7 days') n7, count(*) n30, max(collected_at) last_event, "
                   "max(published_at) newest_pub from intelligence_events where collected_at > now() - interval '30 days' group by 1) "
                   "select s.source_name, s.source_type, s.category, s.active, s.updated_at, coalesce(h.checks7,0) checks7, coalesce(h.bad7,0) bad7, "
                   "coalesce(h.checks72,0) checks72, coalesce(h.ok72,0) ok72, h.last_check, h.last_ok, lh.last_status, lh.last_items, lh.last_valid, "
                   "lh.last_error, coalesce(ev.n24,0) n24, coalesce(ev.n7,0) n7, coalesce(ev.n30,0) n30, ev.last_event, ev.newest_pub "
                   "from intelligence_source_registry s left join h using (source_id) left join lh using (source_id) left join ev using (source_id) "
                   "order by s.active desc, s.source_name",
        "feed_health_post_deploy": f"select r.source_name, r.source_type, count(*) checks, max(h.items_retrieved) max_items, max(h.checked_at) last_check "
                                   f"from intelligence_source_health h join intelligence_source_registry r using (source_id) "
                                   f"where h.checked_at >= timestamptz '{deployed_at}' and r.source_type in ('rss','atom','json_feed','feed') "
                                   f"group by 1,2 order by max_items desc nulls last limit 20",
        "itnews_checks": f"select h.checked_at, h.status, h.items_retrieved from intelligence_source_health h join intelligence_source_registry r using (source_id) "
                         f"where r.source_name = 'iTnews' and h.checked_at >= least(timestamptz '{deployed_at}', now() - interval '24 hours') order by h.checked_at limit 100",
        "nvd_runs": "select date_trunc('minute', e.collected_at) as run_minute, count(*) items, count(distinct e.dedup_hash) distinct_hash, "
                    "count(distinct e.canonical_url) distinct_url, min(e.published_at) oldest_published, max(e.published_at) newest_published "
                    "from intelligence_events e join intelligence_source_registry s using (source_id) "
                    "where s.source_name ~* 'nvd|nist cve' and e.collected_at > now() - interval '10 days' group by 1 order by 1 desc limit 30",
        "nvd_totals": f"select count(*) total, count(distinct e.dedup_hash) distinct_hash, count(distinct e.canonical_url) distinct_url, "
                      f"count(*) filter (where e.collected_at >= timestamptz '{deployed_at}') post_deploy_items "
                      f"from intelligence_events e join intelligence_source_registry s using (source_id) "
                      f"where s.source_name ~* 'nvd|nist cve' and e.collected_at > now() - interval '10 days'",
        "provenance_days": "select date_trunc('day', collected_at) as collected_day, count(*) total, count(publisher_domain) publisher_domain, "
                           "count(publisher_family) publisher_family, count(published_at_basis) published_at_basis, "
                           "count(published_at_precision) published_at_precision, count(published_at_confidence) published_at_confidence "
                           "from intelligence_events where collected_at > now() - interval '7 days' group by 1 order by 1 desc",
        "briefs": "select brief_type, brief_date, generated_at, signals_count, evidence_window_hours, collection_caveat, length(brief_text) text_len "
                  "from captains_daily_briefs where generated_at > now() - interval '12 days' order by generated_at desc limit 60",
        "latest_morning_brief": "select brief_type, brief_date, generated_at, evidence_window_hours, collection_caveat, brief_text "
                                "from captains_daily_briefs where brief_type = 'morning' order by generated_at desc limit 1",
        "window_events": "with b as (select generated_at gen, coalesce(evidence_window_hours,24) h from captains_daily_briefs "
                         "where brief_type = 'morning' order by generated_at desc limit 1) "
                         f"select e.event_id, left(e.raw_title,200) raw_title, {summary_col} raw_summary, e.geography, e.collected_at, "
                         "e.published_at, e.suppressed, e.signal_status, s.source_name "
                         "from intelligence_events e join intelligence_source_registry s using (source_id), b "
                         "where e.collected_at >= b.gen - make_interval(hours => b.h) and e.collected_at <= b.gen "
                         + where_subset + f"order by e.collected_at desc limit {WINDOW_LIMIT}",
        "external_fetch_usage": "select provider, billing_cycle_start, billing_cycle_end, call_count, updated_at from external_fetch_usage "
                                "where billing_cycle_end >= current_date - 1 order by provider, billing_cycle_start desc limit 12",
    }


def followup_sql(results: dict) -> dict[str, str]:
    """Queries that depend on a first pass: events behind the brief's HIGH lines (so they can be matched to their source and dates)."""
    brief = (rows(results, "latest_morning_brief") or [{}])[0]
    keys = []
    for line in high_lines(brief.get("brief_text") or ""):
        key = _title_key(line)
        if key:
            keys.append("'%" + key.replace("'", "''").replace("%", "\\%").replace("_", "\\_") + "%'")
    if not keys:
        return {}
    return {"high_line_events": "select e.event_id, left(e.raw_title,200) raw_title, e.collected_at, e.published_at, e.suppressed, e.signal_status, s.source_name "
                                "from intelligence_events e join intelligence_source_registry s using (source_id) "
                                f"where e.collected_at > now() - interval '10 days' and e.raw_title ilike any (array[{', '.join(keys)}]) limit 100"}


# ── result handling ────────────────────────────────────────────────────────────────────────────────────────────
def _ts(v) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    try:
        d = datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _coerce_rows(value):
    """Rows as a list of dicts. Also accepts a JSON string, or a Supabase connector reply wrapped in <untrusted-data-...> tags."""
    if isinstance(value, str):
        m = re.search(r"<untrusted-data-[^>]*>\s*(.*?)\s*</untrusted-data-[^>]*>", value, re.DOTALL)
        value = json.loads(m.group(1) if m else value)
    return value if isinstance(value, list) else None


def rows(results: dict, name: str):
    """None when the query was not supplied (distinct from [] = supplied, zero rows)."""
    if name not in results:
        return None
    try:
        return _coerce_rows(results[name])
    except (ValueError, TypeError):
        return None


@dataclass
class Check:
    id: str
    title: str
    verdict: str
    detail: str
    evidence: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.verdict == PASS and not self.evidence:     # a PASS without evidence rows is never emitted
            self.verdict, self.detail = NYO, f"no evidence rows ({self.detail})"


def nyo(cid, title, detail, evidence=None):
    return Check(cid, title, NYO, detail, evidence or [])


def _missing(cid, title, *names):
    return nyo(cid, title, "results not supplied for: " + ", ".join(names) + " (run --print-sql)")


@dataclass
class Ctx:
    results: dict
    now: datetime
    deployed_at: datetime
    sweep_hour: int

    @property
    def last_sweep_start(self) -> datetime:
        s = self.now.replace(hour=self.sweep_hour, minute=0, second=0, microsecond=0)
        return s if s <= self.now else s - timedelta(days=1)


def _src(ctx: Ctx, pattern: str) -> list[dict]:
    return [r for r in rows(ctx.results, "sources") or [] if re.search(pattern, r.get("source_name") or "", re.IGNORECASE)]


# ── checks ─────────────────────────────────────────────────────────────────────────────────────────────────────
def check_sweep_ran(ctx: Ctx) -> Check:
    t = "Daily sweep ran at the scheduled hour (latest expected sweep)"
    days = rows(ctx.results, "sweep_days")
    if days is None:
        return _missing("sweep_ran", t, "sweep_days")
    start = ctx.last_sweep_start
    mine = [r for r in days if _ts(r.get("sweep_start")) == start]
    if not mine:
        return nyo("sweep_ran", t, f"no sweep_days row for expected sweep {start:%Y-%m-%d %H:%MZ}")
    r = mine[0]
    if int(r.get("checks") or 0) > 0:
        return Check("sweep_ran", t, PASS, f"{r['checks']} source health checks across {r['sources']} sources in the 3h after {start:%Y-%m-%d %H:%MZ}", [r])
    if ctx.now < start + timedelta(hours=3):
        return nyo("sweep_ran", t, f"sweep window {start:%H:%MZ}-{(start + timedelta(hours=3)):%H:%MZ} not finished or not started at as_of", [r])
    return Check("sweep_ran", t, FAIL, f"no source health rows in the 3h after the expected {start:%Y-%m-%d %H:%MZ} sweep", [r])


def check_heartbeat(ctx: Ctx) -> Check:
    t = "Sweep heartbeat (domain_heartbeats intelligence_collection) recorded ok"
    hb = rows(ctx.results, "heartbeats")
    if hb is None:
        return _missing("heartbeat", t, "heartbeats")
    start = ctx.last_sweep_start
    win = [r for r in hb if (d := _ts(r.get("checked_at"))) and start <= d < start + timedelta(hours=3)]
    bad = [r for r in win if r.get("status") != "ok"]
    if bad:
        return Check("heartbeat", t, FAIL, f"{len(bad)} non-ok heartbeat(s) in the sweep window", bad)
    if not win:
        return nyo("heartbeat", t, f"no heartbeat row in the sweep window starting {start:%Y-%m-%d %H:%MZ}")
    return Check("heartbeat", t, PASS, f"{len(win)} ok heartbeat(s) in the sweep window", win[:3])


def check_items_collected(ctx: Ctx) -> Check:
    t = "Items collected by the latest sweep"
    si = rows(ctx.results, "sweep_items")
    if si is None:
        return _missing("items_collected", t, "sweep_items")
    mine = [r for r in si if _ts(r.get("sweep_start")) == ctx.last_sweep_start]
    if not mine:
        return nyo("items_collected", t, "no sweep_items row for the latest expected sweep")
    n = int(mine[0].get("items") or 0)
    if n > 0:
        return Check("items_collected", t, PASS, f"{n} events from {mine[0].get('sources')} sources", mine)
    if ctx.now < ctx.last_sweep_start + timedelta(hours=3):
        return nyo("items_collected", t, "sweep window still open", mine)
    return Check("items_collected", t, FAIL, "sweep window closed with zero events collected", mine)


def check_source_health(ctx: Ctx) -> Check:
    t = "Per-source health ok in the latest sweep (priority sources must not fail)"
    days, fails, srcs = rows(ctx.results, "sweep_days"), rows(ctx.results, "sweep_failures"), rows(ctx.results, "sources")
    if days is None or fails is None:
        return _missing("source_health", t, "sweep_days", "sweep_failures")
    mine = [r for r in days if _ts(r.get("sweep_start")) == ctx.last_sweep_start]
    if not mine or not int(mine[0].get("checks") or 0):
        return nyo("source_health", t, "no health checks in the latest sweep window")
    from intelligence import source_effectiveness as se
    ev = se.load_evidence()
    checks, ok = int(mine[0]["checks"]), int(mine[0].get("ok") or 0)
    ratio = ok / checks
    prio = sorted({f["source_name"] for f in fails if se.is_priority(f["source_name"], ev)})
    detail = f"{ok}/{checks} checks ok ({ratio:.0%}); {len(fails)} non-ok"
    if srcs is not None and (ctx.results.get("_meta") or {}).get("sources_complete", True):
        detail += f"; {sum(1 for s in srcs if s.get('active'))} active sources registered"
    if prio:
        return Check("source_health", t, FAIL, detail + "; priority sources failing: " + ", ".join(prio), fails)
    if ratio < OK_RATIO_MIN:
        return Check("source_health", t, FAIL, detail + f"; below {OK_RATIO_MIN:.0%}", fails)
    return Check("source_health", t, PASS, detail + "; no priority source failing", mine + fails[:10])


def check_authoritative(ctx: Ctx, label: str, pattern: str) -> Check:
    cid, t = "auth:" + label, f"{label} delivers (active, last check ok, items collected)"
    if rows(ctx.results, "sources") is None:
        return _missing(cid, t, "sources")
    found = _src(ctx, pattern)
    if not found:
        return nyo(cid, t, "not in the registry export" + (" (OAIC: only judged when a registry row exists)" if label == "OAIC" else ""))
    verdicts = []
    for r in found:
        name = r["source_name"]
        ev = [{k: r.get(k) for k in ("source_name", "active", "checks72", "ok72", "last_check", "last_status", "last_items", "last_valid", "n24", "n7", "last_event", "last_error")}]
        if not r.get("active"):
            verdicts.append(Check(cid, name, NYO, f"{name}: inactive (activation pending)", ev))
        elif not int(r.get("checks72") or 0):
            upd = _ts(r.get("updated_at"))
            late = upd is not None and upd > ctx.last_sweep_start
            verdicts.append(Check(cid, name, NYO if late else FAIL,
                                  f"{name}: active but never checked in 72h" + (" (registry row changed after the last sweep: await next sweep)" if late else ""), ev))
        elif r.get("last_status") != "ok" or r.get("last_valid") is False:
            verdicts.append(Check(cid, name, FAIL, f"{name}: last check {r.get('last_status')} ({r.get('last_error') or 'no error text'}); {r.get('ok72')}/{r.get('checks72')} ok in 72h", ev))
        elif int(r.get("n7") or 0) == 0:
            verdicts.append(Check(cid, name, NYO, f"{name}: checks ok but no items collected in 7 days", ev))
        else:
            verdicts.append(Check(cid, name, PASS, f"{name}: {r.get('n7')} items in 7 days, last check ok", ev))
    return _combine(cid, t, verdicts)


def _combine(cid: str, title: str, parts: list[Check]) -> Check:
    verdict = FAIL if any(p.verdict == FAIL for p in parts) else NYO if any(p.verdict == NYO for p in parts) else PASS
    return Check(cid, title, verdict, "; ".join(p.detail for p in parts), [e for p in parts for e in p.evidence])


def check_firecrawl(ctx: Ctx) -> Check:
    t = f"Firecrawl usage within the {FIRECRAWL_CEILING} cycle ceiling"
    use = rows(ctx.results, "external_fetch_usage")
    if use is None:
        return _missing("firecrawl", t, "external_fetch_usage")
    today = ctx.now.date()
    cur = [r for r in use if r.get("provider") == "firecrawl" and str(r.get("billing_cycle_start"))[:10] <= str(today) < str(r.get("billing_cycle_end"))[:10]]
    if not cur:
        return nyo("firecrawl", t, "no firecrawl row for the billing cycle containing as_of")
    r, n = cur[0], int(cur[0].get("call_count") or 0)
    start, end = datetime.fromisoformat(str(r["billing_cycle_start"])[:10]).date(), datetime.fromisoformat(str(r["billing_cycle_end"])[:10]).date()
    elapsed, length = max((today - start).days, 1), (end - start).days
    projected = round(n / elapsed * length)
    upd = _ts(r.get("updated_at"))
    detail = f"{n}/{FIRECRAWL_CEILING} used, day {elapsed}/{length}, projected {projected}"
    if n > FIRECRAWL_CEILING:
        return Check("firecrawl", t, FAIL, detail + ": over ceiling", cur)
    if projected > FIRECRAWL_CEILING:
        return Check("firecrawl", t, FAIL, detail + ": projected to exceed the ceiling", cur)
    if upd is None or ctx.now - upd > timedelta(hours=48):
        return nyo("firecrawl", t, detail + "; counter not updated in 48h, so usage is not being metered live", cur)
    return Check("firecrawl", t, PASS, detail, cur)


def _nvd_post_deploy(ctx: Ctx):
    runs = rows(ctx.results, "nvd_runs")
    if runs is None:
        return None
    return [r for r in runs if (d := _ts(r.get("run_minute"))) and d >= ctx.deployed_at]


def check_nvd_volume(ctx: Ctx) -> Check:
    t = "NVD paged collection: volume after the release"
    post = _nvd_post_deploy(ctx)
    if post is None:
        return _missing("nvd_volume", t, "nvd_runs")
    if not post:
        return nyo("nvd_volume", t, f"no NVD run collected after the release ({ctx.deployed_at:%Y-%m-%d %H:%MZ}); next daily sweep is the first observation")
    big = [r for r in post if int(r.get("items") or 0) > NVD_RUN_CAP]
    if big:
        return Check("nvd_volume", t, FAIL, f"run exceeded the {NVD_RUN_CAP}-item per-run cap", big)
    if all(int(r.get("items") or 0) == 0 for r in post):
        return Check("nvd_volume", t, FAIL, "post-release run(s) stored zero NVD items", post)
    return Check("nvd_volume", t, PASS, f"{len(post)} post-release run(s); items per run {[int(r['items']) for r in post]} (cap {NVD_RUN_CAP}, previously {OLD_FEED_CAP})", post)


def check_nvd_duplicates(ctx: Ctx) -> Check:
    t = "NVD paged collection: no duplicate rows"
    tot = rows(ctx.results, "nvd_totals")
    if tot is None:
        return _missing("nvd_duplicates", t, "nvd_totals")
    if not tot or not int(tot[0].get("total") or 0):
        return nyo("nvd_duplicates", t, "no NVD rows exported")
    r = tot[0]
    dup_h, dup_u = int(r["total"]) - int(r["distinct_hash"]), int(r["total"]) - int(r["distinct_url"])
    if dup_h or dup_u:
        return Check("nvd_duplicates", t, FAIL, f"{dup_h} duplicate dedup_hash, {dup_u} duplicate canonical_url among {r['total']} rows", [r])
    if not int(r.get("post_deploy_items") or 0):
        return nyo("nvd_duplicates", t, f"no duplicates in {r['total']} rows, but none were collected after the release, so paging is untested", [r])
    return Check("nvd_duplicates", t, PASS, f"0 duplicates among {r['total']} rows ({r['post_deploy_items']} after the release)", [r])


def check_nvd_newest_first(ctx: Ctx) -> Check:
    t = "NVD paged collection: newest-first (each run stores recently published CVEs)"
    post = _nvd_post_deploy(ctx)
    if post is None:
        return _missing("nvd_newest", t, "nvd_runs")
    if not post:
        return nyo("nvd_newest", t, "no NVD run after the release")
    stale = [r for r in post if (n := _ts(r.get("newest_published"))) is None or _ts(r["run_minute"]) - n > timedelta(hours=72)]
    if stale:
        return Check("nvd_newest", t, FAIL, f"{len(stale)} post-release run(s) whose newest stored CVE is older than 72h (oldest-first slicing signature)", stale)
    return Check("nvd_newest", t, PASS, f"newest stored CVE within 72h of collection in all {len(post)} post-release run(s)", post)


def check_feed_ceiling(ctx: Ctx) -> Check:
    t = f"Larger feed limit observed (a feed returned more than the old {OLD_FEED_CAP}-item cap)"
    fh = rows(ctx.results, "feed_health_post_deploy")
    if fh is None:
        return _missing("feed_ceiling", t, "feed_health_post_deploy")
    big = [r for r in fh if int(r.get("max_items") or 0) > OLD_FEED_CAP]
    if big:
        return Check("feed_ceiling", t, PASS, f"{len(big)} feed(s) returned more than {OLD_FEED_CAP} items after the release", big[:5])
    return nyo("feed_ceiling", t, f"no feed returned more than {OLD_FEED_CAP} items since the release (max {max([int(r.get('max_items') or 0) for r in fh], default=0)}); not conclusive", fh[:3])


def check_sweep_history(ctx: Ctx) -> Check:
    t = "Daily sweep present on each of the last 3 expected days"
    days = rows(ctx.results, "sweep_days")
    if days is None:
        return _missing("sweep_history", t, "sweep_days")
    recent = sorted(days, key=lambda r: str(r.get("sweep_start")), reverse=True)
    if ctx.now < ctx.last_sweep_start + timedelta(hours=3):
        recent = [r for r in recent if _ts(r.get("sweep_start")) != ctx.last_sweep_start]   # window still open: judge completed sweeps
    recent = recent[:3]
    if len(recent) < 3:
        return nyo("sweep_history", t, f"only {len(recent)} completed sweep day(s) exported")
    missing = [r for r in recent if not int(r.get("checks") or 0)]
    if missing:
        return Check("sweep_history", t, FAIL, f"{len(missing)} of the last 3 sweeps have no health rows", recent)
    return Check("sweep_history", t, PASS, "health rows present for each of the last 3 sweeps", recent)


def check_itnews(ctx: Ctx) -> Check:
    t = "iTnews checked on the 90-minute media cadence after the release"
    ck = rows(ctx.results, "itnews_checks")
    if ck is None:
        return _missing("itnews", t, "itnews_checks")
    pts = sorted(d for r in ck if (d := _ts(r.get("checked_at"))) and d >= ctx.deployed_at)
    if len(pts) < 3:
        return nyo("itnews", t, f"{len(pts)} iTnews check(s) since the release; need 3 to see a cadence", ck[-3:])
    gaps = [(b - a).total_seconds() / 60 for a, b in pairwise(pts)]
    ev = [{"checks_since_release": len(pts), "max_gap_min": round(max(gaps)), "median_gap_min": round(sorted(gaps)[len(gaps) // 2])}]
    if max(gaps) > 120:
        return Check("itnews", t, FAIL, f"largest gap {max(gaps):.0f} min exceeds 120", ev)
    return Check("itnews", t, PASS, f"{len(pts)} checks since release, max gap {max(gaps):.0f} min", ev)


def check_source_states(ctx: Ctx) -> Check:
    t = "Source coverage states classify every real registry row (intelligence.source_effectiveness)"
    srcs = rows(ctx.results, "sources")
    if srcs is None:
        return _missing("source_states", t, "sources")
    meta = ctx.results.get("_meta") if isinstance(ctx.results.get("_meta"), dict) else {}
    if meta.get("sources_complete") is False:
        return nyo("source_states", t, "the sources export was narrowed (_meta.sources_complete=false): the full registry was not classified")
    if not srcs:
        return nyo("source_states", t, "empty source export")
    from intelligence import source_effectiveness as se
    ev = se.load_evidence()
    classified = se.classify_all(srcs, ev, ctx.now)
    real = classified[:len(srcs)]
    counts = se.summarise(classified)
    exc = se.material_exceptions(srcs, ev, ctx.now)
    detail = "states " + ", ".join(f"{k}={v}" for k, v in counts.items() if v) + (f"; material exceptions: {[e['source_name'] for e in exc]}" if exc else "; no material exceptions")
    bad = [c for c in real if c["state"] not in (se.HEALTHY, se.QUIET, se.UNVERIFIED, se.DEGRADED, se.BROKEN, se.UNCOVERED)]
    if bad:
        return Check("source_states", t, FAIL, "unclassifiable rows", bad)
    interesting = [c for c in real if c["state"] != se.HEALTHY][:12]
    return Check("source_states", t, PASS, detail, interesting or real[:3])


def check_provenance(ctx: Ctx) -> Check:
    t = "Provenance columns populated for new rows once the flag is on"
    days = rows(ctx.results, "provenance_days")
    if days is None:
        return _missing("provenance", t, "provenance_days")
    days = sorted(days, key=lambda r: str(r.get("collected_day")))
    on = [r for r in days if any(int(r.get(c) or 0) for c in PROVENANCE_COLUMNS)]
    if not on:
        tot = sum(int(r.get("total") or 0) for r in days)
        return nyo("provenance", t, f"no row in {tot} exported events carries {'/'.join(PROVENANCE_COLUMNS)}: the flag is off or the change is not live", days[-2:])
    first = _ts(on[0]["collected_day"])
    after = [r for r in days if (d := _ts(r.get("collected_day"))) and d > first]
    if not after:
        return nyo("provenance", t, "first populated day is the only day since activation; wait for a full day of new rows", on)
    bad = [r for r in after if any(int(r.get(c) or 0) < int(r["total"]) * 0.95 for c in PROVENANCE_COLUMNS)]
    if bad:
        return Check("provenance", t, FAIL, f"{len(bad)} day(s) after activation with <95% populated", bad)
    return Check("provenance", t, PASS, f"{len(after)} full day(s) after activation with >=95% populated", after)


# -- briefs --
def _expected_brief_date(ctx: Ctx) -> str:
    from intelligence import brief_reliability as br
    return br.brief_date_aest(ctx.now)


def _brief_rows(ctx: Ctx, btype="morning"):
    b = rows(ctx.results, "briefs")
    return None if b is None else [r for r in b if r.get("brief_type") == btype]


def check_brief_row(ctx: Ctx) -> Check:
    t = "Morning brief row stored for the expected date"
    b = _brief_rows(ctx)
    if b is None:
        return _missing("brief_row", t, "briefs")
    want = _expected_brief_date(ctx)
    mine = [r for r in b if str(r.get("brief_date"))[:10] == want]
    if mine and int(mine[0].get("text_len") or 0) > 0:
        return Check("brief_row", t, PASS, f"morning brief_date {want} stored at {mine[0].get('generated_at')}", mine[:1])
    local_hour = ctx.now.astimezone(timezone(timedelta(hours=10))).hour
    if local_hour < 8:
        return nyo("brief_row", t, f"no row for {want} yet; deadman fires at 08:00 local")
    return Check("brief_row", t, FAIL, f"no morning brief row for {want} after the 08:00 deadman time", [])


def check_deadman_quiet(ctx: Ctx) -> Check:
    t = "Deadman did not fire for a day that has a brief row"
    b = _brief_rows(ctx)
    j = rows(ctx.results, "deadman_journal")
    if b is None:
        return _missing("deadman_quiet", t, "briefs")
    if j is None:
        return nyo("deadman_quiet", t, "deadman_journal not supplied (journalctl is the only record of the deadman result; run: journalctl -u intelligence-scheduler --since '2 days ago' | grep -i 'deadman|MISSED BRIEF')")
    want = _expected_brief_date(ctx)
    lines = [str(r.get("line", r)) for r in j]
    fired = [ln for ln in lines if re.search(r"MISSED BRIEF|deadman:\s*alerted", ln, re.IGNORECASE)]
    have_row = any(str(r.get("brief_date"))[:10] == want for r in b)
    if fired and have_row:
        return Check("deadman_quiet", t, FAIL, f"deadman alerted although a brief row exists for {want}", [{"line": x} for x in fired[:5]])
    oks = [ln for ln in lines if re.search(r"deadman:\s*ok", ln, re.IGNORECASE)]
    if have_row and oks:
        return Check("deadman_quiet", t, PASS, f"brief row exists for {want}; journal shows deadman ok and no alert", [{"line": x} for x in oks[-2:]])
    return nyo("deadman_quiet", t, "no 'Brief deadman: ok' journal line for the date, so the quiet result is not evidenced")


def check_miss_exercised(ctx: Ctx) -> Check:
    t = "Missed-brief path exercised live (a miss was detected AND the next brief extended its lookback)"
    b = _brief_rows(ctx)
    if b is None:
        return _missing("miss_exercised", t, "briefs")
    dates = sorted({str(r.get("brief_date"))[:10] for r in b})
    if not dates:
        return nyo("miss_exercised", t, "no morning briefs exported")
    d0, d1 = datetime.fromisoformat(dates[0]).date(), datetime.fromisoformat(dates[-1]).date()
    gaps = [str(d0 + timedelta(days=i)) for i in range((d1 - d0).days + 1) if str(d0 + timedelta(days=i)) not in dates]
    if not gaps:
        return nyo("miss_exercised", t, f"no missed morning brief between {dates[0]} and {dates[-1]}: the path has not been exercised")
    j = rows(ctx.results, "deadman_journal")
    nxt = [r for r in b if str(r.get("brief_date"))[:10] > gaps[0]]
    nxt = sorted(nxt, key=lambda r: str(r.get("brief_date")))[:1]
    extended = bool(nxt) and int(nxt[0].get("evidence_window_hours") or 0) > 24
    alerted = bool(j) and any(re.search(r"MISSED BRIEF|deadman:\s*alerted", str(r.get("line", r)), re.IGNORECASE) for r in j)
    ev = [{"missed_dates": gaps}] + nxt
    if j is None:
        return nyo("miss_exercised", t, f"missed date(s) {gaps} observed but deadman_journal not supplied", ev)
    if extended and alerted:
        return Check("miss_exercised", t, PASS, f"miss on {gaps[0]} alerted; next brief window {nxt[0].get('evidence_window_hours')}h", ev)
    return Check("miss_exercised", t, FAIL, f"miss on {gaps[0]}: alerted={alerted}, next brief extended={extended}", ev)


def high_lines(text: str) -> list[str]:
    return [ln.strip()[1:].strip() for ln in text.splitlines() if ln.strip().startswith("\U0001F534")]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip().lower().rstrip("…. ")


def _title_key(line: str) -> str:
    tail = _norm(line).split(": ", 1)[-1]
    return tail[:40].strip()


def _brief_and_events(ctx: Ctx):
    lb, we = rows(ctx.results, "latest_morning_brief"), rows(ctx.results, "window_events")
    if lb is None or we is None:
        return None
    return lb[0] if lb else None, we


def _predates(ctx: Ctx, brief: dict) -> bool:
    g = _ts(brief.get("generated_at"))
    return g is not None and g < ctx.deployed_at


def _gate(ctx: Ctx, brief: dict, c: Check) -> Check:
    """Evidence from a brief generated before the release says nothing about the new code: never a PASS or FAIL for it."""
    if _predates(ctx, brief) and c.verdict != NYO:
        return Check(c.id, c.title, NYO, f"brief generated {_ts(brief['generated_at']):%Y-%m-%d %H:%MZ}, before the release; assess the next brief. (Informational: {c.verdict} - {c.detail})", c.evidence)
    return c


def check_window_wording(ctx: Ctx) -> Check:
    t = "Daily brief states its evidence window ('Based on reports from the last N hours')"
    lb = rows(ctx.results, "latest_morning_brief")
    if lb is None:
        return _missing("brief_window", t, "latest_morning_brief")
    if not lb:
        return nyo("brief_window", t, "no morning brief")
    b = lb[0]
    m = re.search(r"Based on reports from the last (\d+) hours", b.get("brief_text") or "")
    ev = [{"brief_date": b.get("brief_date"), "generated_at": b.get("generated_at"), "evidence_window_hours": b.get("evidence_window_hours"),
           "wording": m.group(0) if m else None}]
    if m and int(m.group(1)) == int(b.get("evidence_window_hours") or m.group(1)):
        c = Check("brief_window", t, PASS, f"'{m.group(0)}' present and matches the stored window", ev)
    else:
        c = Check("brief_window", t, FAIL, "evidence-window sentence absent or differs from evidence_window_hours", ev)
    return _gate(ctx, b, c)


def _replay(ctx: Ctx, brief: dict, events: list[dict]):
    from intelligence import brief_evidence as be
    gen, hours = _ts(brief["generated_at"]), int(brief.get("evidence_window_hours") or 24)
    pool = [e for e in events if not e.get("suppressed") and e.get("signal_status") != "DUPLICATE"
            and (c := _ts(e.get("collected_at"))) and gen - timedelta(hours=hours) <= c <= gen]

    def sb_get(_table, _query):
        return [{"event_id": e["event_id"], "raw_title": e.get("raw_title"), "raw_summary": e.get("raw_summary"), "geography": e.get("geography"),
                 "collected_at": e.get("collected_at"), "published_at": e.get("published_at"), "canonical_url": e.get("canonical_url"),
                 "intelligence_source_registry": {"source_name": e.get("source_name")}} for e in pool]
    kept = be.load_events(sb_get, hours=hours, limit=WINDOW_LIMIT, now=gen)
    retro = [e for e in pool if be._retrospective_import(e.get("source_name") or "", e.get("published_at"), gen, hours)]
    return be, gen, hours, pool, kept, retro


def check_historical_guard(ctx: Ctx) -> Check:
    t = "Historical-import guard: register and old items absent from the V1 view and OTHER SIGNALS (load_events replay)"
    pair = _brief_and_events(ctx)
    if pair is None:
        return _missing("hist_guard", t, "latest_morning_brief", "window_events")
    brief, events = pair
    if not brief:
        return nyo("hist_guard", t, "no morning brief")
    try:
        be, gen, hours, pool, kept, retro = _replay(ctx, brief, events)
    except Exception as exc:  # noqa: BLE001 - replay depends on repo modules; report, never PASS
        return nyo("hist_guard", t, f"replay unavailable: {exc}")
    retro_ids = {str(e["event_id"]) for e in retro}
    leaked = [k for k in kept if k["id"] in retro_ids or be._retrospective_import(k["source"], k["published_at"], gen, hours)]
    text = _norm(brief.get("brief_text") or "")
    shown = [{"source_name": e.get("source_name"), "title": e.get("raw_title"), "published_at": e.get("published_at")}
             for e in retro if len(_norm(e.get("raw_title"))) >= 20 and _norm(e["raw_title"])[:50] in text]
    if leaked or shown:
        ev = [{"replay_leaked": k["title"]} for k in leaked[:5]] + shown[:5]
        return _gate(ctx, brief, Check("hist_guard", t, FAIL, f"{len(leaked)} retrospective row(s) survive load_events; {len(shown)} appear in the stored brief text", ev))
    if not retro:
        return nyo("hist_guard", t, f"no historical-import row inside the brief window ({len(pool)} rows replayed): nothing for the guard to exclude yet")
    ev = [{"replayed_rows": len(pool), "retrospective_rows": len(retro), "kept_after_guard": len(kept)}] + \
         [{"source_name": e.get("source_name"), "title": (e.get("raw_title") or "")[:80], "published_at": e.get("published_at")} for e in retro[:5]]
    return _gate(ctx, brief, Check("hist_guard", t, PASS, f"{len(retro)} retrospective row(s) in the window all excluded by load_events and absent from the brief text", ev))


def check_false_live(ctx: Ctx) -> Check:
    t = "No HIGH line in the brief is a retrospective/old item presented as live"
    lb, hl, we = rows(ctx.results, "latest_morning_brief"), rows(ctx.results, "high_line_events"), rows(ctx.results, "window_events")
    if lb is None:
        return _missing("false_live", t, "latest_morning_brief")
    if not lb:
        return nyo("false_live", t, "no morning brief")
    b = lb[0]
    lines = high_lines(b.get("brief_text") or "")
    ev0 = [{"brief_date": b.get("brief_date"), "high_lines": len(lines)}]
    if not lines:
        return _gate(ctx, b, Check("false_live", t, PASS, "brief contains no HIGH lines", ev0))
    if hl is None and we is None:
        return _missing("false_live", t, "high_line_events (see --print-sql --results)")
    from intelligence import brief_evidence as be
    gen, hours = _ts(b["generated_at"]), int(b.get("evidence_window_hours") or 24)
    pool = (hl or []) + (we or [])
    verdict_rows, unmatched, retro = [], [], []
    for ln in lines:
        key = _title_key(ln)
        m = [e for e in pool if key and (key in _norm(e.get("raw_title")) or _norm(e.get("raw_title"))[:40] in _norm(ln))]
        if not m:
            unmatched.append(ln)
            verdict_rows.append({"line": ln[:90], "match": None})
            continue
        old = [e for e in m if be._retrospective_import(e.get("source_name") or "", e.get("published_at"), gen, hours)]
        (retro if len(old) == len(m) else []).append(ln)
        verdict_rows.append({"line": ln[:90], "source_name": m[0].get("source_name"), "published_at": m[0].get("published_at"), "retrospective": len(old) == len(m)})
    if retro:
        return _gate(ctx, b, Check("false_live", t, FAIL, f"{len(retro)} HIGH line(s) are retrospective items shown as live", verdict_rows))
    if unmatched:
        return _gate(ctx, b, nyo("false_live", t, f"{len(unmatched)} of {len(lines)} HIGH line(s) could not be matched to an exported event; cannot confirm they are current", verdict_rows))
    return _gate(ctx, b, Check("false_live", t, PASS, f"all {len(lines)} HIGH line(s) match events published inside the window from non-register sources", verdict_rows))


def check_urgent(ctx: Ctx) -> Check:
    t = "'URGENT TO VERIFY' appears only when an incident qualifies (replay of build_evidence)"
    pair = _brief_and_events(ctx)
    if pair is None:
        return _missing("urgent", t, "latest_morning_brief", "window_events")
    brief, events = pair
    if not brief:
        return nyo("urgent", t, "no morning brief")
    meta = ctx.results.get("_meta") if isinstance(ctx.results.get("_meta"), dict) else {}
    complete = bool(meta.get("window_events_complete", len(events) < WINDOW_LIMIT))
    try:
        be, gen, hours, _pool, kept, _retro = _replay(ctx, brief, events)
        ev = be.build_evidence(kept, now=gen, window_hours=hours)
    except Exception as exc:  # noqa: BLE001
        return nyo("urgent", t, f"replay unavailable: {exc}")
    qual = [i for i in ev.incidents if i.urgent_verify]
    present = "URGENT TO VERIFY" in (brief.get("brief_text") or "")
    info = [{"in_brief": present, "qualifying_incidents_in_replay": len(qual), "replayed_events": len(kept), "window_complete": complete}] + \
           [{"incident": i.incident_id, "headline": i.headline[:90]} for i in qual[:3]]
    if present and not qual:
        c = Check("urgent", t, FAIL if complete else NYO, "URGENT TO VERIFY is in the brief but no replayed incident qualifies" + ("" if complete else " (window export incomplete)"), info)
    elif qual and not present:
        c = Check("urgent", t, FAIL, f"{len(qual)} incident(s) qualify but the brief has no URGENT TO VERIFY section", info)
    elif not complete:
        c = nyo("urgent", t, "brief and replay agree on the subset, but the window export was narrowed (--subset), so absence cannot be confirmed", info)
    else:
        c = Check("urgent", t, PASS, "URGENT TO VERIFY " + ("present and a replayed incident qualifies" if present else "absent and no replayed incident qualifies"), info)
    return _gate(ctx, brief, c)


# ── capability map ─────────────────────────────────────────────────────────────────────────────────────────────
def _auth_checks(ctx):
    return [check_authoritative(ctx, lab, pat) for lab, pat in AUTHORITATIVE]


def _rollup_sources(ctx: Ctx) -> Check:
    parts = [c for c in _auth_checks(ctx) if not c.id.endswith("OAIC") or c.verdict != NYO]
    t = "New sources activated and collecting (ASIC, Optus register, RBA, ATO agents, OAIC if active)"
    return _combine("new_sources", t, parts) if parts else nyo("new_sources", t, "no sources")


# (capability, checks builder, covers_all_remaining, what stays open even when every check passes)
CAPABILITIES = [
    ("Discovery and collection",
     lambda c: [check_sweep_ran(c), check_heartbeat(c), check_items_collected(c), check_source_health(c), check_feed_ceiling(c),
                check_nvd_volume(c), check_nvd_duplicates(c), check_nvd_newest_first(c), _rollup_sources(c)], True, ""),
    ("Authoritative Australian and international sources",
     lambda c: _auth_checks(c) + [check_firecrawl(c)], False,
     "ATO business and PLS status pages still to add; no authoritative Telstra, ASX or ACMA collection method"),
    ("Collection reliability and timeliness",
     lambda c: [check_sweep_history(c), check_itnews(c), check_nvd_volume(c), check_nvd_newest_first(c), check_source_states(c)], True, ""),
    ("Daily executive brief",
     lambda c: [check_brief_row(c), check_window_wording(c), check_false_live(c), check_urgent(c), check_historical_guard(c)], True, ""),
    ("Missed-brief detection and recovery",
     lambda c: [check_brief_row(c), check_deadman_quiet(c), check_miss_exercised(c)], True, ""),
    ("Provenance and verified freshness",
     lambda c: [check_provenance(c)], False, "database change approval and activation are decisions, not observations"),
]


@dataclass
class CapResult:
    name: str
    verdict: str
    checks: list[Check]
    covers_all: bool
    open_note: str
    current: str = "?"


def evaluate(results: dict, *, now: datetime, deployed_at: datetime, sweep_hour: int = 19, current: dict | None = None) -> list[CapResult]:
    ctx = Ctx(results, now, deployed_at, sweep_hour)
    out = []
    for name, build, covers, note in CAPABILITIES:
        try:
            checks = build(ctx)
        except Exception as exc:  # noqa: BLE001 - one malformed export must not hide the other capabilities
            checks = [nyo("error", "evaluation error", f"{type(exc).__name__}: {exc}")]
        verdict = FAIL if any(c.verdict == FAIL for c in checks) else NYO if any(c.verdict == NYO for c in checks) else PASS
        out.append(CapResult(name, verdict, checks, covers, note, (current or {}).get(name, "?")))
    return out


def read_checklist(path: Path = CHECKLIST) -> dict[str, str]:
    cur = {}
    try:
        for ln in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\|\s*([^|]+?)\s*\|\s*(Operational|Partial|Outstanding)\s*\|", ln)
            if m:
                cur[m.group(1)] = m.group(2)
    except OSError:
        pass
    return cur


def propose(r: CapResult) -> tuple[str, str]:
    """(proposed status, evidence sentence). Never edits the checklist; PASS is the only route to 'Operational'."""
    bad = [c for c in r.checks if c.verdict == FAIL]
    wait = [c for c in r.checks if c.verdict == NYO]
    good = [c for c in r.checks if c.verdict == PASS]
    if r.verdict == PASS and r.covers_all:
        return "Operational", "; ".join(f"{c.title}: {c.detail}" for c in good)
    if r.verdict == PASS:
        return "Partial", "verified: " + "; ".join(c.detail for c in good) + f". Still open: {r.open_note}"
    if r.verdict == FAIL:
        status = "Partial" + (" (regression from Operational)" if r.current == "Operational" else "")
        return status, "blocking: " + "; ".join(f"{c.title}: {c.detail}" for c in bad)
    return f"{r.current if r.current != '?' else 'Partial'} (no change)", "not yet observable: " + "; ".join(f"{c.title}: {c.detail}" for c in wait)


# ── output ─────────────────────────────────────────────────────────────────────────────────────────────────────
def render(res: list[CapResult], now: datetime, deployed_at: datetime, max_evidence: int = 4) -> str:
    out = [f"OPERATIONAL VERIFICATION  as_of {now:%Y-%m-%d %H:%M:%SZ}  release boundary {deployed_at:%Y-%m-%d %H:%MZ}", ""]
    groups = {PASS: [], FAIL: [], NYO: []}
    for r in res:
        groups[r.verdict].append(r)
    out += [f"VERIFIED (PASS, evidenced): {len(groups[PASS])}"] + [f"  + {r.name}" for r in groups[PASS]] or []
    out += [f"FAIL (defect observed): {len(groups[FAIL])}"] + [f"  ! {r.name}" for r in groups[FAIL]]
    out += [f"NOT YET OBSERVABLE: {len(groups[NYO])}"] + [f"  ? {r.name}" for r in groups[NYO]] + [""]
    for r in res:
        out.append(f"== {r.name}: {r.verdict}  (checklist: {r.current})")
        for c in r.checks:
            out.append(f"  [{c.verdict}] {c.title}")
            out.append(f"      {c.detail}")
            for e in c.evidence[:max_evidence]:
                out.append("      evidence: " + json.dumps(e, default=str, ensure_ascii=False)[:260])
            if len(c.evidence) > max_evidence:
                out.append(f"      ... {len(c.evidence) - max_evidence} more evidence row(s)")
        out.append("")
    out.append("CHECKLIST UPDATE (ready to paste; the checklist itself is not edited)")
    for r in res:
        status, ev = propose(r)
        out.append(f"- {r.name} | proposed: {status} | evidence: {ev}")
    return "\n".join(out)


def to_json(res: list[CapResult], now, deployed_at) -> dict:
    return {"as_of": now.isoformat(), "release_boundary": deployed_at.isoformat(),
            "capabilities": [{"capability": r.name, "verdict": r.verdict, "current_status": r.current, "proposed_status": propose(r)[0], "evidence_summary": propose(r)[1],
                              "checks": [{"id": c.id, "title": c.title, "verdict": c.verdict, "detail": c.detail, "evidence": c.evidence} for c in r.checks]} for r in res]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--print-sql", action="store_true", help="print the SELECT statements (with --results: also the dependent follow-up queries)")
    ap.add_argument("--subset", action="store_true", help="with --print-sql: narrow window_events to retrospective rows and incident keywords (then set _meta.window_events_complete=false)")
    ap.add_argument("--results", help="JSON file: {query name: [rows]}")
    ap.add_argument("--deployed-at", default=DEFAULT_DEPLOYED_AT, help="release boundary (UTC ISO); evidence before it never counts for new code")
    ap.add_argument("--now", help="override as_of (UTC ISO); default results.as_of[0].as_of, else the wall clock")
    ap.add_argument("--sweep-hour-utc", type=int, default=19, help="daily sweep hour in UTC (06:00 Melbourne = 19 in daylight saving, 20 otherwise)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-evidence", type=int, default=4)
    a = ap.parse_args(argv)
    dep = _ts(a.deployed_at)
    if dep is None:
        print("bad --deployed-at", file=sys.stderr)
        return 2
    if a.print_sql:
        q = build_queries(a.sweep_hour_utc, a.deployed_at, a.subset)
        if a.results:
            q = followup_sql(json.loads(Path(a.results).read_text(encoding="utf-8")))
        for name, sql in q.items():
            print(f"-- name: {name}\n{sql};\n")
        return 0
    if not a.results:
        ap.error("--results or --print-sql is required")
    results = json.loads(Path(a.results).read_text(encoding="utf-8"))
    asof = (rows(results, "as_of") or [{}])[0].get("as_of")
    now = _ts(a.now) or _ts(asof) or datetime.now(timezone.utc)
    res = evaluate(results, now=now, deployed_at=dep, sweep_hour=a.sweep_hour_utc, current=read_checklist())
    print(json.dumps(to_json(res, now, dep), indent=2, default=str) if a.json else render(res, now, dep, a.max_evidence))
    return 1 if any(r.verdict == FAIL for r in res) else 0


if __name__ == "__main__":
    sys.exit(main())
