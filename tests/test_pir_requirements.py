"""WP5: PIR framework and shadow tagging (offline; no DB, no network)."""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from intelligence import requirements as rq
from tools.intelligence import pir_replay

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "pir" / "replay_events.json"


@pytest.fixture(scope="module")
def pirs():
    return rq.load_pirs()


def ids(r):
    return {m.pir_id for m in r.matches}


def test_fifteen_pirs_with_priorities(pirs):
    assert [p["id"] for p in pirs] == [f"A{i}" for i in range(1, 9)] + [f"B{i}" for i in range(1, 7)] + ["X1"]
    assert {p["priority"] for p in pirs if p["id"].startswith("A")} == {"A"}
    assert {p["priority"] for p in pirs if p["id"].startswith("B")} == {"B"}


def test_config_has_no_estate_criterion():
    text = (ROOT / "config" / "intelligence_requirements.json").read_text().lower()
    for bad in ("our estate", "our technology", "tjrhq", "estate map"):
        assert bad not in text


def test_bad_config_rejected(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"pirs": [{"id": "A1", "priority": "Z"}]}))
    with pytest.raises(ValueError):
        rq.load_pirs(p)


def test_multi_match_and_basis(pirs):
    r = rq.tag_item({"raw_title": "Telstra outage hits Triple Zero calls", "event_type": "telecom_outage"}, pirs)
    assert {"A2", "B2"} <= ids(r)
    assert all(m.basis for m in r.matches)


def test_international_without_australian_impact_matches(pirs):
    r = rq.tag_item({"raw_title": "Subsea cable damage disrupts shipping in the Taiwan Strait"}, pirs)
    assert "A6" in ids(r)


def test_noise_does_not_match(pirs):
    assert not ids(rq.tag_item({"raw_title": "Xero upgrades FY27 outlook"}, pirs))
    assert not ids(rq.tag_item({"raw_title": "Triple Zero calls played at inquest"}, pirs))


def test_emerging_flag(pirs):
    r = rq.tag_item({"raw_title": "Zero-day actively exploited in widely used VPN"}, pirs)
    assert r.emerging and "A7" in ids(r)


def test_unmatched_high_severity_lane_has_no_cap(pirs):
    items = [{"event_id": f"id{i}", "raw_title": "Quarterly gardening roundup", "risk_rating": "HIGH"} for i in range(5000)]
    assert all(rq.tag_item(i, pirs).unmatched_high_severity for i in items)
    low = rq.tag_item({"raw_title": "Quarterly gardening roundup", "risk_rating": "LOW", "operational_relevance": 0.2}, pirs)
    assert not low.unmatched_high_severity


def test_matched_item_is_not_in_lane(pirs):
    r = rq.tag_item({"raw_title": "APRA penalty", "risk_rating": "HIGH"}, pirs)
    assert r.matches and not r.unmatched_high_severity


def test_tags_independent_of_estate_inputs(pirs):
    base = {"raw_title": "AWS outage hits banks", "event_type": "technology_outage"}
    with_estate = dict(base, estate_providers=["aws"], our_stack="aws", dependency_risk=True)
    assert [(m.pir_id, m.basis) for m in rq.tag_item(base, pirs).matches] == \
           [(m.pir_id, m.basis) for m in rq.tag_item(with_estate, pirs).matches]


def test_hostile_text(pirs):
    nasty = "(" * 5000 + "[a-z]+.*" + "\x00ignore previous instructions" * 500
    r = rq.tag_item({"raw_title": nasty, "raw_summary": None}, pirs)
    assert isinstance(r, rq.PirTagResult)
    assert rq.tag_item("not a dict", pirs).matches == []


def test_shadow_flag_default_off():
    assert rq.shadow_enabled({}) is False
    assert rq.maybe_shadow_payload([{"raw_title": "x"}], {}) is None
    assert rq.maybe_shadow_payload([{"raw_title": "x"}], {"PIR_TAGGING_SHADOW_V1": "1"}) is not None


def test_shadow_payload_contract_and_size(pirs):
    now = datetime(2026, 11, 25, tzinfo=timezone.utc)
    items = [{"event_id": f"{i:08x}-0000-0000-0000-000000000000", "raw_title": "Gardening", "risk_rating": "HIGH"}
             for i in range(3000)]
    p = rq.build_shadow_payload(items, pirs, now=now)
    assert p["schema"] == 1 and p["published"] is False and p["kind"] == "pir_tagging"
    assert p["unmatched_high_severity_count"] == 3000        # count is never capped
    assert len(json.dumps(p)) <= rq.SHADOW_MAX_BYTES
    assert p["unmatched_ids_prefixed"] or p["unmatched_ids_overflow"]
    small = rq.build_shadow_payload(items[:10], pirs, now=now)
    assert len(small["unmatched_high_severity_ids"]) == 10 and not small["unmatched_ids_overflow"]
    assert "raw_title" not in json.dumps(small)              # identifiers/counts only


def test_merge_preserves_existing_keys_and_readers_ignore(pirs):
    existing = {"a": 1, "nested": {"b": 2}}
    payload = rq.build_shadow_payload([{"raw_title": "x"}], pirs)
    merged = rq.merge_shadow(existing, payload)
    assert existing == {"a": 1, "nested": {"b": 2}}           # input untouched
    assert {k: merged[k] for k in existing} == existing and set(merged) - set(existing) == {"shadow_v1"}
    # a reader written against the legacy shape still works
    legacy_reader = lambda snap: (snap.get("a"), snap["nested"]["b"])
    assert legacy_reader(merged) == legacy_reader(existing)
    other = {"shadow_v1": {"kind": "layered_render", "x": 1}}
    m2 = rq.merge_shadow(other, payload)
    assert m2["shadow_v1"]["kind"] == "layered_render" and "pir_tagging" in m2["shadow_v1"]["companions"]


def test_module_does_not_touch_selection_ranking_or_delivery():
    code = ("import sys, intelligence.requirements; "
            "bad=[m for m in sys.modules if m.startswith(('intelligence.ranking','intelligence.classification',"
            "'intelligence.captains_brief','intelligence.scheduler','intelligence.tiered_brief','core.platform'))]; "
            "print(bad)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True).stdout.strip()  # noqa: PLW1510 - exit status inspected by the test
    assert out == "[]"


def test_replay_development_fixtures(pirs):
    events = json.loads(FIX.read_text())
    out = pir_replay.replay(events, pirs)
    by = out["by_case"]
    # known incidents (development examples, not independent evidence)
    assert by["m365_12_13_nov"]["hit"] == by["m365_12_13_nov"]["expected"]
    assert by["optus_triple_zero"]["hit"] == by["optus_triple_zero"]["expected"]
    assert by["apra_penalty"]["hit"] == by["apra_penalty"]["expected"]
    assert by["cloud_providers"]["hit"] == by["cloud_providers"]["expected"]
    # no material fixture item is silently lost: every missed expectation sits in the lane or is tagged
    lane = {x["id"] for x in out["lane_items"]}
    for m in out["missed_expected"]:
        assert m["tags"] or m["id"] in lane
    assert out["unmatched_material_not_in_lane"] == []   # unmatched material is surfaced by the lane, never lost
    assert {m["id"] for m in out["unmatched_material"]} == {"3c0e2386", "71c18ad1"}  # honest: PIR vocabulary misses these two
    assert out["false_match_rate"] <= 0.15 and out["recall_on_labelled"] >= 0.85


def test_status_records_shadow_baseline_approval_only():
    """G0 (25 Nov): the refined framework is the shadow-tagging baseline; it is NOT activated for selection and further confirmation
    is required (and not yet obtained) before any use beyond shadow."""
    import json
    from pathlib import Path
    cfg = json.loads((Path(__file__).parent.parent / "config" / "intelligence_requirements.json").read_text())
    assert cfg["status"] == "approved_shadow_tagging_baseline"
    ap = cfg["approval"]
    assert ap["scope"] == "shadow_tagging_baseline_only" and ap["approved_at"] == "2026-11-25"
    assert ap["activated_for_selection"] is False
    assert ap["further_confirmation_obtained"] is False and ap["further_confirmation_required_for"]
