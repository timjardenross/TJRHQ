"""Data for reference set v3: owner decisions, corrections with audit trail, and the records new in v3.

Everything here is applied by build_reference_set_v3.py on top of the FROZEN v1 file and the v2 candidates file. Evidence rule: a fact is
stored only if it was read from a TJR row (intelligence_events, SELECT) or from a source named in ``sources`` that was actually read; each
evidence entry carries ``basis`` (tjr_row | review_pack_web_read | session_web_read) so the reader can see which. Nothing is invented.
"""
from __future__ import annotations

APPLIED_ON = "2026-11-24"
APPLIED_BY = "claude (agent, session_015Lqu25Jrf3fePKgyCU7xa5) applying the owner's decisions"
OWNER_POINTER = ("Owner decisions Q1-Q9 and amendments, given as written instructions to the Intelligence programme lead agent on 2026-11-24 "
                 "(Claude session_015Lqu25Jrf3fePKgyCU7xa5), accepting the defaults of REFERENCE-SET-REVIEW-2026-11-24.md "
                 "(sha256 d7590e44685530a806a2e263486f0db1a72efac0d1d8e66b1e69f7129b29efd5) subject to those amendments")

MATERIAL_CATEGORIES = ("material_operational_disruption", "material_emerging_risk_or_warning", "material_retrospective_finding")
CATEGORIES = MATERIAL_CATEGORIES + ("non_material", "unresolved")
STATUS_TO_CATEGORY_RULE = {
    "confirmed_material": "one of the three material_* categories (decided per record, see category_rationale)",
    "confirmed_non_material": "non_material",
    "stale_or_resurfaced": "non_material",
    "duplicate_report": "non_material (clustered under duplicate_of; never scored)",
    "unrelated_incident": "non_material",
    "unresolved_insufficiently_verified": "unresolved",
}

MOD, MEW, MRF, NONMAT, UNRES = (*MATERIAL_CATEGORIES, "non_material", "unresolved")

# v1 records that are material operational disruptions / warnings (the 15 v1 confirmed minus RS-004, RS-005, plus RS-042 below).
V1_CATEGORY = {
    "RS-001": (MOD, "Named bank outage affecting customers (phone/internet/mobile banking): an operational disruption."),
    "RS-002": (MOD, "Unauthorised access to a government portal by an AI agent: a security incident, not a warning."),
    "RS-003": (MOD, "Exchange failure with failed Triple Zero calls: an operational disruption."),
    "RS-008": (MOD, "Global Microsoft 365 outage with Australian impact: an operational disruption."),
    "RS-009": (MOD, "Retailer cybersecurity incident under investigation: an incident, not a warning."),
    "RS-011": (MOD, "Subsea cable break / faults hitting a wholesale carrier: an operational disruption."),
    "RS-028": (MOD, "Confirmed breach of 1.08M AU/NZ user records: an incident."),
    "RS-029": (MOD, "State-health cyber incident declared a major incident: an incident."),
    "RS-030": (MOD, "Transmission-tower loss cutting power to ~24k properties: an operational disruption."),
    "RS-031": (MEW, "ASD/ACSC CRITICAL alert on Citrix NetScaler zero-days: an advisory/alert, i.e. a warning rather than a disruption."),
    "RS-032": (MOD, "ASX-listed company disclosed a cyber incident: an incident."),
    "RS-033": (MOD, "Territory-wide government network outage: an operational disruption."),
    "RS-034": (MOD, "Government department lost $809k through a telecom-vendor compromise: an incident."),
}

# ---- corrections CORR-01..12 (+ supplementary SUPP-nn found while applying them), each with an audit trail -------------------------------------
# previous / corrected values are as stored in the frozen files (v1 file or v2 candidates file) and in v3.
CORRECTIONS = [
    {"id": "CORR-01", "record": "RS-030", "field": "first_public_report_time, start_time_utc, tjr_detection.first_* (first collected, first published, first source, first headline, n_events, disposition)",
     "previous_value": {"first_public_report_time": "2026-11-19T08:00:00Z (AEMO media statement 7pm AEDT)", "start_time_utc": "2026-11-19T08:00:00Z",
                        "tjr_detection": {"first_collected_at": "2026-11-21T08:44:56Z", "first_published_at": "2026-11-21T07:45:38Z", "first_source": "ABC News",
                                          "first_headline": "Eyre Peninsula residents worried about further blackouts", "n_events": 1, "events_with_brief_id": 0}},
     "corrected_value": {"first_public_report_time": "2026-11-19T06:59:07Z", "start_time_utc": "not later than 2026-11-19T06:59:07Z (upper bound; the AEMO statement time is later than the first ABC report)",
                         "tjr_detection": {"first_collected_at": "2026-11-19T07:07:17Z", "first_published_at": "2026-11-19T06:59:07Z", "first_source": "ABC News",
                                           "first_headline": "Breaking: Transmission towers 'crushed', knocking out power to 20,000", "disposition": "BRIEF",
                                           "n_events": "measured 6 with the v3 pattern (review stated >=5)"}},
     "evidence": ["735f411c-2683-40e8-b19c-2c0dfe5bbe5e (ABC News, pub 2026-11-19T06:59:07Z, col 07:07:17Z, BRIEF)", "4893fe2f-058d-4ef1-88e3-e725b23c5a9a", "342b2fd9-e6a1-46d9-9fbc-692de8464d70",
                  "35c916c9-e410-4822-ae5d-ce0728f59dcd", "f932c96c-ec08-4279-9f15-655bb4203373"],
     "reason": "v1 pattern 'Eyre Peninsula' matched only a later follow-up headline, so v1 recorded detection 2 days late; the first ABC report does not contain the words 'Eyre Peninsula'."},
    {"id": "CORR-02", "record": "RS-003", "field": "first_public_report_time",
     "previous_value": "2026-09-11T07:00:00Z", "corrected_value": "2026-09-12T00:52:41Z",
     "evidence": ["abfb49cc-e92b-4f76-8857-1217076a93b3 (Google News/The Age, published_at 2026-09-11T07:00:00Z is a date-only placeholder, collected 2026-09-20)",
                  "ee8f9734-5e74-47d0-8823-0975ad029988 (ABC News, pub 2026-09-12T00:52:41Z, col 01:32:59Z)"],
     "reason": "the v1 first-report time came from an aggregator placeholder, not a verified report time; the earliest TJR row with a reliable time is the ABC item. An earlier public report (The Age, 11 Sep) probably existed; outage start was never established."},
    {"id": "CORR-03", "record": "RS-002", "field": "first_public_report_time",
     "previous_value": "2026-09-23T00:00:00Z", "corrected_value": "2026-09-23T20:31:06Z",
     "evidence": ["af9d4ebd-be0a-4fbf-8ab4-ebc113d563e2 (ABC News, pub 2026-09-23T20:31:06Z, col 21:12:39Z)"],
     "reason": "the v1 value is a midnight placeholder; the earliest TJR row with a reliable time is the ABC item. A row with published_at 11:38:00Z also matches the pattern (HH:MM:00 pattern suggests an aggregator placeholder) and was not used."},
    {"id": "CORR-04", "record": "RS-004", "field": "tjr_detection.appeared (forward-looking signal)",
     "previous_value": "appeared=false (v1 price-title pattern found no row)", "corrected_value": "true for the forward-looking signal, via AEMO Market Notices (carried by RS-083); RS-004 itself is reclassified non-material (owner Q8) so its own detection is not scored",
     "evidence": ["7763f981-4fb8-4056-842d-6caa7840466f (STPASA forecast LOR1 NSW 12/10, pub 2026-10-09T19:00:23Z)", "9e56c031-7dfc-4670-acaf-1e95b75d4e5a (PDPASA suspect LOR1/LOR2 NSW from 10/10)",
                  "553633dd-0d94-42f2-bd1d-252c67a81a2a (PDPASA forecast LOR1 NSW 12/10, pub 2026-10-11T19:05:22Z, brief_id set)"],
     "reason": "v1 searched price headlines; TJR collected the primary AEMO reserve notices 1-3 days earlier."},
    {"id": "CORR-05", "record": "RS-008", "field": "events_export rows",
     "previous_value": "events_export_2026-11-24.json contains event_id gnrest01 and itnrec01 (hand-added rows)", "corrected_value": "removed in events_export_v3-2026-11-24.json (the frozen v1 export is untouched)",
     "evidence": ["review pack: no row with these ids exists in intelligence_events (synthetic ids)"],
     "reason": "synthetic ids must not appear in an export described as production rows."},
    {"id": "CORR-06", "record": "RS-051", "field": "tjr_detection.appeared; alias C2-U04",
     "previous_value": "appeared=false, n_events=0", "corrected_value": "appeared=true; evidence row 86d6455f-6c84-4c67-8ead-46ba3df4a670 (Google News - Telstra, Information Age copy, pub 2026-09-15T02:50:53Z, col 2026-09-16T07:16:46Z); duplicate_of RS-003; candidate C2-U04 is the same item and is recorded as an alias, not a second record",
     "evidence": ["86d6455f-6c84-4c67-8ead-46ba3df4a670"], "reason": "the same article URL is already a cited source of RS-003; the TJR row exists."},
    {"id": "CORR-07", "record": "RS-054 (candidate C2-001)", "field": "evidence",
     "previous_value": "evidence included 1a0f85b0-f294-42b1-8ae3-ce84873c4354 (ABC 2026-09-09 'Man charged over court data breach asked AI for legal advice')", "corrected_value": "row removed; organisation 'Court Services Victoria' and '28,600 lines' added from the reviewer's read of the ABC article",
     "evidence": ["review pack: the 9 Sep ABC item is about a NSW courts online-registry breach (8,769 restricted documents, Jan-Mar 2025), a different incident"],
     "reason": "wrong incident attached to the record."},
    {"id": "CORR-08", "record": "RS-059 (candidate C2-010)", "field": "first_report; evidence",
     "previous_value": "first_report ABC de43fcb5 2026-10-22T00:48:22Z", "corrected_value": "first_report ACSC 32572cfb-28e7-46b7-87ac-1b5f73597e13 2026-10-21T03:01:26Z; evidence adds a6a5935d-3e8c-487e-abe5-1999aec59f6d and a0e63dcd-f2c0-4cc4-b634-bb506377a0f4",
     "evidence": ["32572cfb-28e7-46b7-87ac-1b5f73597e13 (ACSC 'Critical vulnerabilities in PHP', pub 2026-10-21T03:01:26Z, col 19:00:06Z)"],
     "reason": "the primary ASD alert pre-dates the ABC article."},
    {"id": "CORR-09", "record": "RS-060 (candidate C2-011)", "field": "first_report",
     "previous_value": "2026-10-22T07:00:00Z (Google News copy b28ee180)", "corrected_value": "2026-10-23T01:41:30Z (ABC 4a151322-daa8-41f5-a76d-7d9dc675de8c)",
     "evidence": ["b28ee180-bb1e-4805-bd31-a2ea7fc5adb8 (published_at is a date-only placeholder; TJR collected it 2026-11-04)"], "reason": "aggregator placeholder time is not a report time."},
    {"id": "CORR-10", "record": "RS-071 (candidate C2-015)", "field": "status, duplicate_of",
     "previous_value": "candidate (promotion_if_reviewed confirmed_material)", "corrected_value": "duplicate_report, duplicate_of RS-066 (Bookeasy, candidate M-03)",
     "evidence": ["review pack: the 14 Nov ACT article links the 12 Nov Qld/Vic/SA article and names Bookeasy"], "reason": "one incident, several jurisdictions."},
    {"id": "CORR-11", "record": "RS-079 (candidate C2-016)", "field": "start_time_utc, duration",
     "previous_value": "'week of 16 Nov 2026'", "corrected_value": "start 2026-11-19T09:11:00Z (8:11pm AEDT), duration 4 minutes",
     "evidence": ["ABC article read this session: 'between 8:11 and 8:15pm on November 19'"], "reason": "date resolved from the article."},
    {"id": "CORR-12", "record": "RS-063 (candidate C2-U01)", "field": "evidence",
     "previous_value": "one row (64196b70)", "corrected_value": "adds 312f3026-9742-407a-8a4b-43e91a5a97fb (ABC 2026-09-22T18:48:33Z, SUPPRESS generic_news) and 575358f7-332c-4ddc-baf9-a9d3ce79076b (Google News copy, SUPPRESS)",
     "evidence": ["review pack"], "reason": "the 22 Sep article makes the data type and consequence (replace passports/licences) explicit."},
    # supplementary corrections discovered while applying the above (not in the review's list of 12; applied the same way)
    {"id": "SUPP-01", "record": "RS-029", "field": "first_public_report_time",
     "previous_value": None, "corrected_value": "2026-11-03T15:06:00Z (earliest TJR row, iTnews c75e3f2c-96ec-4520-af9a-b9fc32d96d3b; not necessarily the first public report)",
     "evidence": ["c75e3f2c-96ec-4520-af9a-b9fc32d96d3b (iTnews, pub 2026-11-03T15:06:00Z, col 2026-11-04T19:00:14Z)", "ffa0c323-3563-46bc-9eef-e4075ff654b9 (ABC, pub 2026-11-03T21:46:03Z, col 22:52:55Z)"],
     "reason": "v1 left the first report undated ('not located'), which excluded the record from period assignment; the review pack notes the earliest TJR rows. Police were alerted 30 Oct per the review pack."},
    {"id": "SUPP-02", "record": "RS-080 (candidate M-04)", "field": "event date",
     "previous_value": "~4 Sep 2026 (TJR published_at 2026-09-04T07:00:00Z, a date-only placeholder)", "corrected_value": "Saturday 2026-09-05, late afternoon AEST (about 07:00Z)",
     "evidence": ["Nine article read this session: 'services dropped out on late Saturday afternoon'; News24 dated 5 Sep 2026; Endeavour Energy Facebook post 'Saturday 5pm' (search excerpt)"],
     "reason": "the placeholder time precedes the event it reports; Nine's page metadata says published 2026-09-04T07:18Z but the body describes Saturday, so the exact first-report time is unresolved."},
]
CORRECTIONS[-2]["previous_value_note"] = "v1: first_public_report_time.value null, source 'first public report not located'"


# ---- evidence helpers -------------------------------------------------------------------------------------------------------------------
def ev(eid, src, pub, col, disp, headline, basis="tjr_row", note=None):
    ref = eid if str(eid).startswith("session-") else None  # not a TJR row: a page read (or search excerpt) in the preparing session
    d = {"event_id": None if ref else eid, "source_name": src, "published_at": pub, "collected_at": col, "disposition": disp, "headline": headline, "basis": basis}
    if ref:
        d["ref"] = ref
    if note:
        d["note"] = note
    return d


def cand_ev(cand, drop=(), note_by_id=None):
    out = []
    for e in cand["evidence"]:
        if e["event_id"] in drop:
            continue
        out.append(ev(e["event_id"], e["source_name"], e["published_at"], e["collected_at"], e["disposition"], e["headline"],
                      note=(note_by_id or {}).get(e["event_id"])))
    return out


def owner(basis, instruction, review_ref=None):
    d = {"decided_by": "owner", "decided_on": APPLIED_ON, "basis": basis, "instruction": instruction}
    if review_ref:
        d["review_pack_ref"] = review_ref
    return d


ACCEPT = ("review default accepted (owner: 'everything else from the review's default decisions stands')", "Section 1 list A / decisions block PROMOTE")
FIRST_REPORT_NOTE = "earliest TJR-collected report (published_at, post-repair); an earlier public report may exist"


def rec(rid, cid, title, status, cat, rationale, sector, first_pub, decision, evidence, *, sectors=None, start=None, end=None, level="high", level_reason="",
        sources=None, verification="tjr_rows_only", uncertain=None, discovered="tjr_events_only", dup=None, nm_type=None, extra=None, confidence=None,
        first_pub_source=FIRST_REPORT_NOTE, start_conf="low"):
    r = {
        "id": rid, "candidate_id": cid, "title": title, "set_membership": "v3_new", "record_kind": "incident", "status": status,
        "intelligence_category": cat, "category_rationale": rationale, "primary_sector": sector, "sectors": sectors or [sector],
        "start_time_utc": {"value": start, "source": "" if start is None else "see evidence", "confidence": start_conf},
        "first_public_report_time": {"value": first_pub, "source": first_pub_source},
        "end_time_utc": {"value": end, "source": ""},
        "australian_materiality": {"level": level, "reason": level_reason},
        "sources": sources or [], "verification_status": verification, "uncertain_facts": uncertain or [], "discovered_via": discovered,
        "duplicate_of": dup, "non_material_type": nm_type, "correlation_traps": [], "reviewed_by_human": True,
        "is_negative_example": status in ("confirmed_non_material", "stale_or_resurfaced", "unrelated_incident", "duplicate_report"),
        "scoring_excluded": status == "unresolved_insufficiently_verified", "decision": decision, "evidence": evidence,
    }
    if confidence:
        r["review_confidence"] = confidence
    if extra:
        r.update(extra)
    return r


def new_records(cands: dict) -> list[dict]:
    C = cands
    A_DEC = lambda ref: owner(ACCEPT[0], "owner accepted the review defaults (list A)", ref)
    out = []

    # --- list A: accepted ------------------------------------------------------------------------------------------------------------------
    out.append(rec("RS-054", "C2-001", "Hackers leak Court Services Victoria hearing data (28,600 lines of Magistrates'/Children's Court WebEx records incl. family-violence order parties) to a dark-web forum (posted July; ABC 6 Aug 2026)",
                   "confirmed_material", MOD, "Confirmed leak of sensitive court records: a data-breach incident.", "government", "2026-08-06T19:10:35Z", A_DEC("C2-001"),
                   cand_ev(C["C2-001"], drop=("1a0f85b0-f294-42b1-8ae3-ce84873c4354",)) + [
                       ev("b19f2ee5-3ff3-432c-85bf-c0e8d5b75e5d", "ABC News", "2026-08-06T19:10:35Z", "2026-08-06T20:00:25Z", "SUPPRESS", "Court Services Victoria; 28,600 lines; family-violence order and children's court party names; online hearings in regional courts (reviewer's read of the ABC article)", "review_pack_web_read")],
                   sectors=["government", "justice"], confidence="medium-high", level_reason="Victorian state courts; online hearings in 10 regional courts named (review pack).",
                   uncertain=["Posting date 'July' only; exact leak date not established.", "Article body read by the reviewer (review pack), not re-read this session."],
                   extra={"coverage_limits": []}))
    out.append(rec("RS-055", "C2-003", "ASD HIGH alert: active exploitation of the N-able N-central remote monitoring platform within Australia (19 Aug 2026)",
                   "confirmed_material", MEW, "National-authority alert of active exploitation: a warning (advisory), not a service disruption.", "cyber_security", "2026-08-19T04:44:29Z", A_DEC("C2-003"),
                   cand_ev(C["C2-003"], note_by_id={"57d5bb9c-e4b9-46cc-b0ce-de8d58191ff9": "page-item re-collection of the same alert on 8 Oct (same published time); not independent"}),
                   confidence="medium-high", level_reason="ASD states exploitation inside Australia.", uncertain=["CVE ids appear only in the TJR summary, not verified."]))
    out.append(rec("RS-056", "C2-004", "ASD HIGH alert: active exploitation of JetBrains TeamCity On-Premise within Australia (24 Aug 2026)",
                   "confirmed_material", MEW, "National-authority alert of active exploitation: a warning (advisory).", "cyber_security", "2026-08-24T06:03:59Z", A_DEC("C2-004"),
                   cand_ev(C["C2-004"], note_by_id={"607afd1e-0e06-4128-ab0f-77276087bb98": "page-item row with a corrupted URL and an HTML-anchor title (collector artefact); reached a brief on 7 Oct re-collection"}),
                   confidence="medium", level_reason="ASD states exploitation inside Australia.", uncertain=["Vendor named only in the TJR summary; the alert body was not read."]))
    out.append(rec("RS-057", "C2-005", "ASD CRITICAL alert: Adobe Commerce / Magento Open Source stores under active attack in Australia (9 Sep 2026)",
                   "confirmed_material", MEW, "National-authority CRITICAL alert plus specialist press that Australian stores are under attack: a warning (advisory).", "retail_cyber", "2026-09-09T02:58:57Z", A_DEC("C2-005"),
                   cand_ev(C["C2-005"], note_by_id={"35663948-3234-49be-9892-abdc2a0347f2": "ACSC page-item row; TJR only collected it on 14 Oct (the genuine first collection is f65829a0 on 9 Sep)"}) + [
                       ev("75db3b48-ef4a-4bf0-952c-769ef07dafde", "CISA Known Exploited Vulnerabilities", "2026-09-08T00:00:00Z", "2026-09-08T20:00:23Z", "REFERENCE",
                          "CVE-2026-75650: Adobe Commerce and Magento (KEV entry)", note="related signal only: published_at is a date-only placeholder and the CVE's relation to the ASD alert is not verified; not counted as detection")],
                   confidence="high", level_reason="ASD + iTnews state Australian stores attacked.", uncertain=["Number of stores affected not stated."]))
    out.append(rec("RS-058", "C2-009", "Napoleon Perdis data breach: names, DOB, emails, phones, addresses and purchase histories of 340,000 clients (17 Oct 2026)",
                   "confirmed_material", MOD, "Named company, stated scale, national broadcaster: a data-breach incident.", "retail_cyber", "2026-10-17T05:59:12Z", A_DEC("C2-009"),
                   cand_ev(C["C2-009"]), confidence="medium-high", level_reason="Australian brand; ABC states 340,000 clients.", uncertain=["Scale is the ABC's figure; the company statement was not read."]))
    out.append(rec("RS-059", "C2-010", "Critical PHP flaw ('PHP2shell'): ASD critical alert; ABC reports GovCMS, Moodle and VentraIP among platforms affected, expected spike in Australian breaches (21-22 Oct 2026)",
                   "confirmed_material", MEW, "ASD critical alert about a widely used web platform with expected Australian breaches: a warning (advisory), no confirmed compromise.", "cyber_security", "2026-10-21T03:01:26Z", A_DEC("C2-010"),
                   [ev("32572cfb-28e7-46b7-87ac-1b5f73597e13", "ACSC Alerts & Advisories", "2026-10-21T03:01:26Z", "2026-10-21T19:00:06Z", "WATCH", "Critical vulnerabilities in PHP", note="primary ASD alert; summary: security release for two critical PHP vulnerabilities set for disclosure 22 Oct 2026"),
                    ev("a6a5935d-3e8c-487e-abe5-1999aec59f6d", "ABC News", "2026-10-21T15:58:02Z", "2026-10-21T16:05:48Z", "WATCH", "Australia's cybersecurity site among those hit by 'critical' software flaw"),
                    ev("de43fcb5-745a-4a45-abd4-803df4d132b9", "ABC News", "2026-10-22T00:48:22Z", "2026-10-22T01:56:42Z", "WATCH", "Australians facing spike in data breaches after 'critical' flaw uncovered"),
                    ev("a0e63dcd-f2c0-4cc4-b634-bb506377a0f4", "ABC News", None, None, None, "Hacking attempts surge (22 Oct)", note="id and headline from the review pack; published/collected times not re-read")],
                   sectors=["cyber_security", "government", "education", "hosting"], confidence="medium", level_reason="ASD critical alert; named Australian platforms.",
                   uncertain=["Body text says VentraIP restricted file uploads (precaution) while the ABC description says sites were 'forced offline'; AWS saw exploitation attempts from 17 Oct (review pack)."]))
    out.append(rec("RS-060", "C2-011", "ABC wipes staff devices after a 'sophisticated cyber attack' (22-23 Oct 2026)",
                   "confirmed_material", MOD, "Named organisation took a destructive response (device wipe) after an attack: an incident.", "media_cyber", "2026-10-23T01:41:30Z", A_DEC("C2-011"),
                   cand_ev(C["C2-011"], note_by_id={"b28ee180-bb1e-4805-bd31-a2ea7fc5adb8": "Google News copy: published_at is a date-only placeholder; TJR collected it 13 days later (2026-11-04)"}),
                   confidence="medium", level_reason="National broadcaster; device wipe is a destructive response.", first_pub_source="ABC 4a151322 (CORR-09); the Google News copy time is a placeholder",
                   uncertain=["Number of devices not stated; ABC reporting about itself (self-reported)."]))
    q4_c2013 = {"rule": "Q4 automatic inclusion: >=20,000 premises, or 24 h with a critical service affected",
                "threshold_applied": ">=20,000 premises", "premises_stated": "more than 58,000 homes (ABC headline, row 637b353c); thousands still out the next day (row e9733e96)",
                "qualifiers_evidenced": [], "qualifiers_not_evidenced": ["emergency-service disruption", "critical-infrastructure failure", "failure of redundancy or backup", "regional isolation", "cross-sector or cascading", "vulnerable populations", "regulatory implications"],
                "result": "material: automatic inclusion by premises threshold; distributor not named in the headline"}
    out.append(rec("RS-061", "C2-013", "Storms leave more than 58,000 Queensland homes without power (Logan, Scenic Rim, Moreton Bay, Gympie); thousands still out next day (11-12 Nov 2026)",
                   "confirmed_material", MOD, "Large-scale distribution outage: an operational disruption.", "energy", "2026-11-11T06:41:00Z", owner("owner Q4: re-assessed against the new threshold/qualifier rule", "Q4: adopt 20,000 premises or 24 h with a critical service as AUTOMATIC INCLUSION; re-assess C2-013", "C2-013 (rule-dependent)"),
                   cand_ev(C["C2-013"]), confidence="medium", level_reason="Australian grid customers.", extra={"q4_assessment": q4_c2013},
                   uncertain=["Distributor (Energex/Ergon) not named in the headline; restoration time not read."]))
    out.append(rec("RS-062", "C2-014", "VCAA website hacked during VCE exam period; hacker claims to have sold VCE exam papers to hundreds of students (11 Nov 2026)",
                   "confirmed_material", MOD, "Government website compromise with claimed exam-integrity impact: an incident.", "education_cyber", "2026-11-11T09:15:15Z", A_DEC("C2-014"),
                   cand_ev(C["C2-014"]), sectors=["education_cyber", "government"], confidence="medium", level_reason="Victorian curriculum authority; Year 12 exams.",
                   uncertain=["Exam-integrity impact is claimed by the hacker, not confirmed by VCAA (it is 'investigating')."]))
    out.append(rec("RS-063", "C2-U01", "Quest Apartment Hotels customer data breach (19 Aug 2026); 22 Sep ABC: customers told to replace passports and driver's licences",
                   "confirmed_material", MOD, "Customer data breach with a stated customer consequence: an incident.", "hospitality_cyber", "2026-08-19T02:08:09Z", A_DEC("C2-U01 (promoted from unresolved)"),
                   cand_ev(C["C2-U01"]) + [
                       ev("312f3026-9742-407a-8a4b-43e91a5a97fb", "ABC News", "2026-09-22T18:48:33Z", "2026-09-22T19:42:37Z", "SUPPRESS", "(ABC 22 Sep: 'security breach in August ... replace passports and driver's licences')", note="suppression reason generic_news; headline from the review pack"),
                       ev("575358f7-332c-4ddc-baf9-a9d3ce79076b", "Google News", "2026-09-22T18:48:33Z", None, "SUPPRESS", "Google News copy of 312f3026", note="times per review pack")],
                   confidence="medium-high", level_reason="Australian hotel chain.", uncertain=["Scale not stated."]))
    out.append(rec("RS-064", "M-01", "Tungatinah Power Station (Hydro Tasmania, Central Highlands) gutted by fire; supplies about 5% of Tasmania's energy; fire accidental per authorities (2-9 Sep 2026)",
                   "confirmed_material", MOD, "Physical loss of a named generation asset: an operational disruption.", "energy", "2026-09-02T20:22:23Z", A_DEC("M-01 (new)"),
                   [ev("b37c0ae3-0fac-4c6f-8f95-cef83825f38f", "ABC News", "2026-09-02T20:22:23Z", "2026-09-02T20:30:41Z", "REFERENCE", "Fire breaks out at major Tasmanian power station", note="reached a brief"),
                    ev("859441e4-42ae-4de7-a5be-94f3ce7b8ab2", "ABC News", "2026-09-03T19:19:21Z", "2026-09-03T20:00:54Z", "REFERENCE", "Not yet safe to access Hydro Tasmania power station destroyed by fire", note="summary: supplies 5% of the state's energy (ABC figure)"),
                    ev("d49de54e-1b0f-4d8a-b574-ccdf593ff9b4", "ABC News", "2026-09-09T23:51:08Z", "2026-09-10T01:16:25Z", "REFERENCE", "Authorities determine Tasmanian power station fire was accidental")],
                   confidence="medium-high", level_reason="Tasmanian grid, named asset; national broadcaster only.", uncertain=["5% figure is the ABC's; no Hydro Tasmania/AEMO statement in TJR; supply impact not confirmed."]))
    out.append(rec("RS-065", "M-02", "RMS Cloud (accommodation software) breach: bookings of BIG4, Reflections, G'day Parks, Summerstar, McMillans of Metung and other holiday parks exposed; scam emails to guests; card data not exposed (27-28 Oct 2026)",
                   "confirmed_material", MOD, "Third-party platform breach with named Australian operators and active scam follow-on: an incident.", "hospitality_saas_cyber", "2026-10-27T05:24:30Z", A_DEC("M-02 (new)"),
                   [ev("b6bc6af9-445f-4fbb-9d65-c747b774866f", "ABC News", "2026-10-27T05:24:30Z", "2026-10-27T06:26:49Z", "WATCH", "Scammers target major holiday parks across Australia in cybersecurity breach", "review_pack_web_read", "vendor RMS Cloud; >6,000 properties globally per article; guest scale not stated"),
                    ev("b07257e5-f0e6-47bb-867b-ff41d7e51845", "ABC News", "2026-10-28T19:21:44Z", "2026-10-28T19:59:42Z", "BRIEF", "'Convincing' scam email used real booking number, check-in dates", note="URL slug: tas-federal-group-hotels-caught-up-in-rms-booking-data-breach")],
                   confidence="medium", level_reason="Multiple named Australian operators; Tasmanian Federal Group hotels also affected (28 Oct).", uncertain=["Number of affected guests not stated; one source family (ABC)."]))
    out.append(rec("RS-066", "M-03", "Bookeasy booking platform breach: Qld, Vic and SA national-park booking systems hacked (11 Nov), ACT system disabled and about 6,000 customers alerted (13-14 Nov); new campsite bookings suspended",
                   "confirmed_material", MOD, "Platform breach with services suspended across four jurisdictions: an incident.", "government", "2026-11-11T23:54:20Z", A_DEC("M-03 (new)"),
                   [ev("10718b2f-f898-4c35-b982-2d4525bc06e1", "ABC News", "2026-11-11T23:54:20Z", "2026-11-12T01:00:46Z", "WATCH", "Personal data stolen after National Parks booking service hacked in three states", "review_pack_web_read", "Bookeasy; Qld DETSI, Parks Victoria, SA NPWS; new bookings suspended"),
                    ev("29b4a708-2ba6-4ea9-8f0f-b83a8c3a370e", "ABC News", "2026-11-14T04:17:12Z", "2026-11-14T04:18:56Z", "WATCH", "Campground booking portal disabled while data breach investigated", note="candidate C2-015 (ACT portal, about 6,000 customers); same incident")],
                   sectors=["government", "saas"], confidence="medium-high", level_reason="Four Australian state/territory park agencies.", uncertain=["Scale not stated beyond 'about 6,000' ACT customers; the review reads Bookeasy as the platform (review pack)."]))

    # --- list B: rejected / duplicates / holds ---------------------------------------------------------------------------------------------
    B_DEC = lambda ref: owner("review default accepted (list B)", "owner accepted the review defaults (list B)", ref)
    out.append(rec("RS-067", "C2-008", "UK air traffic control failure; Australians sleep at Heathrow (8-9 Sep 2026)", "confirmed_non_material", NONMAT,
                   "Foreign event; traveller inconvenience only; no Australian network disruption evidenced.", "transport", "2026-09-08T23:52:20Z", B_DEC("C2-008"),
                   cand_ev(C["C2-008"]), nm_type="foreign_event_low_au_materiality", level="low", level_reason="Traveller inconvenience only (review pack)."))
    out.append(rec("RS-068", "C2-U02", "Google Cloud Status: Multiple Products, timeouts/service errors (20 Aug 2026)", "confirmed_non_material", NONMAT,
                   "Generic status-feed item with no Australian region or customer evidenced.", "cloud", "2026-08-20T16:44:37Z", B_DEC("C2-U02"), cand_ev(C["C2-U02"]),
                   nm_type="status_page_noise", level="low", level_reason="No Australian region in the item."))
    out.append(rec("RS-069", "C2-U05", "Attackers use SQL-injection emails to root Cisco email gateways (iTnews, 16 Sep 2026)", "confirmed_non_material", NONMAT,
                   "No Australian victim or advisory in the item.", "cyber_security", "2026-09-16T10:34:00Z", B_DEC("C2-U05"), cand_ev(C["C2-U05"]),
                   nm_type="foreign_event_low_au_materiality", level="low", level_reason="No Australian victim or advisory evidenced."))
    out.append(rec("RS-070", "C2-U08", "Railway (app hoster) attackers ran up US$740,000 on stolen AI keys (iTnews, 10 Nov 2026)", "confirmed_non_material", NONMAT,
                   "Financial loss at a foreign vendor; no Australian customer or authority named.", "cloud_cyber", "2026-11-10T17:31:00Z", B_DEC("C2-U08"), cand_ev(C["C2-U08"]),
                   nm_type="foreign_event_low_au_materiality", level="low", level_reason="No Australian exposure evidenced."))
    out.append(rec("RS-071", "C2-015", "ACT national-park campground booking portal disabled after data breach; about 6,000 customers alerted (14 Nov 2026)", "duplicate_report", NONMAT,
                   "Same incident as RS-066 (Bookeasy); clustered under the parent, never scored.", "government", "2026-11-14T04:17:12Z", B_DEC("C2-015 / CORR-10"), cand_ev(C["C2-015"]),
                   dup="RS-066", nm_type="same_event_other_jurisdiction", level="none", level_reason="Counted under RS-066."))
    out.append(rec("RS-072", "C2-U06", "Stake (Australian investing app) data breach (Daily Mail via Google News, 25 Sep 2026)", "unresolved_insufficiently_verified", UNRES,
                   "Single aggregator copy, scale unknown; not scored either way.", "financial_services_cyber", "2026-09-25T07:09:49Z", B_DEC("C2-U06 (hold)"), cand_ev(C["C2-U06"]),
                   level="med", level_reason="High if true.", confidence="low",
                   uncertain=["A second source (ABC/iTnews/AFR or company notice) giving scale would resolve it."]))
    out.append(rec("RS-073", "C2-U07", "Data breach at an Adelaide private hospital (ABC, 8 Oct 2026; hospital named only in the URL slug)", "unresolved_insufficiently_verified", UNRES,
                   "Hospital named only in a URL slug; scale not stated; not scored either way.", "healthcare_cyber", "2026-10-08T05:01:42Z", B_DEC("C2-U07 (hold)"), cand_ev(C["C2-U07"]),
                   level="med", level_reason="High if scaled.", confidence="low-medium",
                   uncertain=["Article stating a large number of patients or clinical-system disruption would resolve it."]))
    out.append(rec("RS-074", "C2-U09", "Cyberattack via Optimizely Web exposes banking, media and insurance websites to malware (Beinsure via Google News, 16 Nov 2026)", "unresolved_insufficiently_verified", UNRES,
                   "Aggregator only; no Australian site named; original publisher unverified; not scored.", "cyber_security", "2026-11-16T08:00:00Z", B_DEC("C2-U09 (hold)"), cand_ev(C["C2-U09"]),
                   level="low", level_reason="Unknown: no Australian site named.", confidence="low",
                   first_pub_source="Google News date-only placeholder (08:00:00Z); real first report time unknown",
                   uncertain=["An original report naming Australian banks/insurers would resolve it."]))
    return out


def owner_amended_records(cands: dict) -> list[dict]:
    C = cands
    out = []
    # --- Q7: Sydney Airport, one parent anchored on 8 Aug, cause disputed -----------------------------------------------------------------
    e_ = {e["event_id"][:8]: e for e in cand_ev(C["C2-002"])}
    sa_ev = list(e_.values())
    out.append(rec("RS-075", "C2-002", "Sydney Airport: one parent incident anchored on 8 Aug 2026 (dozens of flights delayed), with dated developments (9 Aug tarmac near-miss; 26 Aug regulator investigating six incidents)",
                   "confirmed_material", MOD, "Delays on 150+ flights and a tarmac near-miss at the country's busiest airport, with a regulator investigation: an operational disruption.", "transport", "2026-08-08T03:48:52Z",
                   owner("owner Q7", "Q7: ONE parent incident anchored on 8 Aug with distinct dated lifecycle developments; do not merge unrelated disruptions; do NOT state the disputed cause as established; store competing cause claims with sources; mark cause 'disputed'", "C2-002"),
                   sa_ev, sectors=["transport", "aviation"], start="2026-08-08T00:00:00Z", start_conf="low", level_reason="Sydney Airport; Qantas/Virgin flights; regulator action.",
                   confidence="medium (parent anchored per owner)", discovered="tjr_events_only",
                   sources=["https://www.theguardian.com/australia-news/2026/aug/08/sydney-airport-delays-affecting-qantas-virgin-flights",
                            "https://www.abc.net.au/news/2026-08-09/sydney-airport-near-miss-jetstar-qatar-airlines/107014048",
                            "https://www.theguardian.com/australia-news/2026/aug/13/whats-behind-sydney-airports-heavy-delays-and-near-miss-incident"],
                   uncertain=["The 26 Aug 'six incidents' claim is supported only by the row's headline: the stored URL is a Guardian live blog about national cabinet/CPI; the article itself was not read.",
                              "Delay scale: Guardian summary says more than 150 flights affected including 95 across the Qantas network (row fad30c0f)."],
                   extra={
                       "cause": {"status": "disputed", "established_cause": None,
                                 "competing_claims": [
                                     {"claim": "Air traffic controller 'rostering issues' behind the 8 Aug disruption", "claimed_by": "Airservices Australia (as reported by the Guardian)", "evidence_event_id": "fad30c0f-cab4-4f61-8eb8-d9e9949bbddb"},
                                     {"claim": "Air traffic controller staff shortages / not enough controllers (safety concerns after the near-miss)", "claimed_by": "Guardian reporting and safety-concern sources (attribution to a named party not read)", "evidence_event_id": "cc32c99d-8511-4ccb-aaa7-44e0fa281d6c"},
                                     {"claim": "Controllers short-staffed and exhausted; recruits face a hard aptitude test and train in Melbourne", "claimed_by": "Guardian explainer (attribution not read)", "evidence_event_id": "6c001814-d56c-41d6-b2a8-7a84222b7abf"}],
                                 "note": "The review pack described the dispute as 'ATC staffing vs equipment'; no TJR row or source read here supports an equipment claim, so none is stored."},
                       "lifecycle": [
                           {"date": "2026-08-08", "kind": "anchor", "development": "Significant delays, dozens of international and domestic routes; more than 150 flights affected incl. 95 Qantas", "evidence": ["fad30c0f-cab4-4f61-8eb8-d9e9949bbddb"]},
                           {"date": "2026-08-09", "kind": "development", "development": "Jetstar A320 and Qatar Airways 777 near-collision on the tarmac about 7am Sunday; a cabin crew member injured (ABC summary)", "evidence": ["762e1557-09e9-4131-9565-73805ab0bca9", "cc32c99d-8511-4ccb-aaa7-44e0fa281d6c"]},
                           {"date": "2026-08-12", "kind": "analysis", "development": "Explainer on the delays and near-miss (Guardian, URL dated 13 Aug)", "evidence": ["6c001814-d56c-41d6-b2a8-7a84222b7abf"]},
                           {"date": "2026-08-26", "kind": "development", "development": "Transport regulator investigating two more incidents, tally of six in a month (title only; article not read)", "evidence": ["e4b5bed4-d8ed-4fd3-b70d-f5e99957455b"]}],
                       "not_merged": "RS-084 (16 Nov weather cancellations) is a different disruption and is recorded separately."}))
    # --- Q6: Coles web outage and Telstra MessageBank: non-material on assessed consequence ------------------------------------------------
    out.append(rec("RS-076", "C2-006", "Coles website and app offline for several hours (Saturday 22 Aug 2026) after a viral discount post triggered mass orders",
                   "confirmed_non_material", NONMAT, "Assessed consequence below the bar on current evidence; basis recorded below, not a blanket exclusion.", "retail", "2026-08-22T05:55:46Z",
                   owner("owner Q6", "Q6: non-material on current evidence with the assessed consequences recorded; no blanket exclusion for non-cyber incidents, retail outages or individual telecom failures; record the basis as the actual operational/customer consequence found", "C2-006"),
                   cand_ev(C["C2-006"]), nm_type="assessed_low_consequence", level="low", level_reason="See non_material_basis.",
                   extra={"non_material_basis": {"consequences_found": ["Online channel (website and app) offline for several hours on a Saturday; came back online (Guardian summary, row 8e68f7f8)", "Cause: viral post exposing ~80% discount on 24-packs of premixed drinks; customers bought cases (title and summary)"],
                                                 "consequences_not_found": ["no data or security impact stated", "no store outage stated", "no safety or emergency-service effect", "no regulatory implication stated", "customer/order counts not stated"],
                                                 "single_source": True, "would_change_if": "a second source or Coles statement quantifies lost orders or shows a wider multi-hour loss of trading"}}))
    out.append(rec("RS-078", "C2-012", "Telstra MessageBank fault floods customers with missed-call notifications; Telstra admits a glitch (4-5 Nov 2026)",
                   "confirmed_non_material", NONMAT, "Assessed consequence below the bar on current evidence; basis recorded below, not a blanket exclusion.", "telecommunications", "2026-11-04T09:51:00Z",
                   owner("owner Q6", "Q6: non-material on current evidence with the assessed consequences recorded; no blanket exclusion for individual telecom service failures", "C2-012"),
                   cand_ev(C["C2-012"]), nm_type="assessed_low_consequence", level="low", level_reason="See non_material_basis.",
                   extra={"non_material_basis": {"consequences_found": ["Customers received floods of missed-call notifications / mystery calls after a MessageBank fault (headlines of rows 83c30141, 09ac7ab3)"],
                                                 "consequences_not_found": ["no loss of calling or voicemail evidenced in TJR rows", "affected customer count not stated", "no emergency-call effect stated"],
                                                 "single_source_family": "all TJR copies are Google News items (West Australian, Tech Business News)",
                                                 "would_change_if": "Telstra quantifies customers (e.g. >100k) or states calls/voicemail were lost"}}))
    # --- Q9: Fiji fuel contamination, resolved on evidence read now -----------------------------------------------------------------------
    out.append(rec("RS-077", "C2-007", "Fiji (Nadi) jet fuel contamination disrupts Virgin Australia, Qantas and other carriers: Virgin cancelled two services and added refuel stops; reserve fuel released by Fiji (Aug 2026)",
                   "confirmed_material", MOD, "Supply failure at an international airport forcing cancellations and re-routing for two Australian carriers: an operational disruption (third-party/critical-infrastructure dependency).", "transport", "2026-08-21T00:58:00Z",
                   owner("owner Q9", "Q9: read the ABC article and available authoritative supporting evidence now; resolve the classification if the evidence allows", "C2-007"),
                   cand_ev(C["C2-007"]) + [
                       ev("session-read:abc-107061960", "ABC News (article read)", "2026-08-21T00:58:00Z", None, None, "Fiji fuel contamination issue hits Virgin, Qantas, Fiji Airlines services", "session_web_read",
                          "Virgin cancelled two flights (a Brisbane-Fiji return) of about six daily; stops at New Caledonia and Vanuatu; Qantas swapped a 737 for an A330 on Sydney-Nadi; pilots told 'major contamination', supply cannot be guaranteed, may last until end of month; Fiji Airports: Nadi open and operational"),
                       ev("session-read:aerosouthpacific-nadi", "Aero South Pacific (specialist trade site, article read)", None, None, None, "Contaminated fuel worsens Nadi Airport supply shortage", "session_web_read",
                          "says at least four airlines affected (Fiji Airways, Air New Zealand, Qantas, Virgin Australia); Fiji Government released 1.3 million litres of reserve fuel; quotes a 19 Aug NOTAM 'Jet A-1 fuel at critical level, all operators except Fiji Airways and Petro Oceania contracted customers must tanker fuel in' and an 21 Aug Fiji Government statement ('no airport infrastructure, operational or aviation safety issues ... fuel availability remains restricted'); Air NZ cancelled at least one flight; Qantas used an A330 for three days; Jetstar rerouted some flights via Auckland; Nadi had issued fuel-shortage NOTAMs since July")],
                   sectors=["transport", "aviation", "fuel_supply"], start="2026-08-19T00:00:00Z", start_conf="low", level="med",
                   level_reason="Two Australian carriers; limited quantified customer impact (two Virgin cancellations reported).", confidence="medium",
                   sources=["https://www.abc.net.au/news/2026-08-21/fiji-fuel-contamination-impacts-qantas-virgin-flights/107061960", "https://aerosouthpacific.com/blogs/news/contaminated-fuel-worsens-nadi-supply-shortage"],
                   verification="verified_by_two_sources_read_this_session",
                   uncertain=["Cause: 'excessive electrical charge in a batch of fuel' per ABC sources; Fiji Airports did not confirm the cause.",
                              "The 'at least four airlines', 1.3 million litre release, NOTAM and 21 Aug government statement come from one specialist site quoting them; the NOTAM and statement texts themselves were not read.",
                              "Total cancellations across carriers and the resolution date were not found; Nadi had fuel-shortage NOTAMs since July (a wider supply problem).",
                              "No Virgin Australia, CASA or ATSB primary statement was read (the ABC quotes a Virgin spokesman: 'temporary fuel issue')."],
                   extra={"q4_assessment": {"rule": "Q4 qualifiers (smaller disruptions can still be material)", "threshold_applied": "none of the numeric thresholds applies (no premises)",
                                            "qualifiers_evidenced": ["critical-infrastructure failure: airport fuel supply at 'critical level' (NOTAM as quoted by a specialist site), fuel contaminated", "failure of redundancy or backup: government reserve stock released; operators told to tanker fuel in", "cross-sector/multi-party: at least four carriers (single specialist source)"],
                                            "qualifiers_not_evidenced": ["emergency-service disruption", "regional isolation", "vulnerable populations"],
                                            "result": "material on the critical-infrastructure and redundancy qualifiers; quantified Australian customer impact is small, so confidence is medium",
                                            "previous_lean": "unresolved/hold (review default); changed because the article read and a second source give scale, duration and multi-carrier impact"}}))
    # --- Q5: Canberra Triple Zero call centre ---------------------------------------------------------------------------------------------
    out.append(rec("RS-079", "C2-016", "ACT Triple Zero call centre (ESA headquarters, Fairbairn) loses power for four minutes (8:11-8:15pm AEDT, 19 Nov 2026); first backup battery pack failed, second took four minutes",
                   "confirmed_material", MOD, "Emergency-service call-taking continuity lost with a failed first backup: an operational disruption regardless of duration (owner Q5).", "emergency_services", "2026-11-21T03:39:43Z",
                   owner("owner Q5", "Q5: MATERIAL regardless of duration (emergency-service continuity and backup failure are independently significant); preserve the two separately sourced attributes", "C2-016"),
                   cand_ev(C["C2-016"]) + [ev("session-read:abc-107412506", "ABC News (article read)", "2026-11-21T03:39:43Z", None, None, "Investigation underway into power outage at ACT Triple Zero call centre", "session_web_read",
                                              "ESA HQ outage 8:11-8:15pm 19 Nov; first battery pack failed, second took four minutes; staff relocated to the backup centre at Hume; cause unclear (lightning or power surge speculated)")],
                   sectors=["emergency_services", "telecommunications"], start="2026-11-19T09:11:00Z", start_conf="medium", end="2026-11-19T09:15:00Z",
                   sources=["https://www.abc.net.au/news/2026-11-21/investigations-call-centre-outage-act-emergency-services/107412506"], verification="verified_by_article_read_this_session",
                   level_reason="ACT emergency-service continuity; failed backup.", confidence="medium",
                   uncertain=["Cause not established (speculation: lightning or power surge).", "Earlier reports than the 21 Nov ABC row may exist (42.5 h after the event)."],
                   extra={"duration_minutes": 4,
                          "separately_sourced_attributes": {
                              "four_in_progress_ambulance_calls_cut_out": {"statement": "In that time, four in-progress ambulance calls cut out; the ESA said there were no incoming calls to ambulance or fire and rescue", "source": "ABC article (narrative, with the ESA statement on incoming calls)", "evidence_event_id": "ef242803-9993-41c8-91f9-7b67449471f8"},
                              "authorities_state_no_triple_zero_calls_lost": {"statement": "'no Triple Zero calls were lost'; 'We lost a couple at the time but we were able to retrieve them'; attempted calls would have been diverted to ACT Policing, which was not affected", "source": "ACT ESA Commissioner Wayne Phillips (quoted by ABC)", "evidence_event_id": "ef242803-9993-41c8-91f9-7b67449471f8"},
                              "union_view": {"statement": "'to lose a call ... four minutes is life and death'", "source": "Transport Workers' Union (Damian Pollard), quoted by ABC"},
                              "note": "Both attributes are stored; neither is resolved into the other."}}))
    # --- Q4: M-04 Sydney/NSW storm, M-05 Mildura, flights --------------------------------------------------------------------------------
    out.append(rec("RS-080", "M-04", "Sydney/NSW wind storm: more than 46,000 homes without power (Endeavour Energy network; Ausgrid also reporting outages), Saturday 5 Sep 2026",
                   "confirmed_material", MOD, "Large-scale distribution outage with 250+ fault sites: an operational disruption.", "energy", "2026-09-05T07:00:00Z",
                   owner("owner Q4", "Q4: confirm M-04 (Sydney 46k) with an authoritative source via at most 4 Firecrawl calls; keep unresolved only if still one aggregator row", "M-04"),
                   [ev("780c4c4e-ba23-41e4-9b2f-ec6813b455e3", "Google News - Telstra", "2026-09-04T07:00:00Z", "2026-09-16T07:16:46Z", "REFERENCE", "Sydney weather: More than 46,000 homes without power as destructive winds lash NSW - Nine.com.au", note="published_at is a date-only placeholder that precedes the event; TJR collected the aggregator copy 12 days later"),
                    ev("session-read:nine-p60uky", "Nine.com.au (article read)", None, None, None, "More than 46,000 homes without power as destructive winds lash NSW", "session_web_read",
                       "Endeavour Energy crews fixing more than 250 fault sites before restoring power to 46,000 homes after services dropped out late Saturday afternoon; Ausgrid reported more than 23,000 outages; the outage also affecting some 5G services including on Telstra; fallen trees damaged homes; total fire ban in Greater Sydney"),
                    ev("session-search:endeavour-energy-facebook", "Endeavour Energy (official Facebook post, search excerpt only)", None, None, None, "Widespread power outages in Greater Western Sydney and Blue Mountains", "session_web_read",
                       "excerpt: 'Strong winds are causing widespread power outages across the Endeavour Energy network, with around 50,000 customers currently without power' (Saturday 5pm); the page itself was not opened"),
                    ev("session-search:news24-7news", "News24 (5 Sep 2026), 7News (search excerpts)", None, None, None, "More than 46,000 NSW properties affected as damaging winds bring power outages", "session_web_read", "7News excerpt: 43 outages, nearly 40,000 customers; Ausgrid excerpt: 37,713 customers at one point")],
                   start="2026-09-05T07:00:00Z", start_conf="low", level_reason="NSW distribution networks.", confidence="medium-high",
                   sources=["https://www.nine.com.au/australia-news/nsw/total-fire-ban-declared-greater-sydney-saturday-20260904-p60uky.html"], verification="verified_by_distributor_excerpt_and_mainstream_media",
                   uncertain=["Duration not confirmed; the excerpts suggest restoration targeted 'by the end of' the following day (not read).", "Exact first-report time unresolved (SUPP-02); the Endeavour page was seen as a search excerpt only.", "Nine's page metadata (published 4 Sep) conflicts with its body text ('late Saturday afternoon')."],
                   extra={"q4_assessment": {"rule": "Q4 automatic inclusion: >=20,000 premises, or 24 h with a critical service affected", "threshold_applied": ">=20,000 premises",
                                            "premises_stated": "46,000 homes (Nine, News24); about 50,000 customers (Endeavour Energy post excerpt); Ausgrid 23,000+ outages separately",
                                            "qualifiers_evidenced": ["cross-sector or cascading consequences: some 5G services including Telstra affected (Nine)"], "qualifiers_not_evidenced": ["emergency-service disruption", "vulnerable populations", "regional isolation"],
                                            "result": "material: automatic inclusion by premises threshold, confirmed by a distributor excerpt and three mainstream outlets (was one aggregator row)",
                                            "previous_lean": "hold/unresolved (one aggregator row)"}}))
    out.append(rec("RS-081", "M-05", "Mildura (Vic) power outage: about 2,700-3,360 homes and businesses out from Monday 21 Sep after a ute hit a critical pole; restoration for most of the network extended to midday Friday; vulnerable residents affected",
                   "confirmed_material", MOD, "Multi-day outage with vulnerable-population impact and degraded police alarm response: an operational disruption (qualifier-based).", "energy", "2026-09-21T01:23:52Z",
                   owner("owner Q4", "Q4: smaller/shorter disruptions can still be material where evidence shows a qualifier; assess M-05 (Mildura) qualifiers on evidence and record which applied", "M-05"),
                   [ev("1d8d8030-d77b-4917-90ca-27f289c50958", "ABC News", "2026-09-21T01:23:52Z", "2026-09-21T02:38:04Z", "REFERENCE", "Homes without power around Mildura after car hits power pole", note="summary: more than 3,360 homes"),
                    ev("d7c9c6c9-65ef-4a37-824f-8ed26b10dbf0", "ABC News", "2026-09-22T08:57:02Z", "2026-09-22T09:12:38Z", "BRIEF", "Vulnerable residents feeling 'distress' as Mildura power outage drags on"),
                    ev("session-read:abc-107180464", "ABC News (article read)", "2026-09-22T08:57:02Z", None, None, "Vulnerable residents feeling 'distress' as Mildura power outage heads towards third day", "session_web_read",
                       "more than 2,700 homes and businesses, almost 3,000 residents and businesses without power since a ute hit a critical pole at Birdwoodton about 6:30am Monday; Powercor extended 'majority of the network' restoration from Wednesday afternoon to midday Friday; 24 supported accommodation homes (Sunraysia Residential Services) without power; Powercor doing welfare checks on about 130 residents on life support; Victoria Police not responding to alarms until power restored; many shops closed; relief centre and chargers set up")],
                   start="2026-09-21T00:30:00Z", start_conf="medium", end=None, level="med", level_reason="Single regional city, multi-day, vulnerable residents.", confidence="medium-high",
                   sources=["https://www.abc.net.au/news/2026-09-22/residents-mildura-power-outage-distress/107180464"], verification="verified_by_article_read_this_session",
                   uncertain=["Customer count differs: 3,360+ homes (first ABC summary) vs 2,700+ homes and businesses (22 Sep article).", "Actual restoration time not found (forecast midday Friday 25 Sep)."],
                   extra={"q4_assessment": {"rule": "Q4 qualifiers (smaller/shorter disruptions can still be material)", "threshold_applied": "none of the automatic thresholds: about 2,700-3,360 premises (<20,000) and no critical service stated as failed for 24 h",
                                            "qualifiers_evidenced": ["disproportionate impact on vulnerable populations: 24 supported accommodation homes for elderly/disabled residents and about 130 residents on life support needing welfare checks (ABC article)",
                                                                     "emergency-service impact: Victoria Police would not respond to alarms until power was restored (ABC article)"],
                                            "qualifiers_not_evidenced": ["critical-infrastructure failure", "failure of redundancy or backup", "significant regional isolation", "cross-sector or cascading consequences"],
                                            "duration_note": "more than 48 hours by 22 Sep with restoration forecast beyond 4 days",
                                            "result": "material on the vulnerable-population qualifier (supported by the police-alarm effect); not by the automatic thresholds",
                                            "previous_lean": "confirmed_non_material (review default: local outage)"}}))
    out.append(rec("RS-084", "Q4-flights", "Sydney Airport: 104 flights cancelled by weather (cloud and wind; Airservices ground delay program), 16 Nov 2026", "confirmed_non_material", NONMAT,
                   "Weather-driven air-traffic restrictions with re-accommodation; none of the Q4 qualifiers evidenced.", "transport", "2026-11-16T08:58:08Z",
                   owner("owner Q4", "Q4: assess the 104 Sydney flights cancelled by weather (event 67c5c764, 16 Nov) against the qualifiers; record which threshold/qualifier applied or that none was evidenced", "Section 6 (considered, not proposed)"),
                   [ev("67c5c764-3b5f-4fdf-a460-4c60f9e533ff", "ABC News", "2026-11-16T08:58:08Z", "2026-11-16T09:23:25Z", "BRIEF", "104 flights cancelled due to weather conditions at Sydney Airport"),
                    ev("session-read:abc-107392306", "ABC News (article read)", "2026-11-16T08:58:08Z", None, None, "Travellers face delays and cancellations at Sydney Airport due to cloud and wind activity", "session_web_read",
                       "104 cancellations recorded Monday night, mostly domestic; Airservices Australia: cloud and wind affecting air traffic operations; Qantas: ground delay program, 'small number' cancelled overnight, customers re-accommodated within 24 hours; separate Virgin ground-crew industrial action with contingencies")],
                   nm_type="weather_disruption_no_qualifier_evidenced", level="low", level_reason="See q4_assessment.", sources=["https://www.abc.net.au/news/2026-11-16/flight-delays-cancellations-at-sydney-airport/107392306"],
                   verification="verified_by_article_read_this_session", discovered="tjr_events_only",
                   extra={"q4_assessment": {"rule": "Q4 automatic inclusion thresholds and qualifiers", "threshold_applied": "none (no premises; no 24 h critical-service loss)", "qualifiers_evidenced": [],
                                            "qualifiers_not_evidenced": ["emergency-service disruption", "critical-infrastructure failure", "failure of redundancy or backup", "significant regional isolation", "cross-sector or cascading consequences", "disproportionate impact on vulnerable populations", "significant regulatory or systemic implications"],
                                            "result": "non-material on current evidence: no qualifier evidenced (assessed 2026-11-24; reassess if a regulator review or a prolonged network effect is reported)",
                                            "not_merged_with": "RS-075 (August Sydney Airport staffing-related disruption) - unrelated cause and date"}}))
    # --- Q3: Telstra retrospective finding (new record) ----------------------------------------------------------------------------------
    tel = [ev("1b59921d-abf0-4725-b1ac-b60efc5607c1", "ARN - Australian IT Channel", "2026-09-01T23:33:14Z", "2026-09-06T01:03:14Z", "REFERENCE", "Telstra outage report finds critical network function lacked oversight",
              note="summary: Telstra failed to treat network timing as a critical network capability; unclear ownership, insufficient expertise and weak process controls contributed to the 8 July nationwide mobile outage that disrupted services and affected some Triple Zero calls"),
           ev("d8c69eac-baa4-4eca-956c-77dd4945c0b1", "Google News - Telstra", "2026-09-02T00:47:42Z", "2026-09-06T01:03:13Z", "REFERENCE", "Telstra's only timing experts were on a required break before network fell over - SMH.com.au"),
           ev("410d2d7a-5d3b-4395-8b63-439208366a7d", "Google News - Telstra", "2026-09-02T00:58:23Z", "2026-09-10T20:00:13Z", "BRIEF", "TLS:ASX Announcement - Telstra releases external expert findings on July outage - 02 Sep 2026 - Market Index", note="ASX announcement of the external expert findings (via Market Index copy)"),
           ev("360d868c-e22d-473c-8ca2-616339fd78e5", "Google News - Telstra", "2026-09-02T03:08:00Z", "2026-09-06T01:03:13Z", "BRIEF", "Telstra investigation finds lack of money, too few staff caused outage - AFR"),
           ev("1040f778-c1ac-4ffd-82c4-5a25ebf95fe8", "Google News - Telstra", "2026-09-02T05:43:40Z", "2026-09-06T01:03:13Z", "REFERENCE", "Telstra outage exposed years of weaknesses in network timing, audit finds - Telecompaper"),
           ev("f63e39c6-eda2-434b-9ac3-ca715d05d728", "Google News - Telstra", "2026-09-02T08:26:29Z", "2026-09-09T22:11:33Z", None, "Telstra outage investigation reveals problems that led to nationwide meltdown - 7NEWS"),
           ev("2e9118cf-ecad-4932-b0a1-d94ff6506a50", "Google News - Telstra", "2026-09-03T20:03:28Z", "2026-09-17T10:16:45Z", "BRIEF", "Headlines: Telstra investigation into July outage - The Daily Aus")]
    agm = [ev("51b7c290-643c-434c-8b50-15286420db6b", "Google News - Telstra", "2026-10-12T16:40:26Z", "2026-10-12T19:00:19Z", "BRIEF", "Telstra execs face shareholder grilling over outage - The Canberra Times"),
           ev("09a1ed42-9bbf-4ba7-82a4-ab5f6e7c7d65", "Google News - Telstra", "2026-10-12T23:04:00Z", "2026-10-13T01:58:11Z", "REFERENCE", "'Shouldn't have happened': Telstra faces AGM grilling - The West Australian"),
           ev("47ef2735-7fad-44ee-bcf5-d29a761c3c4b", "Google News - Telstra", "2026-10-13T05:50:26Z", "2026-10-13T07:58:08Z", "WATCH", "Telstra boss faces AGM fury over national outage - The Australian"),
           ev("f11b11b2-7aec-4143-afcd-81f730a84fc7", "Google News - Telstra", "2026-10-13T13:58:51Z", "2026-10-16T13:26:28Z", "REFERENCE", "Telstra's Brady Loses $607K Pay at AGM Fury [2026] - tech-insider.org", note="headline only; low-quality publisher; not relied on")]
    out.append(rec("RS-082", "Q3-finding", "Telstra external (TAP) review findings on the 8 Jul 2026 nationwide outage: timing not treated as a critical capability; unclear ownership, insufficient expertise, weak process controls (public 1-2 Sep 2026); AGM scrutiny 12-14 Oct",
                   "confirmed_material", MRF, "Newly published root causes and control failures from a review of an out-of-window outage: material intelligence in its own right, assessed as a retrospective finding rather than as incident detection.", "telecommunications", "2026-09-01T23:33:14Z",
                   owner("owner Q3", "Q3: RS-005 is retrospective for incident-detection scoring, but newly published findings, root causes, control failures, regulatory findings and remediation commitments can be material intelligence in their own right: create a separate record in category 'material retrospective finding' with evidence; do not discard it", "RS-005"),
                   tel, sectors=["telecommunications"], start="2026-07-08T00:00:00Z", start_conf="medium", level_reason="Root-cause findings (timing-system fault, under-resourcing) directly relevant to CPS 230 provider-risk learning (v1 note on RS-005).", confidence="medium",
                   discovered="web_search", sources=["https://www.telstra.com.au/exchange/what-we-ve-learned-from-the-external-investigation-of-our-july-o", "https://www.telstra.com.au/content/dam/tcom/dynamic-media-projects/luke-campbell/TAPFindingsforTelstraOutage.pdf",
                                                     "https://www.canberratimes.com.au/story/9342169/lack-of-oversight-expertise-drove-major-telstra-outage/"],
                   verification="findings_from_tjr_row_summaries_and_titles_only",
                   uncertain=["The TAP report PDF and Telstra's Exchange post were NOT read in this session or collected by TJR: findings are as stated in TJR row summaries/titles only.",
                              "Regulatory findings and remediation commitments: NOT VERIFIED here (ACMA investigation 'ongoing' is a v1 note, not re-read).",
                              "First TJR collection was 6 Sep, 4.1 days after publication, because ARN and the Google News feeds were added on 6 Sep (COVERAGE_CHANGES).",
                              "AGM date 13 vs 14 Oct differs across summaries; figures (600 Triple Zero calls, 33,000 complaints) from secondary summaries (v1 uncertain_facts)."],
                   extra={"parent_incident": "8 Jul 2026 Telstra nationwide outage (out of window; stale retellings RS-019, RS-050)", "related_ids": ["RS-005", "RS-019", "RS-050"],
                          "finding_attributes": {"root_causes_and_control_failures": ["network timing not treated as a critical network capability", "unclear ownership", "insufficient expertise", "weak process controls", "only timing experts on a required break (SMH headline)", "lack of money and too few staff (AFR headline)", "years of weaknesses in network timing, audit finds (Telecompaper headline)"],
                                                 "public_dates": {"findings_public": "2026-09-01/02 (ARN 1 Sep 23:33Z; ASX announcement 2 Sep)", "agm_scrutiny": "2026-10-12 to 2026-10-14"},
                                                 "regulatory_findings": "NOT PROVIDED (not read)", "remediation_commitments": "NOT PROVIDED (not read)"},
                          "lifecycle": [{"date": "2026-09-01", "kind": "findings published", "development": "External expert (TAP) findings made public; ASX announcement 2 Sep", "evidence": [e["event_id"] for e in tel]},
                                        {"date": "2026-10-12", "kind": "agm scrutiny", "development": "AGM scrutiny of executives over the outage (12-14 Oct)", "evidence": [e["event_id"] for e in agm]}],
                          "agm_evidence": agm}))
    # --- Q8: RS-004 forward-looking risk signal (new record) -----------------------------------------------------------------------------
    out.append(rec("RS-083", "Q8-signal", "AEMO reserve notices for NSW: forecast Lack Of Reserve Level 1 (LOR1) for 12 Oct and suspect LOR1/LOR2 from 10 Oct 2026 (forward-looking risk signal around the 12 Oct NSW price spike)",
                   "confirmed_material", MEW, "Reserve-tightness notices are leading indicators of system stress even when supply is maintained: an emerging risk/warning, not a disruption. Owner-designated 'potentially material'.", "energy", "2026-10-09T19:00:23Z",
                   owner("owner Q8", "Q8: RS-004 is NON-MATERIAL for actual disruption detection but RETAIN as a potentially material FORWARD-LOOKING RISK SIGNAL (reserve warnings LOR1/LOR2 and abnormal market conditions are leading indicators of system stress even when supply is maintained); TJR holds AEMO LOR notices for NSW 10-12 Oct", "RS-004"),
                   [ev("7763f981-4fb8-4056-842d-6caa7840466f", "AEMO Market Notices", "2026-10-09T19:00:23Z", "2026-10-09T19:00:23Z", "REFERENCE", "STPASA - Forecast Lack Of Reserve Level 1 (LOR1) in the NSW Region on 12/10/2026", note="published_at equals collected_at for this feed; no independent publication time"),
                    ev("9e56c031-7dfc-4670-acaf-1e95b75d4e5a", "AEMO Market Notices", "2026-10-10T00:00:00Z", "2026-10-09T19:00:23Z", "REFERENCE", "PDPASA - Suspect Lack Of Reserve Levels 1 and 2 (LOR1/ LOR2) in the NSW Region beginning on 10/10/2026"),
                    ev("553633dd-0d94-42f2-bd1d-252c67a81a2a", "AEMO Market Notices", "2026-10-11T19:05:22Z", "2026-10-11T19:05:22Z", None, "PDPASA - Forecast Lack Of Reserve Level 1 (LOR1) in the NSW Region on 12/10/2026", note="event.brief_id set (reached a brief); canonical_url nemweb market notice R145575")],
                   start="2026-10-12T03:10:00Z", start_conf="low", level="med", level_reason="NSW region reserve tightness; no supply loss or load shedding reported (v1 note on RS-004).", confidence="low-medium",
                   discovered="tjr_events_only", verification="primary_notices_in_tjr_rows",
                   uncertain=["'Potentially material' per the owner: LOR1 is the lowest reserve alert; no actual supply loss or load shedding was evidenced.",
                              "The 12 Oct price event itself rests on secondary sources only (Modo Energy, energy-storage.news: two-hour event, assumed 14:10-16:05 AEDT; not confirmed to be the same event).",
                              "Notice text beyond the title (levels, MW) was not read."],
                   extra={"materiality_qualifier": "potential (owner Q8)", "related_ids": ["RS-004"], "forward_looking": True,
                          "lead_time_note": "notices published 1-3 days ahead of 12 Oct"}))
    return out
