"""Regression tests for the independent quality review findings 1 to 5 (cases are real headlines from the 18 to 24 Nov review window).

Development evidence only: not an independent holdout."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from intelligence import requirements as rq
from intelligence.brief import layered_render as lr
from intelligence.brief import layered_shadow as ls

NOW = datetime(2026, 11, 24, 20, 1, tzinfo=timezone.utc)
PIRS = rq.load_pirs()


def view(iid, headline, *, priority="REFERENCE", materiality="medium", impact="stated", evidence="reported", geo="GLOBAL", hours_ago=3,
         rid=None, summary="", etype="outage"):
    rid = rid or iid.replace("inc-", "")
    return SimpleNamespace(incident_id=iid, headline=headline, priority=priority, materiality=materiality, event_type=etype, impact_status=impact,
                           evidence_status=evidence, independent_publishers=1, provisional=True, record={},
                           reports=[{"report_id": rid, "publisher": "p", "source_name": "p", "role": "original", "title": headline, "geography": geo, "summary": summary}],
                           last_seen=NOW - timedelta(hours=hours_ago))


# (id, headline, priority, materiality, impact, evidence): attributes as printed by the reviewer's replay of the real code path
REAL = [
    ("inc-58b17b3fc3", "Equinor says production unaffected as cyberattack disrupts IT", "REFERENCE", "medium", "stated", "unverified"),
    ("inc-b217130888", "NSA hit with system outage as US tech woes continue", "REFERENCE", "medium", "stated", "reported"),
    ("inc-33d0dd33d0", "Rubio says US not 'under systemic attack' after series of tech outages", "REFERENCE", "medium", "stated", "reported"),
    ("inc-d26907e2b4", "White House removes cyber-security chief after series of tech outages", "REFERENCE", "medium", "stated", "reported"),
    ("inc-641e28fdfb", "Federal cybersecurity gaps leave US food supply vulnerable to ransomware", "REFERENCE", "medium", "stated", "unverified"),
    ("inc-2d679c8c2e", "ClamAV Vulnerabilities Affecting Cisco Products: November 2026", "REFERENCE", "low", "none", "officially_confirmed"),
]


def render(views, cov=None, fields=None, ev_events=None):
    ev = SimpleNamespace(incidents=views, n_events=ev_events if ev_events is not None else 40, generated_at=NOW)
    cov = cov if cov is not None else {"expected": 117, "completed": 117, "collection_status": "ok", "degraded": False}
    return ls.build_from_evidence(ev, text="x", ori_brief={"coverage": cov, "generated_at": NOW.isoformat()}, pirs=PIRS, now=NOW, fields_by_event=fields)


def test_international_material_items_get_substantive_treatment_on_the_real_adapter_path():
    views = [view(i, h, priority=p, materiality=m, impact=imp, evidence=e) for i, h, p, m, imp, e in REAL]
    result, _, _ = render(views)
    full = {a["incident_id"] for a in result["L3"]["assessments"]}
    for iid, *_ in REAL:
        assert iid in full, f"{iid} collapsed"
    assert result["L3"]["counted_ids"] == []
    assert {x["ref"] for x in result["L4"] if isinstance(x["ref"], str)} >= {"inc-58b17b3fc3", "inc-b217130888"}   # L4 implications present


def test_reference_priority_does_not_collapse_before_relevance_is_considered():
    i = lr.LayeredIncident.from_any({"incident_id": "inc-x", "headline": "h", "priority": "REFERENCE", "materiality": "medium", "scope": "international"})
    assert lr.relevance_of(i) == "medium" and lr.detail_level(i) == "full"
    j = lr.LayeredIncident.from_any({"incident_id": "inc-y", "headline": "h", "priority": "REFERENCE", "materiality": "low", "scope": "international"})
    assert lr.relevance_of(j) == "unassessed" and lr.detail_level(j) == "line"     # cannot be established: surfaced, not counted
    k = lr.LayeredIncident.from_any({"incident_id": "inc-z", "headline": "h", "priority": "REFERENCE", "materiality": "low", "scope": "international", "relevance": "low"})
    assert lr.detail_level(k) == "count"


def test_unassessed_relevance_says_so_and_is_not_count_only():
    v = view("inc-2b45f105af", "Nginx servers rootable through critical flaws, unpatched Linux kernel bug", materiality="low", impact="none")
    result, _, _ = render([v])
    assert result["L3"]["counted_ids"] == []
    line = result["L3"]["one_line"][0]
    assert "relevance not assessed" in line["text"] and not line["relevance_assessed"]
    assert any("relevance could not be established" in c for c in result["L3"]["counted"])


def test_demonstrably_low_relevance_is_counted_but_listed_by_title_in_the_shadow_payload():
    v = view("inc-2b45f105af", "Nginx servers rootable through critical flaws, unpatched Linux kernel bug", materiality="low", impact="none")
    fields = {"2b45f105af": {"event_id": "2b45f105af", "event_type": "other", "risk_rating": "LOW", "customer_impact": "low",
                             "disposition": "REFERENCE", "operational_relevance": 0.1, "geography": "GLOBAL"}}
    result, items, _ = render([v], fields=fields)
    assert result["L3"]["counted_ids"] == ["inc-2b45f105af"]
    payload = lr.build_shadow_payload(result)
    titles = payload["layers"]["L3"]["counted_items"]
    assert titles[0]["headline"].startswith("Nginx servers rootable") and "low relevance" in titles[0]["reason"]
    assert payload["layers"]["L7"][0]["headline"].startswith("Nginx")
    assert items[0]["event_type"] == "other"            # stored classifier vocabulary reaches the tagger


def test_reduced_shadow_payload_keeps_counted_titles(monkeypatch):
    views = [view(f"inc-{k:010x}", f"Low relevance item number {k} " + "x" * 120, materiality="low", impact="none") for k in range(60)]
    fields = {f"{k:010x}": {"event_id": f"{k:010x}", "event_type": "other", "risk_rating": "LOW", "customer_impact": "low", "disposition": "REFERENCE", "geography": "GLOBAL"} for k in range(60)}
    result, _, _ = render(views, fields=fields)
    monkeypatch.setattr(lr, "SHADOW_MAX_BYTES", 12000)
    payload = lr.build_shadow_payload(result)
    # round 3: the stored form is COMPACT (every layer kept), not 'reduced'; counted titles survive
    assert payload.get("compact") is True and not payload.get("reduced") and "L3_counted" not in payload["layers"]
    assert payload["layers"]["L3"]["counted_total"] == 60 and payload["layers"]["L3"]["counted_items"][0]["headline"].startswith("Low relevance item")
    assert len(payload["layers"]["L3"]["counted_items"]) == 60


# ── PIR vocabulary, classifier path, match strength ───────────────────────────────────────────────────────────────
def test_pir_item_carries_stored_classifier_fields_not_the_evidence_layer_type():
    v = view("inc-aaaaaaaaaa", "Optus outage hits Victoria", etype="outage", materiality="high")
    fields = {"aaaaaaaaaa": {"event_id": "aaaaaaaaaa", "event_type": "telecom_outage", "risk_rating": "HIGH", "customer_impact": "high", "disposition": "ESCALATE",
                             "operational_relevance": 0.9, "geography": "AU", "sector": "telecommunications"}}
    item = ls.pir_item(v, ls.incident_classifier(v, fields))
    assert item["event_type"] == "telecom_outage" and item["risk_rating"] == "HIGH" and item["materiality"] == "high"
    assert item["geography"] == "AU" and item["sector"] == "telecommunications" and item["disposition"] == "ESCALATE"
    bare = ls.pir_item(v)
    assert "event_type" not in bare and "risk_rating" not in bare      # nothing is synthesised


def test_stored_event_type_vocabulary_matches_config():
    """Distinct production event_type values (SELECT, 25 Nov, 30 days) include every value the PIR config relies on."""
    stored = {"other", "cyber", "seismic_event", "regulatory", "technology_outage", "severe_weather", "workforce", "transport_disruption", "geopolitical",
              "third_party_disruption", "physical_security", "energy_disruption", "supply_chain", "payments_disruption", "telecom_outage"}
    used = {e for p in PIRS for e in p.get("event_types", [])}
    assert used and used <= stored


@pytest.mark.parametrize("title,expect", [
    ("Microsoft declares 'Code Red' after historic outage", {"A3", "B5"}),
    ("NSA hit with system outage as US tech woes continue", {"A7"}),
    ("11,000 still without power after storm cell topples transmission towers", {"A2"}),
])
def test_previously_invisible_material_items_now_match_strongly(title, expect):
    r = rq.tag_item({"title": title}, PIRS)
    assert expect <= {m.pir_id for m in r.strong_matches}


def test_weak_type_only_match_keeps_a_high_severity_item_in_the_lane():
    nvidia = {"title": "Nvidia leadership crisis highlights AI dependence", "event_type": "transport_disruption", "risk_rating": "HIGH"}
    r = rq.tag_item(nvidia, PIRS)
    assert r.matches and all(m.strength == "weak" for m in r.matches) and r.weak_only
    assert r.unmatched_high_severity is True and r.strong_matches == []
    # a corroborating term makes the same type strong and takes it out of the lane
    s = rq.tag_item({"title": "Rail network outage strands commuters", "event_type": "transport_disruption", "risk_rating": "HIGH"}, PIRS)
    assert s.strong_matches and not s.unmatched_high_severity
    # a weak match on a non-severe item does not raise the lane
    assert rq.tag_item({"title": "Quiet note", "event_type": "transport_disruption"}, PIRS).unmatched_high_severity is False


def test_materiality_high_counts_as_high_severity_and_posture_goes_amber():
    r = rq.tag_item({"title": "Something odd happened", "materiality": "high"}, PIRS)
    assert r.unmatched_high_severity
    v = view("inc-bbbbbbbbbb", "Something odd happened", priority="WATCH", materiality="high")
    result, _, _ = render([v])
    # round 3: the lane is a review list and does not by itself drive AMBER; the item is listed and fully assessed (materiality high)
    assert result["axes"]["posture"]["value"] == "GREEN" and result["L5"]["watch"]
    assert [a["incident_id"] for a in result["L3"]["assessments"]] == ["inc-bbbbbbbbbb"]


# ── nothing omitted without being counted and listed ─────────────────────────────────────────────────────────────
def test_older_than_window_incidents_are_counted_with_titles_not_dropped():
    old = [view("inc-0000000001", "Nginx servers rootable through critical flaws", materiality="low", impact="none", hours_ago=40),
           view("inc-0000000002", "AI-Fueled Cyberattacks Drive Claims Surge at Japan Insurers", priority="WATCH", materiality="low", hours_ago=50)]
    fresh = [view("inc-0000000003", "Fresh item", priority="WATCH", materiality="medium", hours_ago=2)]
    fields = {"0000000001": {"event_id": "0000000001", "event_type": "other", "risk_rating": "LOW", "customer_impact": "low", "disposition": "REFERENCE", "geography": "GLOBAL"}}
    result, _, meta = render(old + fresh, fields=fields)
    assert meta["incidents_total"] == 3 and meta["incidents_older_than_window"] == 2 and meta["unaccounted"] == 0
    ids = {e["incident_id"] for e in result["L7"]}
    assert ids == {"inc-0000000001", "inc-0000000002", "inc-0000000003"}
    # round 3: only the DEMONSTRABLY low one (classifier fields) is counted by age; the unassessed one stays a titled line
    assert {x["incident_id"] for x in result["L3"]["counted_items"]} == {"inc-0000000001"}
    assert "inc-0000000002" in {x["incident_id"] for x in result["L3"]["one_line"]}
    assert any("older than the brief window" in c for c in result["L3"]["counted"])


def test_old_but_material_incident_is_one_line_not_counted():
    result, _, _ = render([view("inc-0000000009", "Big old outage", priority="VERIFY", materiality="high", hours_ago=40)])
    assert result["L3"]["one_line"] and "older than the brief window" in result["L3"]["one_line"][0]["text"]


def test_health_exclusions_are_counted_in_meta_never_listed():
    h = view("inc-hhhhhhhhhh", "Measles cases rise", etype="health", priority="WATCH")
    result, _, meta = render([h, view("inc-0000000003", "Fresh", priority="WATCH", materiality="medium")])
    assert meta["excluded_health_domain"] == 1 and meta["unaccounted"] == 0
    assert "Measles" not in json.dumps(result)


# ── posture / coverage ───────────────────────────────────────────────────────────────────────────────────────────
def test_unknown_is_reachable_on_the_real_adapter_when_collection_is_impaired_and_evidence_thin():
    cov = {"expected": 113, "completed": 80, "failed": 33, "degraded": True, "collection_status": "ok",
           "missing_sources": ["Source A", "Source B"], "critical_sources_failed": ["Source A"]}
    thin = [view("inc-0000000003", "One watch item", priority="WATCH", materiality="low")]
    result, _, _ = render(thin, cov=cov)
    assert result["axes"]["coverage"]["value"] == "DEGRADED" and result["axes"]["posture"]["value"] == "UNKNOWN"
    assert "NOT ASSESSED" in result["L1"]["text"] and "all-clear" not in result["L1"]["text"].lower().replace("not an all-clear", "")


def test_degraded_with_enough_relevant_events_can_be_green_but_names_the_limit():
    cov = {"expected": 113, "completed": 80, "degraded": True, "missing_sources": ["Source A"], "collection_status": "ok"}
    many = [view(f"inc-00000000{k:02d}", f"Watch item {k}", priority="WATCH", materiality="low") for k in range(4)]
    result, _, _ = render(many, cov=cov)
    # round 3: 80/113 is impaired collection: with no RED/AMBER evidence the posture is NOT ASSESSED whatever the item count
    assert result["axes"]["posture"]["value"] == "UNKNOWN" and "collection impaired" in result["axes"]["posture"]["not_assessed_triggers"][0]
    assert "Source A" in result["L1"]["text"] and "all-clear" not in result["L1"]["text"].lower().replace("not an all-clear", "")


def test_green_under_partial_coverage_with_chronic_missing_sources_names_them():
    """The real 23 Nov shape: degraded flag over 109/113 completed. Coverage grades PARTIAL, the four sources stay named."""
    cov = {"expected": 113, "completed": 109, "failed": 4, "stale": 3, "degraded": True, "collection_status": "ok",
           "missing_sources": ["OAIC Breach Notifications", "ASD Publications"]}
    result, _, _ = render([view("inc-0000000003", "Watch", priority="WATCH", materiality="medium")], cov=cov)
    assert result["axes"]["coverage"]["value"] == "PARTIAL"
    assert result["axes"]["posture"]["value"] in ("GREEN", "UNKNOWN")
    if result["axes"]["posture"]["value"] == "GREEN":
        assert "assessment limited by" in result["L1"]["text"] and "OAIC Breach Notifications" in result["L1"]["text"]


def test_axes_stay_separate():
    cov = {"expected": 10, "completed": 2, "degraded": True}
    r = lr.render_layered([], posture=lr.OperationalPosture.RED, coverage=cov, confidence=None)
    assert r["axes"]["posture"]["value"] == "RED" and r["axes"]["coverage"]["value"] == "DEGRADED"   # coverage never rewrites a supplied posture


# ── shadow nesting parity ────────────────────────────────────────────────────────────────────────────────────────
def test_layered_merge_never_overwrites_another_producers_shadow():
    other = {"keep": 1, "shadow_v1": {"schema": 1, "published": False, "kind": "pir_tagging", "items": 3}}
    payload = {"schema": 1, "published": False, "kind": "layered_brief", "layers": {}}
    out = lr.merge_shadow(other, payload)
    assert out["shadow_v1"]["kind"] == "pir_tagging" and out["shadow_v1"]["items"] == 3
    assert out["shadow_v1"]["companions"]["layered_brief"] == payload and out["keep"] == 1
    assert other["shadow_v1"].get("companions") is None                  # input untouched
    again = lr.merge_shadow(out, dict(payload, generated_at="t2"))        # same-kind replace inside companions keeps the owner
    assert again["shadow_v1"]["kind"] == "pir_tagging" and again["shadow_v1"]["companions"]["layered_brief"]["generated_at"] == "t2"


def test_attach_shadow_with_foreign_pir_shadow_present_keeps_both():
    existing = {"a": 1, "shadow_v1": {"schema": 1, "published": False, "kind": "pir_tagging", "items": 3}}
    result, items, meta = render([view("inc-0000000003", "Watch", priority="WATCH", materiality="medium")])
    out = ls.attach_shadow(existing, result, pir_items=items, meta=meta, pirs=PIRS, now=NOW, env={"PIR_TAGGING_SHADOW_V1": "1"})
    sh = out["shadow_v1"]
    assert sh["kind"] == "pir_tagging" and "layered_brief" in sh["companions"] and out["a"] == 1


def test_classifier_loader_fails_soft_and_chunks():
    calls = []
    def sb(table, q):
        calls.append(q)
        return [{"event_id": "e1", "event_type": "telecom_outage"}]
    out = ls.load_classifier_fields(sb, [f"e{k}" for k in range(200)] + [None])
    assert len(calls) == 3 and out["e1"]["event_type"] == "telecom_outage"
    def boom(table, q):
        raise RuntimeError("down")
    assert ls.load_classifier_fields(boom, ["e1"]) == {}
