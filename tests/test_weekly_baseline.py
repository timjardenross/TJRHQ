"""Weekly baseline report: offline, no network, frozen reference untouched, candidates never scored."""
from __future__ import annotations

import hashlib
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tools" / "intelligence"))

import weekly_baseline as wb

REF_DIR = _REPO / "knowledge" / "intelligence-reference-set"
V1 = REF_DIR / "reference_set_v1.json"
V2C = REF_DIR / "reference_set_v2_candidates.json"
FROZEN = {  # sha256 of the frozen v0 and v1 files: changing any of them must be a deliberate new version, not an edit
    "reference_set.json": "15e3a29ed6fbf9c2e511ba0779e12ab83ed48c0d8bda215420a5ed9a9e9d4fd9",
    "baseline-2026-11-24.json": "851f014f3395f24f8c0b755f2404171579e30af212b1945b6f2403bd28a60425",
    "reference_set_v1.json": "6feff465ddeeea5a5489d7877eb6a801d63849cdcd141c8819ab9b877b1d5d62",
    "baseline_v1-2026-11-24.json": "0b526e90867ca318f955b092b2b53e5893c224805fbe7d4dba55b2a111d076eb",
    "events_export_2026-11-24.json": "440cf0787539f411bc046b674249e87b0e04c18b0dd8ebb7e54ac9c009ec1837",
}
AS_OF = datetime(2026, 11, 24, 6, 34, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


def _inc(iid, first, regex, status="confirmed_material", level="high"):
    return {"id": iid, "title": f"{iid} title", "status": status, "reviewed_by_human": False,
            "first_public_report_time": {"value": first}, "start_time_utc": {"value": first}, "end_time_utc": {"value": None},
            "australian_materiality": {"level": level}, "set_membership": "v0",
            "tjr_detection": {"match": {"title_regex": regex, "published_from": (first or "")[:10] or None, "published_to": (first or "")[:10] or None}}}


def _ref(*incs):
    return {"name": "t", "set_version": "t1", "incidents": list(incs)}


def _ev(eid, title, pub, col, src="ABC News", brief=None):
    return {"event_id": eid, "source_name": src, "raw_title": title, "published_at": pub, "collected_at": col, "brief_id": brief}


def test_frozen_v0_v1_files_are_unchanged():
    for name, sha in FROZEN.items():
        assert hashlib.sha256((REF_DIR / name).read_bytes()).hexdigest() == sha, f"{name} is frozen; create a new version instead"


def test_export_sql_is_select_only_and_names_the_window():
    sql = wb.print_export_sql("2026-11-18", "2026-11-25")
    assert sql.count("select") >= 3 and "2026-11-15" in sql and "2026-11-28" in sql
    for bad in ("insert ", "update ", "delete ", "drop ", "alter ", "create "):
        assert bad not in sql.lower()


def test_candidates_file_is_refused_for_scoring():
    with pytest.raises(SystemExit):
        wb.assert_scoreable_reference(json.loads(V2C.read_text()))
    wb.assert_scoreable_reference(json.loads(V1.read_text()))  # the frozen set passes


def test_v2_candidates_shape_and_no_confirmations():
    d = json.loads(V2C.read_text())
    v1_ids = {i["id"] for i in json.loads(V1.read_text())["incidents"]}
    cands = [i for i in d["incidents"] if i["status"] == "candidate"]
    assert 15 <= len(cands) <= 20
    assert {i["status"] for i in d["incidents"]} <= {"candidate", "unresolved"}
    assert not any(i["status"].startswith("confirmed") for i in d["incidents"])
    ids = [i["id"] for i in d["incidents"]]
    assert len(ids) == len(set(ids)) and not set(ids) & v1_ids
    for i in d["incidents"]:
        assert i["reviewed_by_human"] is False
        assert i["first_report"]["value"] and i["first_report"]["event_id"]
        assert i["evidence"] and all(e["event_id"] and e["published_at"] for e in i["evidence"])
        assert min(e["published_at"] for e in i["evidence"]) == i["first_report"]["value"]
    for i in cands:  # all three strict criteria are stated for every candidate
        assert all(i["criteria"][k] for k in ("stated_operational_impact", "named_service", "credible_source"))
    all_evidence = [e["event_id"] for i in d["incidents"] for e in i["evidence"]]
    assert all(len(x) == 36 for x in all_evidence)


def test_weekly_reference_excludes_undated_and_out_of_window():
    ref = _ref(_inc("A", "2026-11-19T00:00:00Z", "alpha"), _inc("B", "2026-11-01T00:00:00Z", "beta"), _inc("C", None, "gamma"))
    sub, undated = wb.weekly_reference(ref, wb.ps._day("2026-11-18"), wb.ps._day("2026-11-25"))
    assert [i["id"] for i in sub["incidents"]] == ["A"] and undated == ["C"]


def test_morning_variant_and_brief_shape():
    v1 = "<b>MORNING BRIEF</b>\n🛰 EVIDENCE-BASED PICTURE (V1)\n- None.\n- [cyber · x] real item\n<b>📡 COLLECTION HEALTH</b>\n"
    legacy = "<b>MORNING BRIEF</b>\n<b>📡 INTELLIGENCE POSTURE</b>\n  Posture: <b>🟡 AMBER</b>\n  <b>What matters today</b>\n  1. one\n  2. two\n"
    both = v1 + "<b>📡 LEGACY POSTURE (previous method)</b>\n"
    assert wb.morning_variant(v1) == "morning_v1" and wb.morning_variant(legacy) == "morning_legacy"
    assert wb.morning_variant(both) == "morning_v1_fallback" and wb.morning_variant("hello") == "morning_unclassified"
    assert wb.brief_shape(v1)["sections"] == 2 and wb.brief_shape(v1)["items"] == 1  # placeholder "- None." is not an item
    s = wb.brief_shape(legacy)
    assert s["sections"] == 2 and s["items"] == 2  # posture badge is not a section


def test_source_coverage_counts_use_source_effectiveness():
    rows = [
        {"source_name": "Healthy", "active": True, "n7": 2, "n30": 9, "last_event": None, "checks7": 14, "bad7": 0, "last_check": "2026-11-24T05:00:00+00:00"},
        {"source_name": "Broken", "active": True, "n7": 0, "n30": 0, "last_event": None, "checks7": 14, "bad7": 14, "last_check": "2026-11-24T05:00:00+00:00"},
        {"source_name": "Off", "active": False, "n7": 0, "n30": 0, "last_event": None, "checks7": 0, "bad7": 0, "last_check": None},
    ]
    out = wb.source_coverage(rows, AS_OF)
    assert out["counts"]["HEALTHY"] == 1 and out["counts"]["BROKEN"] == 1 and out["counts"]["UNCOVERED"] >= 1
    assert wb.source_coverage(None, AS_OF)["provided"] is False


def _build(events, briefs, ref=None, ratings=None):
    ref = ref or _ref(_inc("A", "2026-11-19T08:00:00Z", "alpha outage"), _inc("N", "2026-11-20T00:00:00Z", "routine notice", status="confirmed_non_material", level="low"))
    return wb.build_report(ref, events, briefs, None, ratings, "2026-11-18", "2026-11-25", AS_OF)


def test_detected_missed_surfacing_and_burden_never_estimated():
    events = [_ev("e1", "Alpha outage hits customers", "2026-11-19T08:30:00Z", "2026-11-19T10:30:00Z")]
    briefs = [{"brief_date": "2026-11-20", "brief_type": "morning", "brief_text": "<b>t</b>\n<b>📡 INTELLIGENCE POSTURE</b>\n  1. Alpha outage continues\n"},
              {"brief_date": "2026-11-21", "brief_type": "morning", "brief_text": "<b>t</b>\n🛰 EVIDENCE-BASED PICTURE (V1)\n- None.\n"}]
    r = _build(events, briefs)
    assert r["material_incidents"]["detected"] == 1 and r["material_incidents"]["missed"] == 0
    assert r["time_to_first_detection_hours"]["median"] == 2.5
    sv = r["morning_v1_vs_legacy"]["by_variant"]
    assert sv["morning_legacy"]["surfaced"] == ["A"] and sv["morning_v1"]["not_surfaced"] == ["A"]
    assert r["false_escalation"]["negatives_scored"] == 1 and r["false_escalation"]["escalated"] == 0
    b = r["manual_verification_burden"]
    assert b["minutes"] is None and b["status"] == "NOT PROVIDED" and "OWNER TO FILL" in b["owner_prompt"]
    md = wb.render_markdown(r)
    assert "NOT PROVIDED" in md and "__________" in md


def test_missed_incident_is_reported_and_ratings_csv_is_the_only_burden_source(tmp_path):
    csv_path = tmp_path / "ratings.csv"
    csv_path.write_text("date,brief_usefulness_1to5,noise_count,manual_verification_minutes,notes\n2026-11-20,4,3,25,\n2026-11-21,3,2,15,\n")
    r = _build([], [], ratings=str(csv_path))
    assert r["material_incidents"]["missed_ids"] == ["A"]
    assert r["manual_verification_burden"]["minutes"] == 40.0 and r["manual_verification_burden"]["status"] == "provided"


def test_cli_end_to_end_on_frozen_v1(tmp_path, capsys):
    (tmp_path / "events.json").write_text(json.dumps([
        _ev("x1", "Eyre Peninsula residents worried about further blackouts", "2026-11-21T07:45:38Z", "2026-11-21T08:44:56Z")]))
    (tmp_path / "briefs.json").write_text("[]")
    rc = wb.main(["--export-dir", str(tmp_path), "--week-start", "2026-11-18", "--week-end", "2026-11-25", "--as-of", "2026-11-24T06:34:00Z",
                  "--out-md", str(tmp_path / "o.md"), "--out-json", str(tmp_path / "o.json")])
    assert rc == 0
    rep = json.loads((tmp_path / "o.json").read_text())
    assert rep["reference_set"]["set_version"] == "v1" and rep["material_incidents"]["detected"] == 1
    assert rep["source_coverage"]["provided"] is False and (tmp_path / "o.md").read_text().startswith("# Intelligence weekly baseline")
    assert V1.read_bytes() and hashlib.sha256(V1.read_bytes()).hexdigest() == FROZEN["reference_set_v1.json"]
