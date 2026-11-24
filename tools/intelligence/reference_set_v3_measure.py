#!/usr/bin/env python3
"""Measurement spec and SELECT-only SQL for reference set v3 (offline; prints SQL, never connects).

``python tools/intelligence/reference_set_v3_measure.py --print-detection-sql`` (and ``--print-conversion-sql``) print read-only
SELECTs that, for every reference record that has a title pattern, compute the TJR detection block the same way the v1 blocks were made
(``intelligence_events.raw_title ~* regex``, published_at within [from-1d, to+2d), the scorecard's match window) and the
CONVERSION channels (event brief_id, captains_daily_briefs text, intelligence_briefs forward_watch/top_events/
executive_snapshot, intelligence_products body). The rows it returns are stored in
``knowledge/intelligence-reference-set/measurements_v3-2026-11-24.json`` and merged by build_reference_set_v3.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REF_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "intelligence-reference-set"

COLUMNS = ["id", "n_events", "first_collected_at", "first_published_at", "earliest_published_at", "first_source", "first_headline",
           "first_event_id", "n_distinct_sources", "n_non_aggregator_families", "events_with_brief_id", "events_suppressed",
           "events_brief_or_escalate", "events_escalate", "daily_briefs_mentioning", "first_daily_brief_date",
           "intelligence_briefs_forward_watch", "intelligence_briefs_other_sections", "first_intelligence_brief_date", "products_mentioning"]

# (id, title_regex, published_from, published_to). Postgres regex (~*): \m \M are word boundaries.
NEW_SPECS = [
    ("RS-054", r"Victorian court.*(data|hack|leak)|Court Services Victoria", "2026-08-06", "2026-08-12"),
    ("RS-055", r"remote monitoring and management platform", "2026-08-19", "2026-08-19"),
    ("RS-056", r"software development platform within Australia", "2026-08-24", "2026-08-24"),
    ("RS-057", r"Active exploitation of Adobe Commerce|ASD warns Aussie Adobe Commerce", "2026-09-09", "2026-09-09"),
    ("RS-058", r"Cosmetics company data breach|Napoleon Perdis", "2026-10-17", "2026-10-17"),
    ("RS-059", r"critical vulnerabilities in PHP|spike in data breaches after .critical. flaw|cybersecurity site among those hit|Hacking attempts surge", "2026-10-21", "2026-10-22"),
    ("RS-060", r"ABC (wipes staff devices|staff targeted)|ABC.*sophisticated cyber attack", "2026-10-22", "2026-10-23"),
    ("RS-061", r"without power.*(Qld|Queensland)|58,000 homes", "2026-11-11", "2026-11-12"),
    ("RS-062", r"VCAA|VCE exam", "2026-11-11", "2026-11-12"),
    ("RS-063", r"\mQuest\M.*(breach|data|passport|hotel)|hotel chain Quest", "2026-08-19", "2026-09-23"),
    ("RS-064", r"Tasmanian power station|Hydro Tasmania power station|Tungatinah", "2026-09-02", "2026-09-09"),
    ("RS-065", r"holiday parks across Australia|\mRMS\M|Federal Group hotels|scam email used real booking", "2026-10-27", "2026-10-28"),
    ("RS-066", r"National Parks booking|Campground booking portal|Bookeasy", "2026-11-11", "2026-11-14"),
    ("RS-067", r"air traffic control failure|sleep at Heathrow", "2026-09-08", "2026-09-09"),
    ("RS-068", r"Google Cloud Status: Multiple Products", "2026-08-20", "2026-08-20"),
    ("RS-069", r"SQL injection emails to root Cisco", "2026-09-16", "2026-09-16"),
    ("RS-070", r"Railway attackers", "2026-11-10", "2026-11-11"),
    ("RS-071", r"Campground booking portal disabled", "2026-11-14", "2026-11-14"),
    ("RS-072", r"\mStake\M.*data breach", "2026-09-25", "2026-09-25"),
    ("RS-073", r"Data breach reported at SA private hospital", "2026-10-08", "2026-10-08"),
    ("RS-074", r"Optimizely", "2026-11-16", "2026-11-16"),
    ("RS-075", r"Sydney (A|a)irport.*(delay|near.miss|incidents|flights affected|air traffic)|incidents at Sydney airport|Planes in tarmac near miss|Not enough air traffic controllers|heavy delays and near-miss", "2026-08-08", "2026-08-26"),
    ("RS-076", r"Coles website down", "2026-08-22", "2026-08-22"),
    ("RS-077", r"Fiji.*fuel|fuel contamination", "2026-08-20", "2026-08-31"),
    ("RS-078", r"MessageBank|Telstra glitch bombards", "2026-11-04", "2026-11-05"),
    ("RS-079", r"Triple Zero outage in Canberra|ACT Triple Zero call centre|Canberra.*Triple Zero", "2026-11-19", "2026-11-22"),
    ("RS-080", r"46,000 (homes|NSW properties)|homes without power as destructive winds", "2026-09-04", "2026-09-06"),
    ("RS-081", r"Mildura.*(power|outage)|without power around Mildura", "2026-09-21", "2026-09-23"),
    ("RS-082", r"Telstra.*(outage report finds|external expert findings|investigation finds|timing experts|outage exposed years|investigation reveals|investigation into July|lack of oversight)", "2026-09-01", "2026-09-03"),
    ("RS-083", r"Lack Of Reserve.*NSW", "2026-10-09", "2026-10-12"),
    ("RS-084", r"104 flights cancelled|Sydney Airport.*cancel", "2026-11-16", "2026-11-16"),
    # Origin: RS-042 = onset detection (22-24 Jul); RS-042#dev = all lifecycle developments (informational).
    ("RS-042", r"Origin.*(breach|hack|customer data|bank account)|Personal and banking details", "2026-07-22", "2026-07-24"),
    ("RS-042#dev", r"Origin Energy.*(breach|hack|cyber|data|card|Accenture|fires employee)|Origin customers|dark web.*Origin|Personal and banking details", "2026-07-22", "2026-10-21"),
]
# v1 records whose title pattern changes in v3 (all others keep their v1 pattern and window).
OVERRIDES = {
    "RS-030": (r"Eyre Peninsula|transmission towers|ElectraNet|post-blackout", "2026-11-17", "2026-11-24"),
}
SKIP_V1 = {"RS-042"}  # replaced by NEW_SPECS entries above


def specs(v1_path: Path | None = None):
    v1 = json.loads((v1_path or REF_DIR / "reference_set_v1.json").read_text(encoding="utf-8"))
    out = []
    for inc in v1["incidents"]:
        if inc["id"] in SKIP_V1:
            continue
        if inc["id"] in OVERRIDES:
            out.append((inc["id"], *OVERRIDES[inc["id"]]))
            continue
        m = (inc.get("tjr_detection") or {}).get("match") or {}
        if m.get("title_regex") and m.get("published_from") and m.get("published_to"):
            out.append((inc["id"], m["title_regex"], m["published_from"], m["published_to"]))
    return out + NEW_SPECS


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


# Records whose conversion channels are measured (material categories). Detection is measured for every record.
CONVERSION_IDS = ["RS-001", "RS-002", "RS-003", "RS-008", "RS-009", "RS-011", "RS-028", "RS-029", "RS-030", "RS-031", "RS-032", "RS-033",
                  "RS-034", "RS-042", "RS-054", "RS-055", "RS-056", "RS-057", "RS-058", "RS-059", "RS-060", "RS-061", "RS-062", "RS-063",
                  "RS-064", "RS-065", "RS-066", "RS-075", "RS-077", "RS-079", "RS-080", "RS-081", "RS-082", "RS-083"]
DETECTION_COLUMNS = COLUMNS[:14]
CONVERSION_COLUMNS = ["id", "daily_briefs_mentioning", "first_daily_brief_date", "intelligence_briefs_forward_watch",
                      "intelligence_briefs_other_sections", "first_intelligence_brief_date", "products_mentioning"]


def _values(rows):
    return ",\n".join(f"({_q(i)},{_q(rx)},{_q(f)}::date,{_q(t)}::date)" for i, rx, f, t in rows)


def detection_sql(v1_path: Path | None = None, chunk: tuple[int, int] | None = None) -> str:
    rows = specs(v1_path)
    if chunk:  # the table scan is regex-per-record: run in slices to stay under the 60 s SQL tool limit
        i, n = chunk
        rows = rows[i::n]
    return f"""-- SELECT only. Reference set v3 detection block per record (scorecard match window: published_at in [from-1d, to+2d)).
with r(id, rx, f, t) as (values
{_values(rows)}
), m as (
  select r.id, e.event_id, s.source_name, e.published_at, e.collected_at, e.disposition, e.brief_id, e.suppressed,
         coalesce(e.publisher_family, s.source_name) fam, (s.source_name ~* '^Google News') agg, e.raw_title
  from r join intelligence_events e on e.raw_title ~* r.rx and e.published_at >= r.f - 1 and e.published_at < r.t + 2
  join intelligence_source_registry s using (source_id)
), first as (
  select distinct on (id) id, event_id, source_name, published_at, collected_at, raw_title from m order by id, collected_at
), agg as (
  select id, count(*) n, min(published_at) min_pub, count(distinct source_name) n_src,
         count(distinct fam) filter (where not agg) n_nonagg, count(*) filter (where brief_id is not null) n_brief_id,
         count(*) filter (where suppressed) n_supp,
         count(*) filter (where disposition in ('BRIEF','ESCALATE')) n_brief_or_esc,
         count(*) filter (where disposition = 'ESCALATE') n_esc
  from m group by id
)
select json_build_array(a.id, a.n, f.collected_at, f.published_at, a.min_pub, f.source_name, left(f.raw_title,110), f.event_id::text,
       a.n_src, a.n_nonagg, a.n_brief_id, a.n_supp, a.n_brief_or_esc, a.n_esc) as row
from agg a join first f using (id) order by a.id"""


def conversion_sql(v1_path: Path | None = None) -> str:
    rows = [s_ for s_ in specs(v1_path) if s_[0] in CONVERSION_IDS]
    return f"""-- SELECT only. Reference set v3 conversion channels (daily brief text, intelligence_briefs sections, intelligence_products).
with r(id, rx, f, t) as (values
{_values(rows)}
), cdb as (
  select r.id, count(b.id) n, min(b.brief_date) first_date from r left join captains_daily_briefs b
    on b.brief_date >= r.f - 1 and b.brief_date <= r.t + 7 and b.brief_text ~* r.rx group by r.id
), ib as (
  select r.id,
         count(b.brief_id) filter (where b.forward_watch::text ~* r.rx) n_fw,
         count(b.brief_id) filter (where (b.top_events::text || coalesce(b.executive_snapshot,'') || b.emerging_themes::text) ~* r.rx) n_other,
         min(b.generated_at::date) filter (where (b.forward_watch::text || b.top_events::text || coalesce(b.executive_snapshot,'') || b.emerging_themes::text) ~* r.rx) first_date
  from r left join intelligence_briefs b on b.generated_at::date >= r.f - 1 and b.generated_at::date <= r.t + 7 group by r.id
), ip as (
  select r.id, count(p.product_key) filter (where (coalesce(p.body_md,'') || coalesce(p.summary,'')) ~* r.rx) n_prod
  from r left join intelligence_products p on p.generated_for >= r.f - 1 and p.generated_for <= r.t + 7 group by r.id
)
select json_build_array(c.id, c.n, c.first_date, coalesce(i.n_fw,0), coalesce(i.n_other,0), i.first_date, coalesce(p.n_prod,0)) as row
from cdb c join ib i using (id) join ip p using (id) order by c.id"""


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--print-detection-sql" in argv:
        chunk = None
        if "--chunk" in argv:
            a, b = argv[argv.index("--chunk") + 1].split("/")
            chunk = (int(a), int(b))
        print(detection_sql(chunk=chunk))
        return 0
    if "--print-conversion-sql" in argv:
        print(conversion_sql())
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
