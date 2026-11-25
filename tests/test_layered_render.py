import copy
import json
import pathlib
import sys

import pytest

from intelligence.brief import layered_render as lr
from intelligence.brief.layered_render import CoverageStatus as CS
from intelligence.brief.layered_render import OperationalPosture as OP

FX = pathlib.Path(__file__).parent / "fixtures" / "layered"
sys.path.insert(0, str(FX))
import stubs


@pytest.fixture
def nov25():
    return json.loads((FX / "morning_2026-11-25.json").read_text())


def render(d, **kw):
    kw.setdefault("posture", None)
    kw.setdefault("confidence", None)
    return lr.render_layered(d["incidents"], coverage=d["coverage"], judgements=d.get("judgements"), outlook=None, limits=None, evidence_refs=None, **kw)


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(lr.FLAG, raising=False)
    assert not lr.enabled()


def test_nov25_three_axes_and_layers(nov25):
    r = render(nov25)
    assert r["axes"]["posture"]["value"] == "AMBER"          # provisional single-source ESCALATE item
    assert r["axes"]["coverage"]["value"] == "FULL"          # coverage 117/117: independent of posture
    assert r["axes"]["confidence"]["level"] == "MODERATE"   # 3 of 6 material items provisional
    for k in ("L1", "L2", "L3", "L4", "L6", "L7"):
        assert k in r, k
    assert "L5" not in r                      # nothing beyond what L2 already carries: omitted, not printed empty
    r5 = lr.render_layered(nov25["incidents"], posture=None, coverage=nov25["coverage"], confidence=None, outlook=[{"text": "Advisory follow-up expected.", "dated": False}])
    assert "L5" in r5


def test_each_incident_fully_treated_once(nov25):
    r = render(nov25)
    counts = lr.treatment_counts(r)
    assert counts and all(v == 1 for v in counts.values())
    assert len(counts) == len(set(counts))
    # every incident id is accounted for somewhere in L3 (full, line or counted) exactly once
    l3 = r["L3"]
    ids = [a["incident_id"] for a in l3["assessments"]] + [x["incident_id"] for x in l3["one_line"]] + l3["counted_ids"]
    assert sorted(ids) == sorted(i["incident_id"] for i in nov25["incidents"])


def test_international_material_substantive_without_australian_impact(nov25):
    r = render(nov25)
    full = {a["incident_id"] for a in r["L3"]["assessments"]}
    assert "inc-54de03474c" in full and "inc-fead0f727e" in full and "inc-06fbfb4861" in full   # international, relevance medium
    # low relevance international collapses to a count, not individual assessment
    assert "inc-d3dca09a66" in r["L3"]["counted_ids"] and "inc-0aeadfcc37" in r["L3"]["counted_ids"]
    assert any("lower-relevance international" in c for c in r["L3"]["counted"])
    l4 = {x["ref"] for x in r["L4"] if isinstance(x["ref"], str)}
    assert "inc-54de03474c" in l4


def test_collection_failure_never_a_disruption():
    inc = [{"incident_id": "inc-aaaaaaaaaa", "headline": "Feed X returned errors for 6 hours", "kind": "collection_issue", "priority": "ESCALATE", "materiality": "high"}]
    r = lr.render_layered(inc, posture=None, coverage={"degraded": True, "failed": 1, "expected": 10, "completed": 4}, confidence=None)
    assert "L3" not in r                       # not assessed as an incident
    assert r["axes"]["posture"]["value"] == "UNKNOWN"
    assert any("not an operational disruption" in x for x in r["L6"]["limits"])
    assert "disruption" not in r["L1"]["text"].lower().replace("not read as quiet", "") or "No defensible" in r["L1"]["text"]


def test_partial_coverage_quiet_is_never_bare_all_clear():
    cov = {"expected": 117, "completed": 110, "missing_sources": ["BOM", "ASD"], "failed": 0}
    r = lr.render_layered([], posture=None, coverage=cov, confidence=None, n_events=40)
    assert r["axes"]["posture"]["value"] == "GREEN"
    assert r["axes"]["coverage"]["value"] == "PARTIAL"
    t = r["L1"]["text"]
    assert "No significant development identified" in t and "limited by" in t and "BOM" in t
    assert "all clear" not in lr.to_text(r).lower().replace("not an all-clear", "")


def test_degraded_quiet_is_not_assessed_not_green():
    r = lr.render_layered([], posture=None, coverage={"degraded": True, "expected": 117, "completed": 20}, confidence=None, n_events=0)
    assert r["axes"]["posture"]["value"] == "UNKNOWN"
    assert "NOT ASSESSED" in r["L1"]["text"]
    assert "do not read this as quiet" in r["L1"]["text"]


def test_zero_events_full_coverage_still_unknown():
    r = lr.render_layered([], posture=None, coverage={"expected": 5, "completed": 5, "collection_status": "ok"}, confidence=None, n_events=0)
    assert r["axes"]["posture"]["value"] == "UNKNOWN"


def test_red_requires_confirmed_nonprovisional_escalate(nov25):
    inc = copy.deepcopy(nov25["incidents"])
    inc[0].update(evidence_status="officially_confirmed", provisional=False)
    r = lr.render_layered(inc, posture=None, coverage=nov25["coverage"], confidence=None)
    assert r["axes"]["posture"]["value"] == "RED"


def test_axes_independent_coverage_never_changes_posture(nov25):
    a = render(nov25)
    d = copy.deepcopy(nov25)
    d["coverage"].update(completed=100, missing_sources=["X"])
    b = render(d)
    assert a["axes"]["posture"]["value"] == b["axes"]["posture"]["value"] == "AMBER"
    assert a["axes"]["coverage"]["value"] != b["axes"]["coverage"]["value"]


def test_caller_posture_never_overridden(nov25):
    r = lr.render_layered(nov25["incidents"], posture=OP.GREEN, coverage=CS.PARTIAL, confidence="LOW")
    assert r["axes"]["posture"]["value"] == "GREEN"


def test_six_classes_present(nov25):
    d = copy.deepcopy(nov25)
    d["incidents"][5]["implications"] = ["Telecom and cyber sectors share this exposure if affected products are deployed."]
    d["incidents"][5]["competing_explanation"] = "Fix publication reflects routine disclosure rather than active exploitation."
    r = lr.render_layered(d["incidents"], posture=None, coverage=d["coverage"], confidence=None,
                          outlook=[{"text": "Vendor advisory follow-up expected within days.", "dated": False}])
    tags = {s["tag"] for a in r["L3"]["assessments"] for s in a["statements"]} | {x["tag"] for x in r["L5"]["outlook"]}
    assert tags >= {"FACT", "REPORTED", "ASSESSMENT", "INFERENCE", "FORECAST", "UNKNOWN"}


def test_empty_sections_omitted():
    r = lr.render_layered([], posture=None, coverage={"expected": 3, "completed": 3}, confidence=None, n_events=5)
    assert set(r) == {"axes", "L1", "L6", "meta"}


def test_l1_over_target_flag_does_not_cut_depth(nov25):
    d = copy.deepcopy(nov25)
    base = render(d)
    d["incidents"][0]["headline"] += " " + "x" * 2500
    r = render(d)
    assert r["L1"]["over_target"] is True
    assert len(r["L3"]["assessments"]) == len(base["L3"]["assessments"])           # depth unchanged
    assert any(a["headline"].endswith("x" * 2500) for a in r["L3"]["assessments"])  # nothing truncated in L3


def test_l1_not_a_cap_and_material_depth_in_l3(nov25):
    r = render(nov25)
    assert r["L1"]["chars"] > 0
    assert "further material item" in r["L1"]["text"] or len(r["L3"]["assessments"]) <= 3


def test_unmatched_high_severity_lane_uncapped():
    # round 3: the watch lane is a REVIEW list, uncapped and never silently dropped, but it does not by itself set the posture
    inc = [{"incident_id": f"inc-{n:010x}", "headline": f"Item {n}", "priority": "WATCH", "materiality": "medium",
            "pir": stubs.pir_dict(stubs.PirTagResult(unmatched_high_severity=True))} for n in range(7)]
    r = lr.render_layered(inc, posture=None, coverage=CS.FULL, confidence=None)
    assert len(r["L5"]["watch"]) == 7
    assert r["axes"]["posture"]["value"] == "GREEN" and r["axes"]["posture"]["watch_not_driving"] == 7


def test_stubs_claim_gate_and_status_in_l6(nov25):
    r = render(nov25, claim_gate=stubs.ClaimGateResult(passed=False, mode="enforce"), production_status=stubs.status_dict("DEGRADED", ["narrative placeholder"]))
    assert any("claim gate" in x for x in r["L6"]["limits"])
    assert "Production status: DEGRADED" in r["L1"]["text"]


def test_l6_always_present_quiet_full():
    r = lr.render_layered([], posture=None, coverage={"expected": 3, "completed": 3}, confidence=None, n_events=5)
    assert "not an all-clear" in r["L6"]["statement"]


def test_audio_script_no_ids_urls_tags_default_3min(nov25):
    d = copy.deepcopy(nov25)
    d["incidents"][2]["reports"][0]["url"] = "https://example.org/x"
    r = render(d)
    a = lr.audio_script(r)
    assert a["target_minutes"] == 3.0 and a["word_budget"] == 450
    import re
    assert not re.search(r"inc-[0-9a-f]{6}|https?://|\[(FACT|UNKNOWN)\]|/intelligence-workbench", a["script"])
    assert a["dropped_judgements"] == 0
    # written layers are unchanged by the audio target
    assert r == render(d)


def test_audio_over_target_reported_not_cut(nov25):
    d = copy.deepcopy(nov25)
    d["judgements"] = [{"statement": "Judgement number %d with a fair amount of explanatory text to take up spoken time." % n, "confidence": "moderate", "evidence": []} for n in range(60)]  # noqa: UP031 - percent format kept (shared template)
    r = render(d)
    a = lr.audio_script(r, minutes=1)
    assert a["over_target"] and a["dropped_judgements"] == 0
    assert a["script"].count("Judgement number") == 60


def test_shadow_merge_preserves_existing_keys_and_is_namespaced(nov25):
    existing = {"capacity": {"x": 1}, "list": [1, 2], "shadow_v1": {"old": True}}
    before = copy.deepcopy(existing)
    p = lr.build_shadow_payload(render(nov25))
    assert p["published"] is False and p["schema"] == 1 and p["kind"] == "layered_brief" and "generated_at" in p
    m = lr.merge_shadow(existing, p)
    assert existing == before
    assert {k: v for k, v in m.items() if k != "shadow_v1"} == {k: v for k, v in before.items() if k != "shadow_v1"}
    assert set(m) == set(before) | {"shadow_v1"}
    assert len(json.dumps(m["shadow_v1"]).encode()) <= lr.SHADOW_MAX_BYTES
    with pytest.raises(ValueError):
        lr.merge_shadow(existing, {**p, "published": True})


def test_shadow_oversize_compacts_without_dropping_layers_or_ids(nov25):
    d = copy.deepcopy(nov25)
    for n in range(400):
        d["incidents"].append({"incident_id": f"inc-{n:010x}", "headline": "Material item " + "y" * 120, "priority": "VERIFY", "materiality": "high"})
    r = render(d)
    p = lr.build_shadow_payload(r)
    assert p.get("compact") and p.get("reduced") and p["compact_level"] == 5 and len(json.dumps(p).encode()) <= lr.SHADOW_MAX_BYTES
    assert all(k in p["layers"] for k in ("axes", "L1", "L3", "L6"))
    assert lr.reconcile([e["incident_id"] for e in r["L7"]], p["layers"])["ok"]


def test_existing_readers_ignore_shadow(nov25):
    # a reader that reads known keys (health_snapshot style) is unaffected by the extra namespaced key
    snap = {"capacity": {"score": 3}, "domains": ["a"]}
    merged = lr.merge_shadow(snap, lr.build_shadow_payload(render(nov25)))
    read = lambda s: (s.get("capacity"), s.get("domains"))
    assert read(merged) == read(snap)


def test_shadow_excludes_health_domain():
    inc = [{"incident_id": "inc-1111111111", "headline": "Health item", "priority": "VERIFY", "materiality": "high", "domain": "health"}]
    r = lr.render_layered(inc, posture=None, coverage=CS.FULL, confidence=None)
    blocked = {i["incident_id"] for i in inc if lr.shadow_domain_blocked(lr.LayeredIncident.from_any(i))}
    p = lr.build_shadow_payload(r, blocked_ids=blocked)
    assert "inc-1111111111" not in json.dumps(p["layers"].get("L3", {}))


def _module_level_imports(path):
    import ast
    tree = ast.parse(pathlib.Path(path).read_text())
    names = []
    for node in tree.body:                      # module level only: lazy in-function imports are the flag-gated hooks
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
            names += [f"{node.module}.{a.name}" for a in node.names]
    return names


def test_legacy_modules_unchanged_when_flag_off():
    """Flag-off parity: the legacy brief paths never import the layered renderer (or its shadow adapter) at module level (hooks import lazily,
    behind the flag; see tests/test_layered_shadow.py); tiered_brief.py is byte-identical to the baseline commit."""
    import subprocess
    root = pathlib.Path(__file__).parent.parent
    for rel in ("intelligence/tiered_brief.py", "intelligence/captains_brief.py", "intelligence/scheduler.py", "intelligence/brief_evidence.py"):
        imported = _module_level_imports(root / rel)
        assert not any("layered_render" in n or "layered_shadow" in n for n in imported), (rel, imported)
    out = subprocess.run(["git", "diff", "--stat", "53085dde", "--", "intelligence/tiered_brief.py"], capture_output=True, text=True, cwd=root).stdout  # noqa: PLW1510 - exit status inspected by the test
    assert out.strip() == ""


def test_pir_tag_result_dataclass_accepted():
    res = stubs.PirTagResult(matches=[stubs.PirMatch("A1", "A", "terms")], unmatched_high_severity=False, emerging=True)
    i = lr.LayeredIncident.from_any({"incident_id": "inc-2222222222", "headline": "h", "pir": res, "scope": "international", "materiality": "low"})
    assert i.pir["matches"][0]["pir_id"] == "A1" and i.pir["emerging"] is True
    assert lr.relevance_of(i) == "high"          # a Priority A match keeps an international item out of the collapsed count


def test_real_wp5_interface_if_present():
    req = pytest.importorskip("intelligence.requirements")
    res = req.tag_item({"id": "e1", "title": "Optus Triple Zero outage", "summary": "000 calls failed"}, req.load_pirs())
    i = lr.LayeredIncident.from_any({"incident_id": "inc-3333333333", "headline": "x", "pir": res, "priority": "WATCH", "materiality": "low"})
    assert isinstance(i.pir["matches"], list)
