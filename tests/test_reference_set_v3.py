"""Reference set v3: reproducible build, frozen inputs untouched, category/status mapping, owner decisions and audit trail present."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tools" / "intelligence"))

import build_reference_set_v3 as B
import reference_set_v3_records as R
import weekly_baseline as wb

REF_DIR = _REPO / "knowledge" / "intelligence-reference-set"
V3 = json.loads((REF_DIR / "reference_set_v3.json").read_text(encoding="utf-8"))
BY = {i["id"]: i for i in V3["incidents"]}
CANDIDATES_SHA = "17e8057cf1dd47852bcbbcd97be83c40ad423b831527530d78f89779f26e4cab"
AUDIT_FIELDS = {"previous_value", "corrected_value", "evidence", "reason", "date_applied", "applied_by"}


def test_committed_v3_files_match_a_fresh_build():
    header, export = B.build()
    assert (REF_DIR / "reference_set_v3.json").read_text(encoding="utf-8") == B.render(header)
    assert (REF_DIR / "events_export_v3-2026-11-24.json").read_text(encoding="utf-8") == B.render(export)


def test_frozen_inputs_are_untouched():
    assert hashlib.sha256((REF_DIR / "reference_set_v2_candidates.json").read_bytes()).hexdigest() == CANDIDATES_SHA


def test_every_record_has_a_category_and_status_maps_to_it():
    allowed = set(R.CATEGORIES)
    assert len(BY) == len(V3["incidents"])
    for r in V3["incidents"]:
        assert r["intelligence_category"] in allowed, r["id"]
        assert r["category_rationale"], r["id"]
        st, cat = r["status"], r["intelligence_category"]
        if st == "confirmed_material":
            assert cat in R.MATERIAL_CATEGORIES, r["id"]
        elif st == "unresolved_insufficiently_verified":
            assert cat == "unresolved", r["id"]
        else:
            assert cat == "non_material", r["id"]
    assert set(V3["statuses"]) >= {r["status"] for r in V3["incidents"]}


def test_header_counts_are_consistent_and_there_is_no_target():
    c = V3["counts"]
    assert c["records"] == len(V3["incidents"])
    assert sum(c["by_status"].values()) == c["records"] == sum(c["by_intelligence_category"].values())
    assert c["by_status"]["confirmed_material"] == sum(c["by_intelligence_category"][k] for k in R.MATERIAL_CATEGORIES)
    assert "No target" in c["material_count_note"]
    assert set(c["confirmed_material_ids"]) == {r["id"] for r in V3["incidents"] if r["status"] == "confirmed_material"}


def test_review_block_records_the_owner_decision():
    rv = V3["review"]
    assert rv["reviewed_by_human"] is True and rv["reviewer"] == "owner" and rv["date"] == "2026-11-24" and rv["decision_pointer"]
    material = [r for r in V3["incidents"] if r["intelligence_category"] in R.MATERIAL_CATEGORIES]
    assert all(r["reviewed_by_human"] and r["decision"]["decided_by"] == "owner" for r in material)
    assert set(rv["reviewed_record_ids"]) | set(rv["not_reviewed_record_ids"]) == set(BY)


def test_all_twelve_corrections_have_a_complete_audit_trail():
    trail = {a["id"]: a for a in V3["audit_trail"]}
    for n in range(1, 13):
        a = trail[f"CORR-{n:02d}"]
        assert AUDIT_FIELDS <= set(a) and a["applied_by"] and a["date_applied"] == "2026-11-24", a["id"]
        assert a["previous_value"] is not None and a["corrected_value"] and a["evidence"] and a["reason"]
    assert {"SUPP-01", "SUPP-02", "RECLASS-01", "RECLASS-02", "RECLASS-03", "Q9"} <= set(trail)
    export = json.loads((REF_DIR / "events_export_v3-2026-11-24.json").read_text(encoding="utf-8"))
    assert not {e["event_id"] for e in export["events"]} & {"gnrest01", "itnrec01"}


def test_origin_is_one_incident_with_dated_lifecycle_entries():
    o = BY["RS-042"]
    assert o["status"] == "confirmed_material" and o["intelligence_category"] == "material_operational_disruption"
    assert o["folded_candidates"] == ["C2-U03"] and "C2-U03" not in BY
    dates = {l["date"]: l for l in o["lifecycle"]}
    assert {"2026-07-22", "2026-07-23", "2026-08-21", "2026-09-10", "2026-10-14", "2026-10-20"} <= set(dates)
    assert dates["2026-08-21"]["source_candidate"] == "C2-U03"
    assert all(l["evidence"] for l in o["lifecycle"] if l["date"] != "2026-07-22" or l["evidence"])
    assert o["start_time_utc"]["value"].startswith("2026-07-22")


def test_owner_amendment_records():
    assert BY["RS-005"]["status"] == "stale_or_resurfaced" and BY["RS-005"]["superseded_by_finding_record"] == "RS-082"
    f = BY["RS-082"]
    assert f["intelligence_category"] == "material_retrospective_finding" and f["evidence"] and f["finding_attributes"]["remediation_commitments"] == "NOT PROVIDED (not read)"
    assert BY["RS-004"]["status"] == "confirmed_non_material" and BY["RS-004"]["non_material_type"] == "market_event_no_supply_loss"
    s = BY["RS-083"]
    assert s["intelligence_category"] == "material_emerging_risk_or_warning" and s["forward_looking"] and s["materiality_qualifier"].startswith("potential")
    c = BY["RS-079"]["separately_sourced_attributes"]
    assert {"four_in_progress_ambulance_calls_cut_out", "authorities_state_no_triple_zero_calls_lost"} <= set(c)
    assert BY["RS-079"]["status"] == "confirmed_material" and BY["RS-079"]["duration_minutes"] == 4
    sa = BY["RS-075"]
    assert sa["cause"]["status"] == "disputed" and sa["cause"]["established_cause"] is None and len(sa["cause"]["competing_claims"]) >= 2
    assert {l["date"] for l in sa["lifecycle"]} >= {"2026-08-08", "2026-08-09", "2026-08-26"}
    for rid in ("RS-076", "RS-078"):  # Q6: assessed consequences, not a blanket exclusion
        r = BY[rid]
        assert r["status"] == "confirmed_non_material" and r["non_material_type"] == "assessed_low_consequence"
        assert r["non_material_basis"]["consequences_found"] and r["non_material_basis"]["consequences_not_found"]
    assert BY["RS-084"]["q4_assessment"]["qualifiers_evidenced"] == [] and BY["RS-084"]["status"] == "confirmed_non_material"
    for rid in ("RS-061", "RS-080", "RS-081", "RS-077"):
        assert BY[rid]["status"] == "confirmed_material" and BY[rid]["q4_assessment"]["result"]
    assert BY["RS-081"]["q4_assessment"]["qualifiers_evidenced"] and "vulnerable" in BY["RS-081"]["q4_assessment"]["qualifiers_evidenced"][0]
    assert BY["RS-077"]["status"] == "confirmed_material" and BY["RS-077"]["review_confidence"] == "medium"


def test_duplicates_point_at_existing_records_and_candidates_are_all_dispositioned():
    for r in V3["incidents"]:
        if r["status"] == "duplicate_report":
            assert r["duplicate_of"] in BY
    assert BY["RS-071"]["duplicate_of"] == "RS-066" and "C2-U04" in BY["RS-051"]["aliases"]
    cand = json.loads((REF_DIR / "reference_set_v2_candidates.json").read_text(encoding="utf-8"))
    assert {i["id"] for i in cand["incidents"]} <= set(V3["candidate_disposition_map"])


def test_evidence_basis_is_explicit_and_session_reads_are_not_passed_off_as_rows():
    seen = 0
    def walk(o):
        nonlocal seen
        if isinstance(o, dict):
            if "basis" in o and "headline" in o:
                seen += 1
                assert o["basis"] in ("tjr_row", "review_pack_web_read", "session_web_read")
                if o["basis"] == "session_web_read":
                    assert o["event_id"] is None and o["ref"].startswith("session-")
                elif o["event_id"]:
                    assert len(o["event_id"]) == 36
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(V3["incidents"])
    assert seen > 80


def test_v3_passes_the_scoring_gate_and_measurements_cover_every_record_with_a_pattern():
    wb.assert_scoreable_reference(V3)
    meas = json.loads((REF_DIR / "measurements_v3-2026-11-24.json").read_text(encoding="utf-8"))
    ids = {r[0] for r in meas["detection_rows"]}
    assert ids <= set(BY) | {"RS-042#dev"}
    for r in V3["incidents"]:
        assert r["tjr_detection"]["appeared"] == (r["id"] in ids or r["id"] == "RS-051"), r["id"]
