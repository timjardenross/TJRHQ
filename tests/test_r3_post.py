"""Round-3 fixes (posture, layered renderer, coverage criticality, measurement integrity). Cases come from the independent re-review
(rereview-quality N1-N11). Evidence class: development; nothing here is independent evidence."""
from __future__ import annotations

import copy
import json
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from intelligence import coverage_criticality as cc
from intelligence import requirements as req
from intelligence.brief import layered_render as lr
from intelligence.brief import layered_shadow as ls

CS = lr.CoverageStatus
P = lr.OperationalPosture
NOW = datetime(2026, 11, 18, 20, 1, tzinfo=timezone.utc)
FIX = Path(__file__).parent / "fixtures" / "coverage"
M4 = ["OAIC Breach Notifications", "ASD Publications", "Daily Operational Resilience Briefs (GitHub)", "OAIC Privacy Determinations & News"]


def inc(n, headline="Item", **kw):
    d = {"incident_id": f"inc-{n:010x}", "headline": headline, "priority": "WATCH", "materiality": "low", "last_seen": NOW.isoformat()}
    d.update(kw)
    return d


def pir(*, lane=False, strong=(), weak=(), emerging=False):
    ms = [{"pir_id": p, "priority": p[0], "basis": "term:x", "strength": "strong"} for p in strong] + [{"pir_id": p, "priority": p[0], "basis": "event_type:x", "strength": "weak"} for p in weak]
    return {"matches": ms, "unmatched_high_severity": lane and not strong, "watch_lane": lane, "high_severity": lane, "emerging": emerging}


def posture(incs, coverage=CS.FULL, **kw):
    r = lr.render_layered(incs, posture=None, coverage=coverage, confidence=None, **kw)
    return r, r["axes"]["posture"]["value"]


# ------------------------------------------------------------------------------------------------------------- N2 / N7 posture
def m365(**over):
    """The 19 Nov false RED: ESCALATE, impact stated, 2 publishers, restored 13 Nov, last seen 16 Nov (out of window)."""
    d = inc(1, "Microsoft says three-month-old bug behind global M365 outage", priority="ESCALATE", materiality="high", impact_status="stated",
            evidence_status="corroborated", independent_publishers=2, provisional=False, state="restored", outside_window=True,
            last_seen=(NOW - timedelta(days=2)).isoformat())
    d.update(over)
    return d


def test_restored_out_of_window_escalate_item_is_not_a_red_driver():
    _, p = posture([m365()])
    assert p == "GREEN"
    _r, p = posture([m365(outside_window=False, state="restored", impact_status="stated")])      # in window but restored
    assert p == "GREEN"
    _, p = posture([m365(outside_window=False, state="", impact_status="retrospective")])        # in window but retrospective
    assert p == "GREEN"
    _, p = posture([m365(outside_window=False, state="", impact_status="stated", priority="REFERENCE")])   # REFERENCE-only
    assert p == "GREEN"


def test_current_confirmed_escalate_is_red_and_current_provisional_escalate_is_amber():
    _, p = posture([m365(outside_window=False, state="ongoing", impact_status="stated")])
    assert p == "RED"
    _, p = posture([m365(outside_window=False, state="ongoing", provisional=True, evidence_status="reported", independent_publishers=1)])
    assert p == "AMBER"


def test_watch_lane_alone_never_sets_amber_and_is_listed_for_review():
    lane = [inc(n, f"Classifier-flagged item {n}", pir=pir(lane=True)) for n in range(60)]
    r, p = posture(lane)
    assert p == "GREEN" and len(r["L5"]["watch"]) == 60
    assert r["axes"]["posture"]["watch_lane_total"] == 60 and r["axes"]["posture"]["watch_not_driving"] == 60
    assert "review/watch list" in r["L1"]["text"]


def test_justified_severity_recency_rule_makes_a_lane_item_a_driver():
    sev = {"pir": pir(lane=True), "severity": "high", "evidence_status": "corroborated", "independent_publishers": 2}
    r, p = posture([inc(1, "Severe corroborated current item", **sev)])
    assert p == "AMBER" and "classifier severity high" in r["axes"]["posture"]["reasons"][0]
    for bad in ({"outside_window": True}, {"impact_status": "retrospective"}, {"state": "restored"}, {"priority": "REFERENCE"},
                {"evidence_status": "reported", "independent_publishers": 1}, {"severity": ""}):
        _, p = posture([inc(1, "x", **{**sev, **bad})])
        assert p == "GREEN", bad


def test_emerging_language_alone_never_sets_amber():
    _, p = posture([inc(1, "Known exploited vulnerability added", materiality="high", evidence_status="officially_confirmed", pir=pir(emerging=True))])
    assert p == "GREEN"


def test_precedence_documented_and_red_amber_win_over_unknown_with_limits_stated():
    r, p = posture([inc(1, "Current outage", priority="ESCALATE", materiality="high", impact_status="stated", provisional=True)],
                   coverage={"expected": 113, "completed": 60, "failed": 53, "missing_sources": ["A"]})
    assert p == "AMBER"
    ax = r["axes"]["posture"]
    assert ax["not_assessed_triggers"] and "collection impaired" in ax["not_assessed_triggers"][0] and "RED > AMBER" in ax["precedence"]
    assert "Assessment limits beside this posture" in r["L1"]["text"]
    assert any("would make the posture NOT ASSESSED" in x for x in r["L6"]["limits"])


@pytest.mark.parametrize("completed, expected_posture", [(91, "GREEN"), (90, "UNKNOWN"), (85, "UNKNOWN"), (80, "UNKNOWN"), (60, "UNKNOWN"), (40, "UNKNOWN"), (0, "UNKNOWN")])
def test_unknown_when_collection_impaired_and_no_red_amber_whatever_the_item_count(completed, expected_posture):
    many = [inc(n, f"Verify item {n}", priority="VERIFY", materiality="medium") for n in range(25)]       # 25 judged items: the count is irrelevant
    cov = {"expected": 113, "completed": completed, "failed": 113 - completed, "missing_sources": ["X"], "degraded": True}
    _, p = posture(many, coverage=cov)
    assert p == expected_posture


def test_unknown_not_produced_by_a_partial_run_at_109_of_113():
    _, p = posture([inc(1, "Verify item", priority="VERIFY", materiality="medium")], coverage={"expected": 113, "completed": 109, "failed": 4, "missing_sources": M4, "degraded": True})
    assert p == "GREEN"          # PARTIAL is the accepted grade; GREEN is rendered with its named limits
    r, _ = posture([], coverage={"expected": 113, "completed": 109, "failed": 4, "missing_sources": M4, "degraded": True}, n_events=5)
    assert "assessment limited by" in r["L1"]["text"]


def snapshot_registry():
    snap = json.loads((FIX / "source_registry_snapshot.json").read_text())
    return [{"source_name": n, "active": True} for n in snap["active"]] + [{"source_name": n, "active": False} for n in snap["inactive"]]


def test_critical_source_loss_makes_unknown_regardless_of_aggregate_completion_and_item_count():
    items = [inc(n, f"Verify {n}", priority="VERIFY", materiality="medium") for n in range(30)]
    cov = {"expected": 113, "completed": 112, "failed": 1, "missing_sources": ["AEMO Market Notices"], "degraded": True}     # 99% complete
    c = cc.evaluate(cov, registry=snapshot_registry())
    assert c["critical_sources_failed"] == ["AEMO Market Notices"] and c["posture_unknown_reasons"]
    r, p = posture(items, coverage=cov, criticality=c)
    assert p == "UNKNOWN" and any("AEMO" in t for t in r["axes"]["posture"]["not_assessed_triggers"])
    _, p0 = posture(items, coverage=cov)                                  # without the producer the same data reads GREEN: the producer is the cause
    assert p0 == "GREEN"


def test_critical_source_not_collected_is_critical_missing():
    reg = [r for r in snapshot_registry() if r["source_name"] != "AEMO Market Notices"]
    c = cc.evaluate({"expected": 5, "completed": 5, "failed": 0, "missing_sources": []}, registry=reg)
    assert c["critical_missing"] == ["AEMO Market Notices"] and c["posture_unknown_reasons"]


def test_authoritative_evidence_unavailable_makes_unknown():
    cov = {"expected": 113, "completed": 110, "failed": 3, "missing_sources": ["CISA Alerts", "CISA Known Exploited Vulnerabilities", "NCSC UK Advisories"], "degraded": True}
    c = cc.evaluate(cov, registry=snapshot_registry())
    # two of the three failing feeds do not exhaust the roles that need a cyber authority: NCSC UK Threat Reports still serves A7
    assert not any(a["pir"] == "A7" for a in c["authoritative_unavailable"])
    cov["missing_sources"] = cov["missing_sources"] + ["NCSC UK Threat Reports"]
    c = cc.evaluate(cov, registry=snapshot_registry())
    assert any(a["pir"] == "A7" and a["role"] == "international cyber authority" for a in c["authoritative_unavailable"])
    _, p = posture([inc(n, f"v{n}", priority="VERIFY", materiality="medium") for n in range(12)], coverage=cov, criticality=c)
    assert p == "UNKNOWN"


def test_material_pir_coverage_gap_makes_unknown():
    names = ["Cloudflare Status", "Microsoft Azure Status", "AWS Service Health", "AWS Sydney (ap-southeast-2)", "Google Cloud Status"]
    cov = {"expected": 113, "completed": 108, "failed": 5, "missing_sources": names[:4], "degraded": True}
    c = cc.evaluate(cov, registry=snapshot_registry())
    # one cloud status feed remains (the role is met) but A3 needs 2 healthy serving sources and the supporting probes are not enough
    assert any(g["pir"] == "A3" for g in c["pir_coverage_gaps"]) or not any(a["pir"] == "A3" for a in c["authoritative_unavailable"])
    cov["missing_sources"] = names + ["Cloudflare Status (Uptime Kuma direct probe)", "AWS Status (Uptime Kuma direct probe)"]
    c = cc.evaluate(cov, registry=snapshot_registry())
    gap = next(g for g in c["pir_coverage_gaps"] if g["pir"] == "A3")
    assert gap["healthy"] == 0 and gap["required"] == 2 and "A3" in gap["consequence"]
    _, p = posture([], coverage=cov, criticality=c, n_events=40)
    assert p == "UNKNOWN"


def test_external_domain_failure_marks_the_emergency_hub_critical():
    cov = {"expected": 115, "completed": 114, "failed": 1, "missing_sources": ["Emergency Alert Hub"], "domains": {"emergency": {"available": False, "error": "timeout"}}}
    c = cc.evaluate(cov, registry=snapshot_registry())
    assert "Emergency Alert Hub" in c["critical_sources_failed"] and any(a["pir"] == "A8" for a in c["authoritative_unavailable"])


def test_priority_b_loss_is_a_named_limit_not_a_posture_trigger():
    cov = {"expected": 113, "completed": 109, "failed": 4, "missing_sources": M4}
    c = cc.evaluate(cov, registry=snapshot_registry())
    assert any(a["pir"] == "B3" and a["role"] == "privacy regulator" for a in c["authoritative_unavailable"])
    assert c["posture_unknown_reasons"] == []
    r, p = posture([inc(1, "x", priority="VERIFY", materiality="medium")], coverage=cov, criticality=c)
    assert p == "GREEN" and any("B3" in x for x in r["axes"]["coverage"]["limits"])


def test_truncated_failed_source_list_cannot_exclude_a_critical_loss():
    cov = {"expected": 113, "completed": 100, "failed": 13, "missing_sources": [f"S{n}" for n in range(10)]}
    c = cc.evaluate(cov, registry=snapshot_registry())
    assert c["failed_names_complete"] is False and any("cannot be excluded" in x for x in c["posture_unknown_reasons"])


def test_healthy_run_has_no_triggers_and_declared_gaps_are_not_triggers():
    c = cc.evaluate({"expected": 113, "completed": 113, "failed": 0, "missing_sources": []}, registry=snapshot_registry())
    assert c["posture_unknown_reasons"] == [] and not c["pir_coverage_gaps"] and not c["authoritative_unavailable"]
    assert {g["pir"] for g in c["declared_gaps"]} >= {"A1", "A4"}


# --------------------------------------------------------------------------------------------- criticality config integrity
def test_service_config_names_exist_in_the_registry_snapshot_and_derive_only_from_pir_service():
    cfg = json.loads((Path(req.DEFAULT_PATH)).read_text())
    snap = json.loads((FIX / "source_registry_snapshot.json").read_text())
    known = set(snap["active"]) | set(snap["inactive"]) | set(snap["external_domains"])
    for p in cfg["pirs"]:
        s = p["service"]
        names = [n for r in s["roles"] for n in r["any_of"]] + s["supporting"] + s["critical"]
        assert set(names) <= known, (p["id"], set(names) - known)
        assert set(s["critical"]) <= set(names)
    blob = json.dumps({"service_policy": cfg["service_policy"], "svc": [p["service"] for p in cfg["pirs"]]}).lower()
    for estate in ("supabase", "vercel", "anthropic", "claude", "telegram", "ollama", "coolify", "infisical", "tjrhq", "starship", "lcars", "twilio", "resend"):
        assert estate not in blob, estate
    assert cfg["service_policy"]["owner"] == "PDB"


def test_producer_flag_default_off_and_flag_off_build_is_unchanged(monkeypatch):
    monkeypatch.delenv(cc.FLAG, raising=False)
    assert cc.enabled() is False
    ev = SimpleNamespace(incidents=[], n_events=3, generated_at=NOW)
    ori = {"coverage": {"expected": 113, "completed": 112, "failed": 1, "missing_sources": ["AEMO Market Notices"]}, "events_evaluated": 5, "generated_at": NOW.isoformat()}
    r_off, _, meta_off = ls.build_from_evidence(ev, text="t", ori_brief=ori, now=NOW)
    assert meta_off["criticality"] is None
    r_on, _, meta_on = ls.build_from_evidence(ev, text="t", ori_brief=ori, now=NOW, registry=snapshot_registry(), criticality_enabled=True)
    assert meta_on["criticality"]["critical_sources_failed"] == ["AEMO Market Notices"]
    assert r_off["axes"]["posture"]["value"] == "GREEN"
    assert r_on["axes"]["posture"]["value"] == "UNKNOWN"


# ------------------------------------------------------------------------------------------------------------------ N3 ordering
def test_l1_leads_with_the_driver_and_order_is_deterministic_not_hash_ordered():
    base = [inc(n, f"Equal item {n:02d}", priority="VERIFY", materiality="medium", last_seen=(NOW - timedelta(hours=n)).isoformat()) for n in range(1, 9)]
    drv = inc(99, "Driver outage", priority="ESCALATE", materiality="high", impact_status="stated", provisional=True)
    orders = set()
    for seed in range(8):
        pool = copy.deepcopy(base) + [copy.deepcopy(drv)]
        random.Random(seed).shuffle(pool)
        for k, d in enumerate(pool):                       # scramble ids so any id/hash tie-break would show
            d["incident_id"] = f"inc-{random.Random(seed * 100 + k).getrandbits(40):010x}"
        r, p = posture(pool)
        assert p == "AMBER"
        orders.add(tuple(a["headline"] for a in r["L3"]["assessments"]))
        assert r["L3"]["assessments"][0]["headline"] == "Driver outage" and "Driver outage" in r["L1"]["text"].split("Decision-first:")[1][:40]
    assert len(orders) == 1                                # same order whatever the input order and ids
    assert [h for h in next(iter(orders))][1:4] == ["Equal item 01", "Equal item 02", "Equal item 03"]      # then newest first


def test_decision_order_prefers_strong_a_match_then_corroboration_then_recency():
    a = inc(1, "A strong", priority="WATCH", pir=pir(strong=("A2",)), materiality="medium", independent_publishers=1)
    b = inc(2, "Corroborated", priority="WATCH", materiality="medium", evidence_status="corroborated")
    c = inc(3, "Plain", priority="WATCH", materiality="medium")
    order = [i.headline for i in sorted([lr.LayeredIncident.from_any(x) for x in (c, b, a)], key=lr.decision_key)]
    assert order == ["A strong", "Corroborated", "Plain"]


# ---------------------------------------------------------------------------------------------------------------- N4 / N5 / N6
def test_medium_relevance_never_collapses_by_age_only_demonstrably_low_does():
    med = lr.LayeredIncident.from_any(inc(1, "Equinor cyberattack", relevance="medium", relevance_basis="B4", outside_window=True, scope="international"))
    hi = lr.LayeredIncident.from_any(inc(2, "Food-supply ransomware", relevance="high", outside_window=True, scope="international"))
    low = lr.LayeredIncident.from_any(inc(3, "Golf result", relevance="low", relevance_basis="classifier LOW", outside_window=True, scope="international"))
    un = lr.LayeredIncident.from_any(inc(4, "Unassessed", outside_window=True))
    assert [lr.detail_level(x) for x in (med, hi, low, un)] == ["line", "line", "count", "line"]
    r = lr.render_layered([med, hi, low, un], posture=None, coverage=CS.FULL, confidence=None)
    assert {x["incident_id"] for x in r["L3"]["one_line"]} == {med.incident_id, hi.incident_id, un.incident_id}
    assert r["L3"]["counted_total"] == 1 and r["L3"]["counted_items"][0]["headline"] == "Golf result"


def test_wrongly_strong_pir_match_does_not_remove_a_high_severity_item_from_review():
    pirs = req.load_pirs()
    item = {"id": "p", "title": "Pilots strike grounds flights; blackout period ends for Fed officials", "risk_rating": "HIGH", "disposition": "ESCALATE",
            "customer_impact": "high"}
    t = req.tag_item(item, pirs)
    assert t.strong_matches and t.unmatched_high_severity is False          # the re-review's N6 case: strongly (wrongly) matched
    assert t.watch_lane is True and t.high_severity is True                 # lane membership is independent of match strength
    i = lr.LayeredIncident.from_any(inc(1, item["title"], pir=t, priority="WATCH"))
    r = lr.render_layered([i], posture=None, coverage=CS.FULL, confidence=None)
    w = r["L5"]["watch"][0]
    assert w["incident_id"] == i.incident_id and w["pir_tags"] and "annotates" in w["text"]
    low = req.tag_item({"id": "q", "title": "Quiet note", "risk_rating": "LOW"}, pirs)
    assert low.watch_lane is False


def test_lane_item_is_visible_even_when_low_relevance_and_outside_window():
    i = lr.LayeredIncident.from_any(inc(1, "Severe thing", relevance="low", relevance_basis="x", outside_window=True, pir=pir(lane=True)))
    assert lr.detail_level(i) == "line"


# ------------------------------------------------------------------------------------------------------------ N1 / N8 stored shadow
def big_day(n=120, full=20):
    incs = []
    for k in range(n):
        kind = {"priority": "VERIFY", "materiality": "medium"} if k < full else {"priority": "WATCH", "outside_window": (k % 3 == 0)}
        incs.append(inc(k + 1, f"Headline number {k} " + "word " * 12, **kind, pir=pir(lane=(k % 2 == 0))))
    return incs


def test_stored_payload_keeps_every_layer_and_every_incident_within_the_bound():
    incs = big_day(150, 30)
    r = lr.render_layered(incs, posture=None, coverage={"expected": 113, "completed": 109, "failed": 4, "missing_sources": M4}, confidence=None,
                          judgements=[{"statement": "A judgement", "evidence": [incs[0]["incident_id"]]}], outlook=["Forward note"])
    meta = {"x": 1}
    p = lr.build_shadow_payload(r, meta=meta)
    assert len(json.dumps(p).encode()) + lr.STORED_RECON_HEADROOM <= lr.SHADOW_MAX_BYTES
    assert p.get("compact") and p["compact_level"] in (1, 2, 3, 4) and not p.get("reduced")
    layers = p["layers"]
    for k in ("axes", "L1", "L2", "L3", "L5", "L6", "L7"):
        assert k in layers, k
    stored = lr.reconcile([i["incident_id"] for i in incs], layers)
    assert stored["ok"] and stored["missing_from_l3"] == [] and stored["input_total"] == 150
    assert stored["counted_titles_not_shown"] == 0 or p["compact_level"] == 4     # titles survive until the last step
    assert layers["L3"]["assessments"][0]["headline"]
    txt = lr.audio_script(layers)["script"]                                      # existing readers work on the compact form
    assert "Posture" in txt or "assessed" in txt.lower()


def test_very_large_day_falls_back_to_ids_and_is_flagged_reduced_never_silently_dropped():
    incs = big_day(420, 60)
    r = lr.render_layered(incs, posture=None, coverage=CS.FULL, confidence=None)
    p = lr.build_shadow_payload(r, meta={"x": 1})
    assert p["compact_level"] == 5 and p["reduced"] is True
    assert lr.reconcile([i["incident_id"] for i in incs], p["layers"])["ok"]
    assert p["layers"]["L3"]["titles_not_stored"] > 0 and "L1" in p["layers"] and "L6" in p["layers"]


def test_reconciliation_is_real_it_detects_a_lost_incident_in_rendered_and_stored_layers():
    incs = big_day(30, 10)
    r = lr.render_layered(incs, posture=None, coverage=CS.FULL, confidence=None)
    ids = [i["incident_id"] for i in incs]
    assert lr.reconcile(ids, r)["ok"]
    broken = copy.deepcopy(r)
    gone = broken["L3"]["one_line"].pop()["incident_id"]
    rec = lr.reconcile(ids, broken)
    assert rec["ok"] is False and gone in rec["missing_from_l3"]
    dup = copy.deepcopy(r)
    dup["L3"]["one_line"].append(dup["L3"]["assessments"][0])
    assert lr.reconcile(ids, dup)["duplicated"]
    assert lr.reconcile(ids + ["inc-ffffffffff"], r)["missing_from_l3"] == ["inc-ffffffffff"]


def test_meta_unaccounted_in_the_adapter_comes_from_the_rendered_output(monkeypatch):
    v = SimpleNamespace(incident_id="inc-aaaaaaaaaa", headline="Outage", priority="WATCH", materiality="medium", event_type="outage", impact_status="stated",
                        evidence_status="reported", independent_publishers=1, provisional=True, reports=[{"report_id": "e1", "role": "original", "title": "Outage", "geography": "AU"}],
                        record={}, last_seen=NOW)
    ev = SimpleNamespace(incidents=[v], n_events=1, generated_at=NOW)
    ori = {"coverage": {"expected": 3, "completed": 3}, "events_evaluated": 1, "generated_at": NOW.isoformat()}
    _, _, meta = ls.build_from_evidence(ev, text="t", ori_brief=ori, now=NOW)
    assert meta["unaccounted"] == 0 and meta["reconciliation"]["ok"]
    real = lr._l3
    monkeypatch.setattr(lr, "_l3", lambda incs: (lambda x: x and {**x, "assessments": [], "one_line": []})(real(incs)))      # a renderer defect that loses the item  # noqa: PLC3002 - immediately-invoked lambda kept for locality
    _, _, meta = ls.build_from_evidence(ev, text="t", ori_brief=ori, now=NOW)
    assert meta["unaccounted"] == 1 and meta["reconciliation"]["ok"] is False


def test_attach_shadow_records_stored_reconciliation_against_the_stored_layers():
    ev = SimpleNamespace(incidents=[], n_events=0, generated_at=NOW)
    r, items, meta = ls.build_from_evidence(ev, text="t", ori_brief={"coverage": {"expected": 3, "completed": 3}, "generated_at": NOW.isoformat()}, now=NOW)
    out = ls.attach_shadow({"k": 1}, r, pir_items=items, meta=meta, now=NOW)
    assert out["k"] == 1 and out["shadow_v1"]["meta"]["reconciliation_stored"]["ok"] is True


# ------------------------------------------------------------------------------------------------------------ N9 ORI age guard
def test_ori_age_guard_applies_without_brief_status_flag(monkeypatch):
    monkeypatch.delenv("BRIEF_STATUS_V1", raising=False)
    ev = SimpleNamespace(incidents=[], n_events=50, generated_at=NOW)
    old = {"coverage": {"expected": 113, "completed": 113, "failed": 0, "missing_sources": []}, "events_evaluated": 50, "generated_at": (NOW - timedelta(days=3)).isoformat()}
    r, _, _meta = ls.build_from_evidence(ev, text="t", ori_brief=old, now=NOW)
    assert r["axes"]["coverage"]["value"] == "DEGRADED" and any("old" in x for x in r["axes"]["coverage"]["limits"])
    assert r["axes"]["posture"]["value"] == "UNKNOWN"
    fresh = {**old, "generated_at": (NOW - timedelta(hours=1)).isoformat()}
    r2, _, _ = ls.build_from_evidence(ev, text="t", ori_brief=fresh, now=NOW)
    assert r2["axes"]["coverage"]["value"] == "FULL"
    assert ls.ori_guard(None) is None
    assert ls.ori_guard(ls.ori_guard(old, NOW), NOW) == ls.ori_guard(old, NOW)       # idempotent


# ------------------------------------------------------------------------------------------------------------- measurement tools
def test_funnel_daily_has_definitions_no_rates_and_select_only_sql():
    from tools.intelligence import effectiveness_measures as em
    q = em.build_queries(funnel_days=7)["funnel_daily"]
    assert re.match(r"\s*with\b", q) and not re.search(r"\b(insert|update|delete|drop|alter|create|truncate|grant)\b\s", re.sub(r"'[^']*'", "''", q), re.IGNORECASE)
    rows = [{"day": "2026-11-24", "sources": 116, "items": 2059, "events": 1144, "suppressed": 478, "relevant": 43, "briefed_ori": 1, "briefed_disp": 59}]
    f = em.compute_funnel_daily(rows)
    d = f["days"][0]
    assert d["new_events"] == 1144 and d["briefed_ori_brief_id"] == 1 and d["briefed_classifier_disposition"] == 59
    assert "briefed_ori_brief_id" in f["definitions"] and "no stage is a conversion" in f["definitions"]["reading_note"].lower()
    md = em.render_markdown(em.compute_all({"funnel_daily": rows}))
    assert "Funnel by day" in md and "not conversions" in md
    assert not re.search(r"\d+(\.\d+)?\s*%\s*\(?same unit|conversion rate of|pct_", md) and "%" not in md.split("## Funnel (one sweep")[0].split("## Funnel by day")[1]
    assert em.compute_funnel_daily(None)["status"] == em.NOT_MEASURED


def test_lane_only_item_is_a_review_line_unless_stored_severity_is_high():
    plain = lr.LayeredIncident.from_any(inc(1, "Classifier-flagged", pir=pir(lane=True), relevance="medium"))
    sev = lr.LayeredIncident.from_any(inc(2, "Severe by classifier", pir=pir(lane=True), relevance="medium", severity="high", scope="international"))
    assert (lr.detail_level(plain), lr.detail_level(sev)) == ("line", "full")
