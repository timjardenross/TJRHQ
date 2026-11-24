#!/usr/bin/env python3
"""Build knowledge/intelligence-reference-set/reference_set_v3.json (offline, deterministic).

Inputs (all read-only, none modified): reference_set_v1.json (frozen), reference_set_v2_candidates.json (frozen),
measurements_v3-2026-11-24.json (production SELECT output), events_export_2026-11-24.json (frozen; a corrected copy is written beside it).
Decisions, corrections and the new records live in reference_set_v3_records.py. Re-running reproduces the committed files byte for byte
(tests/test_reference_set_v3.py enforces it).

    python tools/intelligence/build_reference_set_v3.py            # writes reference_set_v3.json and events_export_v3-2026-11-24.json
    python tools/intelligence/build_reference_set_v3.py --check    # exit 1 if the committed files differ from a fresh build
"""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
for _p in (str(_REPO), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import reference_set_v3_measure as M
import reference_set_v3_records as R

from intelligence import weekly_evidence as we

REF_DIR = _REPO / "knowledge" / "intelligence-reference-set"
OUT = REF_DIR / "reference_set_v3.json"
OUT_EXPORT = REF_DIR / "events_export_v3-2026-11-24.json"

DET_COLS = M.DETECTION_COLUMNS
CONV_COLS = M.CONVERSION_COLUMNS

# v1 records covered by the owner's review decisions (KEEP / RECLASSIFY lines of the decisions block): marked reviewed_by_human=true.
V1_REVIEWED = {"RS-001", "RS-002", "RS-003", "RS-004", "RS-005", "RS-008", "RS-009", "RS-011", "RS-028", "RS-029", "RS-030", "RS-031", "RS-032",
               "RS-033", "RS-034", "RS-042", "RS-051"}

CANDIDATE_DISPOSITION = {
    "C2-001": "RS-054", "C2-002": "RS-075", "C2-003": "RS-055", "C2-004": "RS-056", "C2-005": "RS-057", "C2-006": "RS-076", "C2-007": "RS-077",
    "C2-008": "RS-067", "C2-009": "RS-058", "C2-010": "RS-059", "C2-011": "RS-060", "C2-012": "RS-078", "C2-013": "RS-061", "C2-014": "RS-062",
    "C2-015": "RS-071 (duplicate_report of RS-066)", "C2-016": "RS-079", "C2-U01": "RS-063", "C2-U02": "RS-068",
    "C2-U03": "folded into RS-042 as lifecycle development 2026-08-21 (not a separate incident; id kept in RS-042.folded_candidates)",
    "C2-U04": "alias of RS-051 (duplicate_report of RS-003); same item, no second record", "C2-U05": "RS-069", "C2-U06": "RS-072 (hold)",
    "C2-U07": "RS-073 (hold)", "C2-U08": "RS-070", "C2-U09": "RS-074 (hold)", "M-01": "RS-064", "M-02": "RS-065", "M-03": "RS-066", "M-04": "RS-080",
    "M-05": "RS-081", "Q3-finding": "RS-082 (new: retrospective finding from RS-005)", "Q8-signal": "RS-083 (new: forward-looking signal from RS-004)",
    "Q4-flights": "RS-084 (assessed: non-material, no qualifier evidenced)"}


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _kind(src):
    return we.source_kind(src or "") if src else None


def detection_block(rid, match, det_rows, conv_rows, v1_block=None):
    base = {"queried_at": "2026-11-24", "measured": True, "match": {"title_regex": match[0], "published_from": match[1], "published_to": match[2]},
            "method": "intelligence_events.raw_title ~* regex AND published_at in [from-1d, to+2d); read-only SELECT 2026-11-24 (published_at post +10h RSS repair); see measurements_v3-2026-11-24.json"}
    row = det_rows.get(rid)
    if row is None:
        base.update(appeared=False, n_events=0, first_collected_at=None, first_published_at=None, first_source=None, first_source_kind=None,
                    first_headline=None, n_distinct_sources=0, n_non_aggregator_sources=0, events_with_brief_id=0, events_suppressed=0,
                    events_brief_or_escalate=0, events_escalate=0)
    else:
        d = dict(zip(DET_COLS, row))
        base.update(appeared=d["n_events"] > 0, n_events=d["n_events"], first_collected_at=d["first_collected_at"], first_published_at=d["first_published_at"],
                    earliest_published_at=d["earliest_published_at"], first_source=d["first_source"], first_source_kind=_kind(d["first_source"]),
                    first_headline=d["first_headline"], first_event_id=d["first_event_id"], n_distinct_sources=d["n_distinct_sources"],
                    n_non_aggregator_sources=d["n_non_aggregator_families"], events_with_brief_id=d["events_with_brief_id"],
                    events_suppressed=d["events_suppressed"], events_brief_or_escalate=d["events_brief_or_escalate"], events_escalate=d["events_escalate"])
    c = conv_rows.get(rid)
    if c is None:
        base["conversion"] = {"measured": False, "converted": None, "status": "NOT PROVIDED (conversion not measured for this record)"}
    else:
        cd = dict(zip(CONV_COLS, c))
        ev_brief = base.get("events_with_brief_id", 0)
        chans = {"event_brief_id": ev_brief, "daily_briefs_mentioning": cd["daily_briefs_mentioning"], "first_daily_brief_date": cd["first_daily_brief_date"],
                 "intelligence_briefs_forward_watch": cd["intelligence_briefs_forward_watch"], "intelligence_briefs_other_sections": cd["intelligence_briefs_other_sections"],
                 "first_intelligence_brief_date": cd["first_intelligence_brief_date"], "products_mentioning": cd["products_mentioning"]}
        converted = bool(ev_brief or cd["daily_briefs_mentioning"] or cd["intelligence_briefs_forward_watch"] or cd["intelligence_briefs_other_sections"] or cd["products_mentioning"])
        base["conversion"] = {"measured": True, "converted": converted, **chans,
                              "caveat": "brief/product surfacing is a title-pattern match over stored text (weaker than brief_id); a False result means no match was found, not proof of absence"}
    base["daily_briefs_mentioning"] = (base["conversion"].get("daily_briefs_mentioning") if base["conversion"]["measured"] else None)
    if base["conversion"]["measured"]:
        base["first_daily_brief_date"] = base["conversion"]["first_daily_brief_date"]
    return base


def build():
    v1 = _load(REF_DIR / "reference_set_v1.json")
    cand = _load(REF_DIR / "reference_set_v2_candidates.json")
    meas = _load(REF_DIR / "measurements_v3-2026-11-24.json")
    C = {i["id"]: i for i in cand["incidents"]}
    det_rows = {r[0]: r for r in meas["detection_rows"]}
    conv_rows = {r[0]: r for r in meas["conversion_rows"]}
    spec = {i: (rx, f, t) for i, rx, f, t in M.specs()}
    corr = {c["id"]: c for c in R.CORRECTIONS}

    recs = []
    for inc in v1["incidents"]:
        r = copy.deepcopy(inc)
        rid = r["id"]
        r["tjr_detection_v1"] = copy.deepcopy(inc.get("tjr_detection"))
        if rid in spec:
            r["tjr_detection"] = detection_block(rid, spec[rid], det_rows, conv_rows)
        r["set_membership"] = r.get("set_membership", "v0")
        r["v1_status"] = inc["status"]
        # category
        st = r["status"]
        if st == "confirmed_material":
            cat, why = R.V1_CATEGORY.get(rid, (R.NONMAT, "reclassified below (owner Q3/Q8)"))
        elif st == "unresolved_insufficiently_verified":
            cat, why = R.UNRES, "Insufficiently verified in v1; carried unchanged; never scored."
        else:
            cat, why = R.NONMAT, "Negative / duplicate / stale record carried from v1; not scored."
        r["intelligence_category"], r["category_rationale"] = cat, why
        r["reviewed_by_human"] = rid in V1_REVIEWED
        r["decision"] = ({"decided_by": "owner", "decided_on": R.APPLIED_ON, "basis": "review decisions block (KEEP/RECLASSIFY)", "instruction": "owner accepted the review defaults"}
                         if rid in V1_REVIEWED else {"decided_by": "not reviewed in this pass", "basis": "carried unchanged from v1"})
        r["audit_trail"] = []
        recs.append(r)
    by = {r["id"]: r for r in recs}

    def audit(rid, cid, **extra):
        c = corr[cid]
        by[rid]["audit_trail"].append({"id": cid, "field": c["field"], "previous_value": c["previous_value"], "corrected_value": c["corrected_value"],
                                       "evidence": c["evidence"], "reason": c["reason"], "date_applied": R.APPLIED_ON, "applied_by": R.APPLIED_BY, **extra})

    def tset(rid, key, value, source):
        by[rid][key] = {**by[rid].get(key, {}), "value": value, "source": source}

    # CORR-01 RS-030
    r = by["RS-030"]
    tset("RS-030", "first_public_report_time", "2026-11-19T06:59:07Z", "ABC News 735f411c 'Breaking: Transmission towers crushed' (CORR-01)")
    r["start_time_utc"] = {"value": "2026-11-19T06:59:07Z", "source": "upper bound: not later than the first ABC report (CORR-01); the AEMO statement time (08:00Z) is later", "confidence": "low"}
    r["q4_assessment"] = {"rule": "Q4 automatic inclusion: >=20,000 premises, or 24 h with a critical service affected", "threshold_applied": ">=20,000 premises",
                          "premises_stated": "more than 20,000 properties (ABC headline 735f411c); about 23,000-24,000 (v1 sources)", "qualifiers_evidenced": [], "qualifiers_not_evidenced": [],
                          "result": "material (accepted before Q4; consistent with the rule)"}
    audit("RS-030", "CORR-01")
    # CORR-02 RS-003, CORR-03 RS-002
    tset("RS-003", "first_public_report_time", "2026-09-12T00:52:41Z", "ABC News ee8f9734 (CORR-02); The Age/Google News 2026-09-11T07:00:00Z is a placeholder")
    audit("RS-003", "CORR-02")
    tset("RS-002", "first_public_report_time", "2026-09-23T20:31:06Z", "ABC News af9d4ebd (CORR-03)")
    audit("RS-002", "CORR-03")
    # SUPP-01 RS-029
    tset("RS-029", "first_public_report_time", "2026-11-03T15:06:00Z", "earliest TJR row, iTnews c75e3f2c (SUPP-01); not necessarily the first public report")
    audit("RS-029", "SUPP-01")
    # CORR-05 RS-008 (export file corrected beside the frozen one)
    audit("RS-008", "CORR-05", events_export_file="events_export_v3-2026-11-24.json")
    # CORR-06 RS-051 + alias C2-U04
    r = by["RS-051"]
    r["aliases"] = ["C2-U04"]
    r["tjr_detection"] = {"queried_at": "2026-11-24", "measured": True, "match": {"title_regex": None, "published_from": None, "published_to": None}, "appeared": True, "n_events": 1,
                          "first_collected_at": "2026-09-16T07:16:46Z", "first_published_at": "2026-09-15T02:50:53Z", "first_source": "Google News - Telstra", "first_source_kind": "aggregator",
                          "first_headline": "Another Optus mobile outage blocks 46 Triple Zero calls (Information Age via Google News)", "first_event_id": "86d6455f-6c84-4c67-8ead-46ba3df4a670",
                          "events_with_brief_id": 0, "conversion": {"measured": False, "converted": None, "status": "NOT PROVIDED"},
                          "note": "evidence row for the duplicate (CORR-06); counted under RS-003, never scored"}
    audit("RS-051", "CORR-06")

    # Q2 RS-042 Origin: parent incident, lifecycle (C2-U03 folded in)
    r = by["RS-042"]
    r.update(title="Origin Energy customer data breach: ONE incident, onset 22-23 Jul 2026 (announced 22 Jul, confirmed 23 Jul), with dated material developments through 20 Oct 2026",
             status="confirmed_material", intelligence_category=R.MOD,
             category_rationale="Confirmed customer data breach at a major energy retailer: an incident; later developments are lifecycle entries of the same incident.",
             non_material_type=None, is_negative_example=False, record_kind="incident", folded_candidates=["C2-U03"],
             australian_materiality={"level": "high", "reason": "4.8m customer accounts (Guardian summary); names, addresses, DOB, phone numbers and some bank account details accessed."})
    r["start_time_utc"] = {"value": "2026-07-22T00:00:00Z", "source": "ABC 23 Jul: confirmation came 'a day after it announced it was investigating a potential breach' (row 51c45104); time of day not known", "confidence": "medium"}
    r["first_public_report_time"] = {"value": "2026-07-22T21:25:25Z", "source": "ABC News Business 80e2b0ab live-blog item (earliest TJR row); TJR collected every onset row in the 2026-07-23 20:00Z batch"}
    r["onset_before_window_start"] = True
    r["decision"] = R.owner("owner Q2", "Q2: Origin Energy is ONE material incident with multiple lifecycle developments; preserve the original incident date (onset 22-23 Jul) and each subsequent material development separately as dated lifecycle entries with their own evidence; RS-042 becomes the parent (confirmed_material); C2-U03 folded in as a development, id kept traceable", "RS-042 / C2-U03")
    r["lifecycle"] = [
        {"date": "2026-07-22", "kind": "onset", "development": "Origin announced it was investigating a 'potential' breach (statement as reported in row 51c45104; the announcement itself is not a TJR row)",
         "evidence": [R.ev("80e2b0ab-cc70-4173-b430-0fad97eff2f3", "ABC News Business", "2026-07-22T21:25:25Z", "2026-07-23T20:00:14Z", "SUPPRESS", "Origin Energy shares drop back slightly after company admits data hack - as it happened")]},
        {"date": "2026-07-23", "kind": "confirmation", "development": "Origin confirmed unauthorised access to and disclosure of some customers' data; names, addresses, DOB, phone numbers and some bank account details (4.8m customer accounts)",
         "evidence": [R.ev("51c45104-579e-4132-a1b9-e6b06092b84f", "ABC News Business", "2026-07-23T05:49:16Z", "2026-07-23T20:00:14Z", "WATCH", "Origin Energy confirms breach of customer data"),
                      R.ev("4544637e-4382-4290-9021-ed8e2121d6db", "Guardian Australia", "2026-07-23T09:55:27Z", "2026-07-23T20:00:13Z", "REFERENCE", "Personal and banking details among customer data stolen in Origin Energy hack"),
                      R.ev("165e4272-ac99-4b78-bd25-4369782a9772", "ABC News", "2026-07-23T19:04:19Z", "2026-07-23T20:00:13Z", "WATCH", "Origin breach could fuel wave of AI-powered scams, cyber experts warn")]},
        {"date": "2026-08-21", "kind": "development", "source_candidate": "C2-U03", "development": "As many as 60 customers had full bank account numbers accessed by a hacker in July (ID numbers per headline); customer data not leaked or disclosed publicly (ABC summary)",
         "evidence": [R.ev("abec8447-55b9-4ca2-98b7-2db51f69c94b", "ABC News Business", "2026-08-21T01:06:18Z", "2026-08-21T20:01:10Z", "SUPPRESS", "Dozens of Origin customers' full bank accounts, ID numbers accessed in breach", note="TJR suppressed it (detection miss on a development)")]},
        {"date": "2026-08-24", "kind": "development", "development": "Cyber attack traced to a former Accenture employee in Manila (teiss via Google News; headline only, unverified)",
         "evidence": [R.ev("cf50b56d-0902-4c8c-92a5-81f115a45101", "Google News - Origin Energy", "2026-08-24T07:00:00Z", "2026-09-06T01:03:13Z", "BRIEF", "News - Origin Energy cyber attack traced to former Accenture employee in Manila - teiss", note="published_at is a date-only placeholder; collected 13 days later")]},
        {"date": "2026-09-10", "kind": "development", "development": "Origin fires an employee believed to be behind the breach (Nine via Google News; headline only)",
         "evidence": [R.ev("62659383-c14a-4fe9-8ce3-218de7d7a837", "Google News - Origin Energy", "2026-09-10T07:00:00Z", "2026-09-19T19:08:06Z", "WATCH", "Origin Energy fires employee believed to be behind recent data breach - Nine.com.au", note="published_at is a date-only placeholder")]},
        {"date": "2026-10-14", "kind": "development", "development": "'No evidence customer data published on dark web: Origin' (Michael West Media via Google News; headline only)",
         "evidence": [R.ev("1de5be2a-f681-4a64-b0ae-c4051c4fdb81", "Google News - Origin Energy", "2026-10-14T00:45:58Z", "2026-10-19T20:00:45Z", "REFERENCE", "No evidence customer data published on dark web: Origin - Michael West Media")]},
        {"date": "2026-10-20", "kind": "development", "development": "Breach reported to expose customer and partial card details (TechRepublic via Google News; headline only)",
         "evidence": [R.ev("3efc320e-3829-44c8-80b7-73250a36a78a", "Google News - Origin Energy", "2026-10-20T16:23:06Z", "2026-10-22T04:56:47Z", "WATCH", "Origin Energy Data Breach Exposes Customer and Partial Card Details - TechRepublic")]}]
    r["lifecycle_note"] = "The onset (22-23 Jul) precedes the 2026-07-28 window start, so the incident is reported as pre_window (excluded from period rates); the Aug-Oct developments fall inside the window."
    r["uncertain_facts"] = ["Developments of 24 Aug, 10 Sep, 14 Oct and 20 Oct rest on headlines of aggregator copies only; their articles were not read.",
                            "The 21 Aug headline says 'full bank accounts, ID numbers'; the ABC summary says 'full bank account numbers' for as many as 60 customers.",
                            "v1 measured 8 'Origin' rows as share/battery stories with a Sep-Nov window; the v3 onset pattern/window finds the breach rows."]
    r["sources"] = r.get("sources", [])
    r["audit_trail"].append({"id": "RECLASS-03", "field": "status, intelligence_category, record_kind, lifecycle",
                             "previous_value": {"status": "stale_or_resurfaced", "non_material_type": "old_event_resurfacing", "is_negative_example": True},
                             "corrected_value": {"status": "confirmed_material", "intelligence_category": R.MOD, "lifecycle_entries": 7, "folded_candidates": ["C2-U03"]},
                             "evidence": [e["event_id"] for l in r["lifecycle"] for e in l["evidence"]],
                             "reason": "owner Q2: one material incident with in-window developments; the v1 'stale' label rested on the 1 Sep window rule, and TJR rows show the breach kept developing in-window.",
                             "date_applied": R.APPLIED_ON, "applied_by": R.APPLIED_BY})

    # Q8 RS-004
    r = by["RS-004"]
    r.update(status="confirmed_non_material", intelligence_category=R.NONMAT, non_material_type="market_event_no_supply_loss", is_negative_example=True,
             category_rationale="Price spike with no supply loss: non-material for actual disruption detection; its forward-looking risk signal is retained as RS-083.",
             related_ids=["RS-083"])
    r["decision"] = R.owner("owner Q8", "Q8: NON-MATERIAL for actual disruption detection but RETAIN as a potentially material forward-looking risk signal (see RS-083)", "RS-004")
    r["forward_signal_detection"] = {"carried_by": "RS-083", "note": "CORR-04: appeared=true for the signal via AEMO Market Notices 7763f981, 9e56c031, 553633dd"}
    audit("RS-004", "CORR-04")
    r["audit_trail"].append({"id": "RECLASS-01", "field": "status, intelligence_category, non_material_type", "previous_value": {"status": "confirmed_material"},
                             "corrected_value": {"status": "confirmed_non_material", "non_material_type": "market_event_no_supply_loss", "intelligence_category": R.NONMAT},
                             "evidence": ["v1 australian_materiality.reason: 'Market-price event, no reported supply loss or load shedding'", "no AEMO/AER primary confirmation of the price event"],
                             "reason": "owner Q8", "date_applied": R.APPLIED_ON, "applied_by": R.APPLIED_BY})
    # Q3 RS-005
    r = by["RS-005"]
    r.update(status="stale_or_resurfaced", intelligence_category=R.NONMAT, non_material_type="retrospective_old_event_update", is_negative_example=True,
             category_rationale="Follow-up to an out-of-window outage: retrospective for incident-detection scoring; the findings are retained as RS-082.",
             superseded_by_finding_record="RS-082", related_ids=["RS-082"])
    r["decision"] = R.owner("owner Q3", "Q3: reclassify RS-005 as retrospective for incident-detection scoring; keep the findings as a separate material retrospective finding (RS-082)", "RS-005")
    r["audit_trail"].append({"id": "RECLASS-02", "field": "status, intelligence_category, non_material_type, dates", "previous_value": {"status": "confirmed_material", "record_kind": "follow_up_development", "first_public_report_time": "2026-10-12T21:20:42Z (AGM coverage)"},
                             "corrected_value": {"status": "stale_or_resurfaced", "non_material_type": "retrospective_old_event_update", "intelligence_category": R.NONMAT, "note": "TAP findings were public on 1-2 Sep (rows in RS-082), not 12 Oct; Oct dates are the AGM"},
                             "evidence": ["1b59921d-abf0-4725-b1ac-b60efc5607c1", "410d2d7a-5d3b-4395-8b63-439208366a7d"], "reason": "owner Q3", "date_applied": R.APPLIED_ON, "applied_by": R.APPLIED_BY})

    # new records
    new = R.new_records(C) + R.owner_amended_records(C)
    new.sort(key=lambda x: x["id"])
    for n in new:
        rid = n["id"]
        n["tjr_detection"] = detection_block(rid, spec[rid], det_rows, conv_rows)
        n["audit_trail"] = []
        recs.append(n)
        by[rid] = n
    # Q9 audit entry for RS-077, Q5/Q7 notes, Q4 outcomes recorded in their records
    for cid, rid in (("CORR-07", "RS-054"), ("CORR-08", "RS-059"), ("CORR-09", "RS-060"), ("CORR-10", "RS-071"), ("CORR-11", "RS-079"), ("CORR-12", "RS-063"), ("SUPP-02", "RS-080")):
        audit(rid, cid)
    by["RS-079"]["start_time_utc"]["source"] = "ABC article read this session: 'between 8:11 and 8:15pm on November 19' (AEDT) (CORR-11)"
    by["RS-080"]["start_time_utc"]["source"] = "'late Saturday afternoon' (Nine body text), Endeavour Energy post 'Saturday 5pm' (search excerpt); about 07:00Z (SUPP-02)"
    by["RS-080"]["first_public_report_time"]["source"] = "approximate: Endeavour Energy post 'Saturday 5pm' / Nine body text; the TJR row's 2026-09-04T07:00:00Z is a date-only placeholder that precedes the event (SUPP-02)"
    by["RS-077"]["audit_trail"].append({"id": "Q9", "field": "status", "previous_value": "candidate C2-007: lean unresolved/hold (scale unknown)", "corrected_value": "confirmed_material (medium confidence)",
                                        "evidence": ["ABC article 107061960 read 2026-11-24", "Aero South Pacific article read 2026-11-24", "search excerpts (Facebook/Instagram/Fijivillage titles) not relied on"],
                                        "reason": "owner Q9: resolve if the evidence allows; two sources read give scale, duration and multi-carrier impact", "date_applied": R.APPLIED_ON, "applied_by": R.APPLIED_BY})
    for rid, lim in COVERAGE_LIMITS.items():
        by[rid]["coverage_limits"] = lim
    for r in recs:
        r.setdefault("coverage_limits", [])
    recs.sort(key=lambda x: x["id"])

    # ---- counts and header -----------------------------------------------------------------------------------------------------------
    by_status = Counter(r["status"] for r in recs)
    by_cat = Counter(r["intelligence_category"] for r in recs)
    mat = [r["id"] for r in recs if r["status"] == "confirmed_material"]
    audit_all = []
    for r in recs:
        for a in r["audit_trail"]:
            audit_all.append({"record": r["id"], **a})
    header = {
        "schema_version": "2.0", "name": "intelligence-reference-set", "set_version": "v3",
        "supersedes": "v1 (reference_set_v1.json, frozen) via the v2 candidates review; v0 and v1 files are untouched",
        "window": "2026-07-28..2026-11-24 (end exclusive); the v1 window was 2026-09-01..2026-11-24",
        "created_utc": "2026-11-24T10:00:00Z",
        "status": "REVIEWED: the owner decided every record in the review pack on 2026-11-24 (scope in review.reviewed_record_ids); v1 records outside that review are carried unchanged and remain reviewed_by_human=false",
        "review": {"reviewed_by_human": True, "reviewer": "owner", "date": R.APPLIED_ON, "decision_pointer": R.OWNER_POINTER,
                   "scope": "reviewed_by_human=true on every v3-new record and on the v1 records the review pack addressed (KEEP/RECLASSIFY lines). The other v1 records (negatives, stale, unresolved, duplicates the pack did not touch) are carried unchanged and stay false: the owner did not review them item by item.",
                   "reviewed_record_ids": sorted(r["id"] for r in recs if r["reviewed_by_human"]),
                   "not_reviewed_record_ids": sorted(r["id"] for r in recs if not r["reviewed_by_human"]),
                   "evidence_of_decisions": "each record's `decision` block states the owner question (Q1-Q9) or the review-pack line it came from; the owner's answers are held verbatim in decision_register",
                   "applied_by": R.APPLIED_BY},
        "statuses": ["confirmed_material", "confirmed_non_material", "stale_or_resurfaced", "duplicate_report", "unrelated_incident", "unresolved_insufficiently_verified"],
        "intelligence_categories": list(R.CATEGORIES),
        "status_to_category_mapping": R.STATUS_TO_CATEGORY_RULE,
        "mapping_note": "`status` keeps the v1 vocabulary for compatibility; `intelligence_category` is the explicit v3 field. confirmed_material maps to exactly one of the three material_* categories (decided on evidence, one-line category_rationale per record); confirmed_non_material, stale_or_resurfaced, unrelated_incident and duplicate_report map to non_material; unresolved_insufficiently_verified maps to unresolved. tests/test_reference_set_v3.py enforces the mapping.",
        "scoring_rules": {
            "detection": "scored against intelligence_category == material_operational_disruption ONLY (appeared in TJR events; time to first detection reported, not a score)",
            "emerging_risk_or_warning": "assessed on whether TJR detected the signal AND converted it (event brief_id, daily brief text, intelligence_briefs forward_watch/other sections, intelligence_products); where conversion was not measured the report says NOT PROVIDED, never an estimate",
            "retrospective_finding": "assessed on whether the finding was collected and surfaced as intelligence (same conversion channels); not an incident-detection test",
            "non_material_and_unresolved": "excluded from every score and listed; false escalation is shown as information only"},
        "observation_periods": {"definition": "7 consecutive UTC days from 2026-07-28 (P01..P17); incident period = period of first_public_report_time; first report before 2026-07-28 = pre_window. Coverage state per period comes from coverage_v3-2026-11-24.json plus intelligence/longitudinal_trends.COVERAGE_CHANGES; periods with incomplete coverage are reported separately and excluded from rate comparisons."},
        "decision_register": DECISIONS,
        "candidate_disposition_map": CANDIDATE_DISPOSITION,
        "audit_trail": audit_all,
        "counts": {"records": len(recs), "by_status": dict(sorted(by_status.items())), "by_intelligence_category": dict(sorted(by_cat.items())),
                   "confirmed_material_ids": mat, "material_count_note": "No target: the count is what the evidence supports (owner instruction)."},
        "measurement_provenance": {"evidence_rows_verified": "74 distinct TJR event ids cited in evidence/lifecycle blocks were re-checked against production intelligence_events on 2026-11-24 (SELECT): all exist; published_at, collected_at (to the second) and disposition match the stored values wherever a value is stored (a0e63dcd and 575358f7 carry partial fields by design; one CISA KEV disposition was corrected during the check)",
                                   "tjr_detection": "measurements_v3-2026-11-24.json (read-only SELECT 2026-11-24); previous v1 blocks kept in tjr_detection_v1", "coverage": "coverage_v3-2026-11-24.json",
                                   "unverified": "incident facts taken from web pages are marked per evidence basis (tjr_row | review_pack_web_read | session_web_read); anything without those is unverified"},
        "caveats": ["tjr_detection is title-pattern based and indicative; Google News published_at values are often date-only placeholders.",
                    "Evidence entries with basis review_pack_web_read were read by the reviewer, not re-read in this session; basis session_web_read were read while building v3.",
                    "collected_at is batch time (feed polling and collection lag included)."],
        "incidents": recs}
    export = _load(REF_DIR / "events_export_2026-11-24.json")
    export["events"] = [e for e in export["events"] if e["event_id"] not in ("gnrest01", "itnrec01")]
    export["corrections"] = [{"id": "CORR-05", "removed_event_ids": ["gnrest01", "itnrec01"], "reason": "hand-added synthetic ids; no production rows", "date_applied": R.APPLIED_ON, "applied_by": R.APPLIED_BY,
                              "source_file": "events_export_2026-11-24.json (frozen, unchanged)"}]
    export["sampling"] = export["sampling"].replace(", plus 2 rows added by hand for RS-008 recovery-claim review", " (the 2 hand-added RS-008 rows were removed in v3, CORR-05)")
    return header, export


# Per-record source-coverage limits that are evidenced by the coverage file / registry SELECTs (persistent source gaps, not a property of a week).
COVERAGE_LIMITS = {
    "RS-032": ["no ASX announcements source exists in intelligence_source_registry (no active source with 'ASX' in its name, SELECT 2026-11-24); the ASX announcement (2026-10-01T23:03Z) came within an hour of the 2-4 Oct no-collection gap (zero reports collected on those days)"],
    "RS-003": ["Optus National Outage Register was registered and began collecting only on 2026-11-24; the Downdetector AU - Optus feed has stored no events; detection came from news items"],
    "RS-082": ["ARN - Australian IT Channel and the Google News feeds were added on 2026-09-06, after the 1-2 Sep publications: first collection was 4.1 days after first publication (COVERAGE_CHANGES 2026-09-06)"],
    "RS-080": ["the event (2026-09-05) precedes the 2026-09-06 feed-ceiling step (mainstream volume about 4x lower; Google News, iTnews and ARN not yet added); the only TJR row is a Google News copy collected 2026-09-16"]}


DECISIONS = [
    {"question": "Q1", "decision": "Extend the reference window to 2026-07-28; baselines use consistent observation periods and report incomplete-coverage periods separately, excluded from rate comparisons", "applied_in": "observation_periods; coverage_v3-2026-11-24.json; weekly_baseline.py"},
    {"question": "Q2", "decision": "Origin Energy is ONE material incident with dated lifecycle developments; RS-042 is the parent; C2-U03 folded in", "applied_in": "RS-042"},
    {"question": "Q3", "decision": "RS-005 retrospective for detection scoring; findings kept as a material retrospective finding", "applied_in": "RS-005, RS-082"},
    {"question": "Q4", "decision": "20,000 premises or 24 h with a critical service = AUTOMATIC INCLUSION, not exclusion; smaller/shorter can be material on qualifiers; per item outcome recorded in q4_assessment", "applied_in": "RS-061, RS-080, RS-081, RS-084, RS-030, RS-077"},
    {"question": "Q5", "decision": "C2-016 material regardless of duration; two separately sourced attributes preserved", "applied_in": "RS-079"},
    {"question": "Q6", "decision": "C2-006 and C2-012 non-material on current evidence with assessed consequences recorded; no blanket exclusion", "applied_in": "RS-076, RS-078"},
    {"question": "Q7", "decision": "Sydney Airport one parent anchored on 8 Aug with dated developments; cause marked disputed with competing claims", "applied_in": "RS-075"},
    {"question": "Q8", "decision": "RS-004 non-material for disruption; retained as a potentially material forward-looking risk signal", "applied_in": "RS-004, RS-083"},
    {"question": "Q9", "decision": "Read the ABC article and supporting evidence now; resolve the classification if the evidence allows", "applied_in": "RS-077"},
    {"question": "defaults", "decision": "Everything else from the review's default decisions stands: accept list A, reject list B, duplicates, holds; all 12 corrections applied with audit trail", "applied_in": "RS-054..RS-074, audit_trail"},
    {"question": "no_target", "decision": "Do not artificially raise or lower the material count to reach 30", "applied_in": "counts"},
    {"question": "categories", "decision": "Explicit intelligence_category on every record: material_operational_disruption, material_emerging_risk_or_warning, material_retrospective_finding, non_material, unresolved", "applied_in": "every record"}]


def render(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    header, export = build()
    a, b = render(header), render(export)
    if "--check" in argv:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == a and OUT_EXPORT.exists() and OUT_EXPORT.read_text(encoding="utf-8") == b
        print("reference set v3 files match a fresh build" if ok else "reference set v3 files DIFFER from a fresh build")
        return 0 if ok else 1
    OUT.write_text(a, encoding="utf-8")
    OUT_EXPORT.write_text(b, encoding="utf-8")
    c = header["counts"]
    print(f"wrote {OUT.name}: {c['records']} records; by status {c['by_status']}; by category {c['by_intelligence_category']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
