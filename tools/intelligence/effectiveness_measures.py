#!/usr/bin/env python3
"""Intelligence effectiveness measures (read-only, offline, not scheduled, no write path, never connects to a database).

Pattern of ``verify_operational.py``: this tool prints SELECT-only SQL, you run each statement through a read-only
connector and save the rows, then it computes the measures from the saved rows.

    python3 tools/intelligence/effectiveness_measures.py --print-sql                 # all statements, labelled
    python3 tools/intelligence/effectiveness_measures.py --print-sql funnel          # one statement
    python3 tools/intelligence/effectiveness_measures.py --results results.json --out-json m.json --out-md m.md

``results.json`` is ``{"<query name>": [<row>, ...]}``. Rows are objects (column -> value); the two reference-set recall
queries return ``row`` JSON arrays as in ``reference_set_v3_measure.py`` (either ``{"row": [...]}`` or a bare array).
Chunked queries (``recall_detection_0`` ...) are merged by prefix. A measure whose rows are missing is reported as
NOT_MEASURED, never estimated.

Measures
    funnel            items fetched, new events, mission RELEVANT for one sweep window, with "briefed" reported by path (see BRIEFED_DEFINITION);
                      items to events is NOT a conversion rate
    selection_recall  reference set v3, operational-disruption records: how many reached a brief (frame, not a score)
    health_vs_effect  zero-item "ok" sources, invalid-content sources, active sources absent from the sweep (TIER_1 flagged)
    duplicate_rows    P0-28 duplicate-row check over briefs, products, events and the registry
    replay            RS-062 / RS-079 / RS-081 replayed through the CURRENT incident clustering and delivery tiers (offline)
    brief_duplication mentions / distinct incident ids per stored brief (a floor when the stored text is truncated)
    storage_growth    size and growth of the intelligence tables

IMPORTANT: executing successfully, a source count, an item count or a brief line count do NOT establish intelligence
effectiveness. These measures describe a funnel and a frame; the reference set is not independent (see CAVEATS).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "platform-runtime")]

BRIEFED_DEFINITION = (
    "'Briefed' is reported by path and none of the paths is proof the Captain read or acted on anything. (1) ori_brief_id_events = events whose brief_id is set: "
    "the ORI intelligence_briefs path ONLY, capped at about 5 events per brief, and the Captain's morning brief does not set it, so RELEVANT-to-brief_id is an "
    "artefact of that cap and not a funnel conversion. (2) disposition_brief_or_escalate = events the classifier marked for a brief (selected, not delivered). "
    "(3) morning_brief_incident_ids = distinct incident ids in the latest stored morning brief (the delivered text, any path).")
FUNNEL_DEFINITIONS = {
    "day": "UTC calendar day of the timestamp named in each stage (a Melbourne morning brief spans two UTC days).",
    "sources_swept": "distinct sources with at least one health row that day.",
    "items_returned": "sum of items_retrieved over the FIRST health row of each source that day: feed entries a fetch returned, including re-fetched entries. Not new, unique, relevant or briefed items.",
    "new_events": "intelligence_events rows with collected_at on that day (all jobs). A different unit from items_returned.",
    "suppressed_on_arrival": "of new_events, rows with suppressed = true.",
    "mission_relevant": "of new_events, rows with mission_relevance = 'RELEVANT'.",
    "briefed_ori_brief_id": "of new_events, rows with brief_id set: the ORI intelligence_briefs path only (capped about 5 per brief); the Captain's morning brief never sets it.",
    "briefed_classifier_disposition": "of new_events, rows the classifier marked BRIEF or ESCALATE: selected for a brief, not delivered.",
    "reading_note": "Stages are counts of different things beside each other. No stage is a conversion, yield or rate of another and none is computed.",
}
BOUNDED_GAP = "[^\\n]{0,60}"      # replaces an unbounded ``.*`` in recall regexes: same line, at most 60 characters between the terms

DEFAULT_SWEEP_START = "2026-11-24T19:00:00+00:00"   # 06:00 AEDT sweep of 25 Nov 2026
DEFAULT_WINDOW_HOURS = 1
REF_SET = REPO / "knowledge" / "intelligence-reference-set" / "reference_set_v3.json"
REPLAY_IDS = ("RS-062", "RS-079", "RS-081")
RECALL_CHUNKS = 3
INCIDENT_ID_RX = re.compile(r"inc-[0-9a-f]{8,12}")
NOT_MEASURED = "NOT_MEASURED"

CAVEATS = [
    ("Executing successfully, source counts, item counts and brief line counts do not establish intelligence effectiveness. "
    "They show that collection and rendering ran, not that material events were found, selected, understood or delivered."),
    ("The funnel is a single-sweep snapshot. 'Items fetched' counts what a fetch returned (sum of items_retrieved, first health row per "
    "source in the window), not new, unique, relevant or briefed items; the item-level split between duplicate, dropped and new is not queryable (no items table)."),
    BRIEFED_DEFINITION,
    ("Items fetched and events are different units: items_retrieved counts feed entries returned by each fetch (including re-fetched entries), events are new rows by collected_at across all jobs. "
    "Their quotient is not a conversion rate and is not computed; the stages are shown side by side only."),
    ("Selection recall is a frame: the 27 operational-disruption records of reference set v3 (84 records). Owner decisions of 24 Nov were applied by an agent and "
    "36 records are unreviewed. The set is NOT independent (thresholds were tuned while reading it), so 15/27 is a baseline for change, not an accuracy estimate. "
    "Brief text matching is a title-pattern match (weaker than brief_id): a miss is 'no match found', not proof of absence."),
    ("The replay applies today's clustering and tier rules to the events of each record in isolation. It tests classification, not competition for the "
    "section caps and ranking that also applied on the original day, and it uses only the three named records; it is not a holdout."),
    ("The brief duplication ratio is a floor when the stored brief text is truncated (the stored column is cut at 8,000 characters). Pair it with incident "
    "recall: reducing mentions by dropping incidents is not success."),
    "Duplicate-row checks cover stored rows only. Telegram sends are not queryable (the Bot API cannot list sent messages), so duplicate sends cannot be measured here.",
    "DB text is untrusted data; titles are shown truncated and are never executed or interpreted.",
]


# --------------------------------------------------------------------------------------------------------------------
# SQL (SELECT only)
# --------------------------------------------------------------------------------------------------------------------
def _ts_literal(s: str) -> str:
    datetime.fromisoformat(s)                        # validates; raises on anything that is not an ISO timestamp
    return "'" + s.replace("'", "") + "'::timestamptz"


def bound_regex(rx: str) -> str:
    """Bound the gap between terms of a recall pattern: ``.*`` / ``.+`` (which in Postgres cross newlines and 8,000-character texts, so any
    mention of the first term plus any later mention of the second matched) become same-line gaps of at most 60 characters."""
    return rx.replace(".*", BOUNDED_GAP).replace(".+", "[^\\n]{1,60}")


def _bounded_specs(specs):
    return [(sp[0], bound_regex(sp[1]), *sp[2:]) for sp in specs]


def _recall_specs():
    """(id, regex, from, to) for the operational-disruption records of reference set v3 (reuses the committed match specs)."""
    from tools.intelligence import reference_set_v3_measure as M
    ref = json.loads(REF_SET.read_text(encoding="utf-8"))
    ids = [i["id"] for i in ref["incidents"] if i["intelligence_category"] == "material_operational_disruption"]
    by_id = {s[0]: s for s in M.specs()}
    return ids, _bounded_specs([by_id[i] for i in ids if i in by_id])


def build_queries(sweep_start: str = DEFAULT_SWEEP_START, window_hours: int = DEFAULT_WINDOW_HOURS, funnel_days: int = 7) -> dict[str, str]:
    from unittest import mock

    from tools.intelligence import reference_set_v3_measure as M
    s = _ts_literal(sweep_start)
    h = int(window_hours)
    w = f"with w as (select {s} as s, {s} + interval '{h} hours' as e)"
    first = (f"{w}, f as (select distinct on (h.source_id) h.* from intelligence_source_health h, w "
             f"where h.checked_at >= w.s and h.checked_at < w.e order by h.source_id, h.checked_at, h.health_id)")
    _, specs = _recall_specs()
    q: dict[str, str] = {}
    q["funnel"] = (f"{first}, ev as (select e.* from intelligence_events e, w where e.collected_at >= w.s and e.collected_at < w.e) "
                   "select (select count(*) from f) as sources, (select coalesce(sum(items_retrieved),0) from f) as items, "
                   "(select count(*) from f where status = 'ok') as ok_sources, (select count(*) from f where status <> 'ok') as not_ok_sources, "
                   "(select count(*) from ev) as events, (select count(*) from ev where suppressed) as suppressed, "
                   "(select count(*) from ev where mission_relevance = 'RELEVANT') as relevant, "
                   "(select count(*) from ev where brief_id is not null) as briefed, "
                   "(select count(*) from ev where disposition in ('BRIEF','ESCALATE')) as disp_brief, "
                   "(select count(*) from ev where disposition in ('BRIEF','ESCALATE') and mission_relevance = 'RELEVANT') as relevant_disp_brief")
    n = max(1, min(int(funnel_days), 60))
    day = lambda col: f"(({col}) at time zone 'UTC')::date"
    q["funnel_daily"] = (f"with s as (select {s}::timestamptz as t), days as (select (generate_series(({day('s.t')} - {n - 1}), {day('s.t')}, interval '1 day'))::date as d from s), "
                         f"h1 as (select distinct on (h.source_id, {day('h.checked_at')}) h.source_id, {day('h.checked_at')} as d, h.items_retrieved, h.status "
                         f"from intelligence_source_health h, s where h.checked_at >= ({day('s.t')} - {n - 1})::timestamp at time zone 'UTC' "
                         f"and h.checked_at < ({day('s.t')} + 1)::timestamp at time zone 'UTC' order by h.source_id, {day('h.checked_at')}, h.checked_at, h.health_id), "
                         f"ev as (select {day('e.collected_at')} as d, e.suppressed, e.mission_relevance, e.brief_id, e.disposition from intelligence_events e, s "
                         f"where e.collected_at >= ({day('s.t')} - {n - 1})::timestamp at time zone 'UTC' and e.collected_at < ({day('s.t')} + 1)::timestamp at time zone 'UTC') "
                         "select days.d as day, (select count(*) from h1 where h1.d = days.d) as sources, "
                         "(select coalesce(sum(items_retrieved),0) from h1 where h1.d = days.d) as items, "
                         "(select count(*) from ev where ev.d = days.d) as events, (select count(*) from ev where ev.d = days.d and suppressed) as suppressed, "
                         "(select count(*) from ev where ev.d = days.d and mission_relevance = 'RELEVANT') as relevant, "
                         "(select count(*) from ev where ev.d = days.d and brief_id is not null) as briefed_ori, "
                         "(select count(*) from ev where ev.d = days.d and disposition in ('BRIEF','ESCALATE')) as briefed_disp from days order by days.d")
    q["health_zero_item_ok"] = (f"{first} select r.source_name, r.reliability_tier, f.status, f.items_retrieved from f join intelligence_source_registry r using (source_id) "
                                "where f.status = 'ok' and f.items_retrieved = 0 order by r.source_name")
    q["health_invalid_content"] = (f"{first} select r.source_name, r.reliability_tier, f.content_valid, left(coalesce(f.content_validity_reason,''),120) as reason "
                                   "from f join intelligence_source_registry r using (source_id) where f.content_valid is false order by r.source_name")
    q["health_unswept"] = (f"{w} select r.source_name, r.reliability_tier, "
                           "(select max(checked_at) from intelligence_source_health h where h.source_id = r.source_id) as last_health_at "
                           "from intelligence_source_registry r, w where r.active and not exists (select 1 from intelligence_source_health h "
                           "where h.source_id = r.source_id and h.checked_at >= w.s and h.checked_at < w.e) order by r.reliability_tier, r.source_name")
    q["duplicate_rows"] = (
        "select 'daily_briefs_same_type_date' as chk, 'defect' as kind, count(*) as n_keys, coalesce(sum(c-1),0) as extra_rows from "
        "(select brief_type, brief_date, count(*) c from captains_daily_briefs where brief_date >= current_date - 30 group by 1,2 having count(*) > 1) x "
        "union all select 'intel_briefs_same_cycle', 'defect', count(*), coalesce(sum(c-1),0) from (select morning_cycle_id, count(*) c from intelligence_briefs "
        "where morning_cycle_id is not null and generated_at >= now() - interval '30 days' group by 1 having count(*) > 1) x "
        "union all select 'events_same_dedup_hash', 'defect', count(*), coalesce(sum(c-1),0) from (select dedup_hash, count(*) c from intelligence_events "
        "where collected_at >= now() - interval '30 days' and dedup_hash is not null group by 1 having count(*) > 1) x "
        "union all select 'products_same_key_date', 'defect', count(*), coalesce(sum(c-1),0) from (select product_key, generated_for, count(*) c "
        "from intelligence_products group by product_key, generated_for, md5(body_md) having count(*) > 1) x "
        "union all select 'events_same_source_url', 'informational', count(*), coalesce(sum(c-1),0) from (select source_id, canonical_url, count(*) c "
        "from intelligence_events where collected_at >= now() - interval '30 days' and canonical_url is not null group by 1,2 having count(*) > 1) x "
        "union all select 'registry_same_name', 'informational', count(*), coalesce(sum(c-1),0) from (select lower(source_name) k, count(*) c "
        "from intelligence_source_registry group by 1 having count(*) > 1) x")
    q["duplicate_rows_detail"] = ("select brief_type, brief_date, count(*) as n_rows, min(generated_at) as first_at, max(generated_at) as last_at, "
                                  "count(distinct md5(brief_text)) as distinct_texts from captains_daily_briefs where brief_date >= current_date - 30 "
                                  "group by 1,2 having count(*) > 1 order by 2 desc, 1")
    q["brief_duplication"] = ("select b.brief_date, b.brief_type, length(b.brief_text) as stored_length, "
                              "(select count(*) from regexp_matches(b.brief_text, 'inc-[0-9a-f]{8,12}', 'g')) as mentions, "
                              "(select count(distinct m[1]) from regexp_matches(b.brief_text, '(inc-[0-9a-f]{8,12})', 'g') m) as ids "
                              "from captains_daily_briefs b where b.brief_date >= current_date - 14 order by b.brief_date desc, b.brief_type")
    for k in range(RECALL_CHUNKS):
        with mock.patch.object(M, "specs", lambda v1_path=None: specs):
            q[f"recall_detection_{k}"] = M.detection_sql(chunk=(k, RECALL_CHUNKS))
    with mock.patch.object(M, "specs", lambda v1_path=None: specs):
        q["recall_conversion"] = M.conversion_sql()
    by_id = {sp[0]: sp for sp in _bounded_specs(M.specs())}
    rows = ",\n".join(f"({M._q(i)},{M._q(by_id[i][1])},{M._q(by_id[i][2])}::date,{M._q(by_id[i][3])}::date)" for i in REPLAY_IDS)
    q["replay_events"] = (f"with r(id, rx, f, t) as (values\n{rows}\n) select r.id as rid, e.event_id::text as id, s.source_name as source, "
                          "e.raw_title as title, e.published_at, e.collected_at, e.brief_id::text as brief_id, e.suppressed, e.disposition, "
                          "e.mission_relevance, e.risk_rating, e.rank_score, e.geography from r join intelligence_events e on e.raw_title ~* r.rx "
                          "and e.published_at >= r.f - 1 and e.published_at < r.t + 2 join intelligence_source_registry s using (source_id) "
                          "order by r.id, e.collected_at")
    q["storage_size"] = ("select c.relname as tbl, s.n_live_tup as est_rows, pg_total_relation_size(c.oid) as bytes from pg_stat_user_tables s "
                         "join pg_class c on c.oid = s.relid where c.relname in ('intelligence_events','intelligence_source_health','intelligence_briefs',"
                         "'captains_daily_briefs','intelligence_products','source_reliability_snapshot','intelligence_incident_snapshots') order by 1")
    q["storage_growth"] = (
        "select 'intelligence_events' as tbl, count(*) filter (where collected_at >= now() - interval '7 days') as rows_7d, "
        "count(*) filter (where collected_at >= now() - interval '30 days') as rows_30d, count(*) as rows_total, "
        "coalesce(sum(pg_column_size(e.*)) filter (where collected_at >= now() - interval '30 days'),0) as row_bytes_30d from intelligence_events e "
        "union all select 'intelligence_source_health', count(*) filter (where checked_at >= now() - interval '7 days'), count(*) filter (where checked_at >= now() - interval '30 days'), "
        "count(*), coalesce(sum(pg_column_size(h.*)) filter (where checked_at >= now() - interval '30 days'),0) from intelligence_source_health h "
        "union all select 'captains_daily_briefs', count(*) filter (where created_at >= now() - interval '7 days'), count(*) filter (where created_at >= now() - interval '30 days'), "
        "count(*), coalesce(sum(pg_column_size(b.*)) filter (where created_at >= now() - interval '30 days'),0) from captains_daily_briefs b "
        "union all select 'intelligence_briefs', count(*) filter (where generated_at >= now() - interval '7 days'), count(*) filter (where generated_at >= now() - interval '30 days'), "
        "count(*), coalesce(sum(pg_column_size(b.*)) filter (where generated_at >= now() - interval '30 days'),0) from intelligence_briefs b "
        "union all select 'intelligence_products', count(*) filter (where created_at >= now() - interval '7 days'), count(*) filter (where created_at >= now() - interval '30 days'), "
        "count(*), coalesce(sum(pg_column_size(p.*)) filter (where created_at >= now() - interval '30 days'),0) from intelligence_products p")
    for name, sql in q.items():
        assert re.match(r"\s*(--[^\n]*\n\s*)*(with|select)\b", sql, re.IGNORECASE), name       # SELECT-only guard
        assert not re.search(r"\b(insert|update|delete|drop|alter|create|truncate|grant)\b\s", re.sub(r"'[^']*'", "''", sql), re.IGNORECASE), name
    return q


# --------------------------------------------------------------------------------------------------------------------
# computations (pure)
# --------------------------------------------------------------------------------------------------------------------
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((c - m) / d, 3), round((c + m) / d, 3)


def _i(v) -> int:
    return int(v) if v not in (None, "") else 0


def _rows(results: dict, name: str):
    return results.get(name)


def compute_funnel(rows, brief_dup: dict | None = None) -> dict:
    """Stages side by side. No stage-to-stage conversion between different units is computed (items vs events); 'briefed' is reported
    by path (``BRIEFED_DEFINITION``)."""
    if not rows:
        return {"status": NOT_MEASURED}
    r = rows[0]
    items, events, relevant, ori = _i(r["items"]), _i(r["events"]), _i(r["relevant"]), _i(r["briefed"])
    lambda a, b: round(100 * a / b, 1) if b else None
    morning = (brief_dup or {}).get("latest_morning_with_incident_ids") if isinstance(brief_dup, dict) else None
    briefed = {"ori_brief_id_events": ori,
               "disposition_brief_or_escalate": _i(r["disp_brief"]) if "disp_brief" in r else NOT_MEASURED,
               "relevant_with_disposition_brief_or_escalate": _i(r["relevant_disp_brief"]) if "relevant_disp_brief" in r else NOT_MEASURED,
               "morning_brief_incident_ids": morning["ids"] if morning else NOT_MEASURED,
               "morning_brief_date": morning["brief_date"] if morning else None,
               "definition": BRIEFED_DEFINITION}
    return {"status": "MEASURED", "sources_swept": _i(r["sources"]), "sources_ok": _i(r["ok_sources"]), "sources_not_ok": _i(r["not_ok_sources"]),
            "items_fetched": items, "new_events": events, "suppressed_on_arrival": _i(r["suppressed"]), "mission_relevant": relevant,
            "briefed": briefed, "briefed_events": ori, "briefed_events_meaning": "events.brief_id (ORI path only); see briefed.definition",
            "chain": [items, events, relevant],
            "items_vs_events_note": "different units (feed entries returned vs new event rows); no conversion rate is computed"}


def compute_funnel_daily(rows) -> dict:
    """One row per UTC day with explicit definitions (``FUNNEL_DEFINITIONS``). Counts only: no conversion, yield or rate between stages."""
    if not rows:
        return {"status": NOT_MEASURED, "definitions": FUNNEL_DEFINITIONS}
    days = [{"day": str(r["day"])[:10], "sources_swept": _i(r["sources"]), "items_returned": _i(r["items"]), "new_events": _i(r["events"]),
             "suppressed_on_arrival": _i(r["suppressed"]), "mission_relevant": _i(r["relevant"]),
             "briefed_ori_brief_id": _i(r["briefed_ori"]), "briefed_classifier_disposition": _i(r["briefed_disp"])} for r in rows]
    return {"status": "MEASURED", "days": days, "definitions": FUNNEL_DEFINITIONS}


def _pair_rows(chunks) -> list[list]:
    out = []
    for r in chunks:
        out.append(r["row"] if isinstance(r, dict) and "row" in r else r)
    return out


def compute_recall(det_rows, conv_rows) -> dict:
    """Reference set v3 operational-disruption records that reached a brief. Reached = any of: an event with brief_id; a daily brief,
    intelligence_briefs section or intelligence product whose text matches the record pattern (as in the reference-set measurement)."""
    ref = json.loads(REF_SET.read_text(encoding="utf-8"))
    ops = [i for i in ref["incidents"] if i["intelligence_category"] == "material_operational_disruption"]
    if det_rows is None or conv_rows is None:
        return {"status": NOT_MEASURED, "frame": f"{len(ops)} operational-disruption records of reference set v3"}
    det = {r[0]: r for r in _pair_rows(det_rows)}
    conv = {r[0]: r for r in _pair_rows(conv_rows)}
    detail, reached, appeared = [], 0, 0
    for rec in ops:
        d, c = det.get(rec["id"]), conv.get(rec["id"])
        n_events = _i(d[1]) if d else 0
        ev_brief = _i(d[10]) if d else 0
        ch = {"event_brief_id": ev_brief, "daily_briefs": _i(c[1]) if c else 0, "intel_briefs_forward_watch": _i(c[3]) if c else 0,
              "intel_briefs_other": _i(c[4]) if c else 0, "products": _i(c[6]) if c else 0}
        ok = any(ch.values())
        reached += ok
        appeared += n_events > 0
        detail.append({"id": rec["id"], "title": rec["title"][:90], "events_collected": n_events, "reached_brief": ok, "channels": ch,
                       "first_source": d[5] if d else None})
    n = len(ops)
    return {"status": "MEASURED", "frame": f"{n} operational-disruption records of reference set v3 (84 records, 34 confirmed material)",
            "records": n, "appeared_in_events": appeared, "reached_a_brief": reached, "recall": round(reached / n, 3),
            "wilson_95": wilson(reached, n),
            "wilson_note": "The 27 records are a curated, tuned frame, not a sample: the interval is arithmetic on n=27, NOT an uncertainty statement about recall.",
            "regex_basis": "frozen rows predate bounded patterns: brief-text matches used unbounded gaps (an upper bound); the SQL emitted now bounds them (bound_regex)",
            "bounded_remeasure_2026_11_25": "conversion channels re-run with bounded patterns (SELECT, production, 25 Nov): 13/27 reached (Wilson 31-66%); RS-033 and RS-063 lost their only (spurious) brief-text credit. The 15/27 baseline was an upper bound.",
            "baseline_in_pack": "15/27 = 56% (Wilson 37-72%)",
            "not_reached": [d["id"] for d in detail if not d["reached_brief"]], "detail": detail,
            "caveat": "baseline for change; reference set is not independent and 36 records are unreviewed"}


def compute_health(zero, invalid, unswept) -> dict:
    if zero is None and invalid is None and unswept is None:
        return {"status": NOT_MEASURED}
    z, v, u = zero or [], invalid or [], unswept or []
    return {"status": "MEASURED",
            "zero_item_ok_sources": {"n": len(z), "sources": [r["source_name"] for r in z]},
            "invalid_content_sources": {"n": len({r["source_name"] for r in v}), "rows": len(v),
                                        "sources": sorted({r["source_name"] for r in v})},
            "active_sources_not_swept": {"n": len(u), "sources": [{"name": r["source_name"], "tier": r.get("reliability_tier"),
                                                                  "last_health_at": r.get("last_health_at")} for r in u],
                                         "tier_1_unswept": [r["source_name"] for r in u if r.get("reliability_tier") == "TIER_1"]},
            "reading": "A sweep with 0 failed sources can still contain silent (zero-item), low-validity and unswept sources; these lists are not failures of the health gate."}


def compute_duplicates(rows, detail) -> dict:
    if rows is None:
        return {"status": NOT_MEASURED}
    defects = [r for r in rows if r["kind"] == "defect"]
    n_def = sum(_i(r["extra_rows"]) for r in defects)
    return {"status": "MEASURED", "checks": [{"check": r["chk"], "kind": r["kind"], "duplicated_keys": _i(r["n_keys"]), "extra_rows": _i(r["extra_rows"])} for r in rows],
            "defect_extra_rows": n_def, "acceptance_zero_duplicate_rows": n_def == 0, "detail_daily_briefs": detail or [],
            "reading": "'defect' checks must be 0 for P0-28; 'informational' checks (same URL re-collected, repeated registry name) are listed, not judged. "
                       "Duplicate Telegram sends are not measurable from stored rows."}


def compute_brief_duplication(rows) -> dict:
    if rows is None:
        return {"status": NOT_MEASURED}
    out = []
    for r in rows:
        m, i = _i(r["mentions"]), _i(r["ids"])
        out.append({"brief_date": str(r["brief_date"])[:10], "brief_type": r["brief_type"], "stored_length": _i(r["stored_length"]), "mentions": m, "ids": i,
                    "ratio": round(m / i, 2) if i else None, "possibly_truncated": _i(r["stored_length"]) >= 8000})
    with_ids = [x for x in out if x["ids"]]
    latest = next((x for x in out if x["brief_type"] == "morning" and x["ids"]), None)
    return {"status": "MEASURED", "briefs": out, "latest_morning_with_incident_ids": latest, "briefs_with_ids": len(with_ids),
            "reading": "mentions/ids is a floor when stored_length is 8000 (truncated). Target in the pack: <=1.0 per message, paired with incident recall."}


def _dt(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)


def compute_replay(rows) -> dict:
    """Replay each named record's events through the current clustering and delivery tiers (intelligence.incident_clustering / delivery_tiers)."""
    if not rows:
        return {"status": NOT_MEASURED}
    from intelligence import delivery_tiers as dt
    from tools.intelligence import alert_replay as AR
    out = {}
    for rid in REPLAY_IDS:
        evs = [r for r in rows if r["rid"] == rid]
        if not evs:
            out[rid] = {"status": "NO_EVENTS_MATCHED", "events": 0}
            continue
        events = [{"id": r["id"], "source": r["source"], "title": r["title"], "published_at": str(r["published_at"]), "collected_at": str(r["collected_at"]),
                   "brief_id": r.get("brief_id"), "suppressed": bool(r.get("suppressed")), "disposition": r.get("disposition")} for r in evs]
        res = AR.replay(events, consolidated=True)
        ids = {e["id"] for e in events}
        tiers = []
        for inc in res["final_incidents"]:
            if any(rep.event_id in ids for rep in inc.reports):
                tiers.append({"incident": inc.incident_id, "final_tier": res["tiers"][inc.incident_id].tier,
                              "reasons": list(res["tiers"][inc.incident_id].reasons)[:4], "headline": inc.decision.headline.title[:90]})
        surfaced_tiers = (dt.IMMEDIATE_ALERT, dt.SCHEDULED_BRIEF)
        ever = bool(ids & set(res["ever_material"]))
        out[rid] = {"status": "REPLAYED", "events": len(events),
                    "stored": [{"source": e["source"], "disposition": e["disposition"], "brief_id": bool(e["brief_id"]),
                                "mission_relevance": r.get("mission_relevance"), "risk_rating": r.get("risk_rating"), "rank_score": r.get("rank_score"),
                                "geography": r.get("geography"), "title": e["title"][:90]} for e, r in zip(events, evs)],
                    "alerts": [{"alerted_at": a["alerted_at"], "latency_h_from_first_collection": a["latency_hours_from_first_collection"]} for a in res["alerts"]],
                    "incident_tiers": tiers, "reached_alert_or_scheduled_tier_at_any_batch": ever,
                    "final_tier_in_surfacing_set": any(t["final_tier"] in surfaced_tiers for t in tiers)}
    replayed = [v for v in out.values() if v.get("status") == "REPLAYED"]
    return {"status": "MEASURED", "records": out, "would_surface_under_current_rules": [k for k, v in out.items() if v.get("reached_alert_or_scheduled_tier_at_any_batch")],
            "not_surfaced_under_current_rules": [k for k, v in out.items() if v.get("status") == "REPLAYED" and not v["reached_alert_or_scheduled_tier_at_any_batch"]],
            "n_replayed": len(replayed),
            "reading": "Tiers are the offline classification of that record's own events; a 'surfaces' result does not mean the brief would have shown it "
                       "(section limits, ranking and the 72 h window are not replayed). Each omission needs its own classification before any rule change."}


def compute_storage(size, growth) -> dict:
    if size is None and growth is None:
        return {"status": NOT_MEASURED}
    g = {r["tbl"]: r for r in (growth or [])}
    tabs = []
    for r in size or []:
        gr = g.get(r["tbl"])
        row = {"table": r["tbl"], "est_rows": _i(r["est_rows"]), "total_bytes": _i(r["bytes"])}
        if gr:
            r30, b30 = _i(gr["rows_30d"]), _i(gr["row_bytes_30d"])
            row.update({"rows_7d": _i(gr["rows_7d"]), "rows_30d": r30, "row_bytes_30d": b30,
                        "projected_bytes_per_year_at_30d_rate": round(b30 * 365 / 30)})
        tabs.append(row)
    return {"status": "MEASURED", "tables": tabs,
            "reading": "Row-byte projection is pg_column_size of the last 30 days extrapolated linearly (excludes indexes/TOAST overhead differences); "
                       "the products and briefs tables are small today, the growth that matters is events and health rows. The WP1 append-only history adds rows to intelligence_products only."}


def compute_all(results: dict, sweep_start: str = DEFAULT_SWEEP_START, window_hours: int = DEFAULT_WINDOW_HOURS) -> dict:
    det = [r for k in sorted(results) if k.startswith("recall_detection_") for r in results[k]] or None
    return {"schema": 1, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "read_only": True,
            "sweep_window": {"start": sweep_start, "hours": window_hours},
            "caveats": CAVEATS,
            "funnel_daily": compute_funnel_daily(_rows(results, "funnel_daily")),
            "funnel": compute_funnel(_rows(results, "funnel"), compute_brief_duplication(_rows(results, "brief_duplication"))),
            "selection_recall": compute_recall(det, _rows(results, "recall_conversion")),
            "health_vs_effectiveness": compute_health(_rows(results, "health_zero_item_ok"), _rows(results, "health_invalid_content"), _rows(results, "health_unswept")),
            "duplicate_rows": compute_duplicates(_rows(results, "duplicate_rows"), _rows(results, "duplicate_rows_detail")),
            "replay": compute_replay(_rows(results, "replay_events")),
            "brief_duplication": compute_brief_duplication(_rows(results, "brief_duplication")),
            "storage_growth": compute_storage(_rows(results, "storage_size"), _rows(results, "storage_growth"))}


# --------------------------------------------------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------------------------------------------------
def render_markdown(m: dict) -> str:
    L = ["# Intelligence effectiveness measures", "", f"Generated {m['generated_at']} (read-only; not scheduled). Sweep window {m['sweep_window']['start']} + {m['sweep_window']['hours']} h.", "",
         "> **These measures do not establish effectiveness.** " + m["caveats"][0], ""]
    f = m["funnel"]
    L += ["## Funnel by day (counts side by side; not conversions)"]
    fd = m.get("funnel_daily") or {"status": NOT_MEASURED}
    if fd["status"] == NOT_MEASURED:
        L += ["NOT_MEASURED", ""]
    else:
        L += ["| day (UTC) | sources swept | items returned | new events | suppressed | mission RELEVANT | briefed: ORI brief_id | briefed: classifier BRIEF/ESCALATE |", "|---|---|---|---|---|---|---|---|"]
        L += [f"| {d['day']} | {d['sources_swept']} | {d['items_returned']:,} | {d['new_events']} | {d['suppressed_on_arrival']} | {d['mission_relevant']} | {d['briefed_ori_brief_id']} | {d['briefed_classifier_disposition']} |" for d in fd["days"]]
        L += ["", "Definitions:"] + [f"- {k}: {v}" for k, v in fd["definitions"].items()] + [""]
    L += ["## Funnel (one sweep hour; the single-sweep view, see the daily table above)"]
    if f["status"] == NOT_MEASURED:
        L += ["NOT_MEASURED", ""]
    else:
        b = f["briefed"]
        L += [f"Stages (different units, not a conversion chain): {f['items_fetched']:,} feed items returned | {f['new_events']} new events | {f['mission_relevant']} mission RELEVANT", "",
              f"- sources swept {f['sources_swept']} (ok {f['sources_ok']}, not ok {f['sources_not_ok']}); suppressed on arrival {f['suppressed_on_arrival']}",
              f"- Items-to-events is not a rate: {f['items_vs_events_note']}.",
              ("- Briefed, by path: "
              f"ORI brief_id events {b['ori_brief_id_events']} (ORI path only, capped ~5 per brief); "
              f"classifier disposition BRIEF/ESCALATE {b['disposition_brief_or_escalate']}; "
              f"incident ids in the latest morning brief {b['morning_brief_incident_ids']}."), ""]
    r = m["selection_recall"]
    L += ["## Selection-recall frame"]
    if r["status"] == NOT_MEASURED:
        L += ["NOT_MEASURED", ""]
    else:
        lo, hi = r["wilson_95"]
        L += [f"{r['reached_a_brief']}/{r['records']} = {round(100 * r['recall'])}% (Wilson 95% {round(100 * lo)}-{round(100 * hi)}%); {r['appeared_in_events']}/{r['records']} appeared in collected events.",
              f"Frame: {r['frame']}. Pack baseline: {r['baseline_in_pack']}. {r['caveat']}.", "", "Not reached: " + ", ".join(r["not_reached"]), "",
              "| Record | Events | Reached a brief | Channels (brief_id/daily/fw/other/products) |", "|---|---|---|---|"]
        for d in r["detail"]:
            c = d["channels"]
            L.append(f"| {d['id']} {d['title'][:60]} | {d['events_collected']} | {'yes' if d['reached_brief'] else 'no'} | "
                     f"{c['event_brief_id']}/{c['daily_briefs']}/{c['intel_briefs_forward_watch']}/{c['intel_briefs_other']}/{c['products']} |")
        L.append("")
    h = m["health_vs_effectiveness"]
    L += ["## Health versus effectiveness lists"]
    if h["status"] == NOT_MEASURED:
        L += ["NOT_MEASURED", ""]
    else:
        L += [f"- Zero-item sources reporting ok: {h['zero_item_ok_sources']['n']}", f"- Invalid-content sources: {h['invalid_content_sources']['n']} ({', '.join(h['invalid_content_sources']['sources'])})",
              f"- Active sources absent from the sweep: {h['active_sources_not_swept']['n']}; TIER_1 among them: {', '.join(h['active_sources_not_swept']['tier_1_unswept']) or 'none'}",
              "", "Zero-item ok: " + (", ".join(h["zero_item_ok_sources"]["sources"]) or "none"), "", h["reading"], ""]
    d = m["duplicate_rows"]
    L += ["## Duplicate-row check (P0-28)"]
    if d["status"] == NOT_MEASURED:
        L += ["NOT_MEASURED", ""]
    else:
        L += ["| Check | Kind | Duplicated keys | Extra rows |", "|---|---|---|---|"] + [f"| {c['check']} | {c['kind']} | {c['duplicated_keys']} | {c['extra_rows']} |" for c in d["checks"]]
        L += ["", f"Defect extra rows: {d['defect_extra_rows']} (acceptance 0: {'met' if d['acceptance_zero_duplicate_rows'] else 'NOT met'}).", d["reading"], ""]
    p = m["replay"]
    L += ["## Replay of RS-062 / RS-079 / RS-081 (offline, current rules)"]
    if p["status"] == NOT_MEASURED:
        L += ["NOT_MEASURED", ""]
    else:
        for rid, v in p["records"].items():
            if v["status"] != "REPLAYED":
                L.append(f"- {rid}: {v['status']}")
                continue
            tiers = "; ".join(f"{t['final_tier']}" for t in v["incident_tiers"]) or "no incident"
            L.append(f"- {rid}: {v['events']} stored event(s); final tier(s): {tiers}; reached alert/scheduled tier at any batch: {v['reached_alert_or_scheduled_tier_at_any_batch']}")
            for s in v["stored"]:
                L.append(f"  - {s['source']}: {s['disposition']} / {s['mission_relevance']} / risk {s['risk_rating']} / rank {s['rank_score']} / geo {s['geography']}")
        L += ["", p["reading"], ""]
    b = m["brief_duplication"]
    L += ["## Brief duplication ratio"]
    if b["status"] == NOT_MEASURED:
        L += ["NOT_MEASURED", ""]
    else:
        lt = b["latest_morning_with_incident_ids"]
        if lt:
            L.append(f"Latest morning brief with incident ids ({lt['brief_date']}): {lt['mentions']} mentions / {lt['ids']} ids = {lt['ratio']}" + (" (floor: stored text truncated)" if lt["possibly_truncated"] else ""))
        L += ["", "| Date | Type | Stored length | Mentions | Ids | Ratio |", "|---|---|---|---|---|---|"] + \
             [f"| {x['brief_date']} | {x['brief_type']} | {x['stored_length']} | {x['mentions']} | {x['ids']} | {x['ratio']} |" for x in b["briefs"] if x["ids"]]
        L += ["", b["reading"], ""]
    s = m["storage_growth"]
    L += ["## Storage growth"]
    if s["status"] == NOT_MEASURED:
        L += ["NOT_MEASURED", ""]
    else:
        L += ["| Table | Est. rows | Size (MB) | Rows 7d | Rows 30d | Projected MB/yr |", "|---|---|---|---|---|---|"]
        for t in s["tables"]:
            L.append(f"| {t['table']} | {t['est_rows']:,} | {t['total_bytes'] / 1e6:.1f} | {t.get('rows_7d', '')} | {t.get('rows_30d', '')} | "
                     f"{round(t['projected_bytes_per_year_at_30d_rate'] / 1e6, 1) if 'projected_bytes_per_year_at_30d_rate' in t else ''} |")
        L += ["", s["reading"], ""]
    L += ["## Caveats"] + [f"- {c}" for c in m["caveats"]]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--print-sql", nargs="?", const="all", metavar="NAME")
    ap.add_argument("--results", help="JSON file {query name: rows}")
    ap.add_argument("--sweep-start", default=DEFAULT_SWEEP_START)
    ap.add_argument("--window-hours", type=int, default=DEFAULT_WINDOW_HOURS)
    ap.add_argument("--out-json")
    ap.add_argument("--out-md")
    a = ap.parse_args(argv)
    if a.print_sql:
        q = build_queries(a.sweep_start, a.window_hours)
        if a.print_sql != "all":
            if a.print_sql not in q:
                print(f"unknown query {a.print_sql!r}; choose from: {', '.join(q)}", file=sys.stderr)
                return 2
            q = {a.print_sql: q[a.print_sql]}
        for name, sql in q.items():
            print(f"-- === {name} ===\n{sql};\n")
        return 0
    if not a.results:
        print(__doc__)
        return 0
    results = json.loads(Path(a.results).read_text(encoding="utf-8"))
    m = compute_all(results, a.sweep_start, a.window_hours)
    md = render_markdown(m)
    if a.out_json:
        Path(a.out_json).write_text(json.dumps(m, indent=2, default=str) + "\n", encoding="utf-8")
    if a.out_md:
        Path(a.out_md).write_text(md, encoding="utf-8")
    if not (a.out_json or a.out_md):
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
