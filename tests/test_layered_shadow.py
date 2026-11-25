"""BRIEF_LAYERED_V1 shadow wiring (integration of WP4 renderer with WP2 status, WP3 claim-gate record, WP5 PIR tagging).
No network, no sends, no production writes: the store, Telegram and evidence loader are fakes."""
from __future__ import annotations

import copy
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tests" / "fixtures" / "layered"))

from intelligence import brief_evidence as be
from intelligence import captains_brief as cb
from intelligence import claim_gate
from intelligence import production_status as ps
from intelligence import requirements as req
from intelligence.brief import layered_render as lr
from intelligence.brief import layered_shadow as ls
from tools.intelligence.alert_replay import load_events

FIXTURE = _REPO / "tests/fixtures/incident_clustering/events_30d_sample.tsv"
NOW = datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)
_REAL_BUILD = be.build_evidence
NOV25 = json.loads((_REPO / "tests/fixtures/layered/morning_2026-11-25.json").read_text())
# stored ORI coverage records (production SELECT, 25 Nov 2026): brief generated for 25 Nov (full) and for 24 Nov (4 failed sources, no narrative)
COV_FULL = {"stale": 0, "failed": 0, "reason": None, "degraded": False, "expected": 117, "completed": 117, "cutoff_reached": False,
            "missing_sources": [], "collection_status": "ok"}
COV_DEGRADED = {"stale": 3, "failed": 4, "reason": None, "degraded": True, "expected": 113, "completed": 80, "cutoff_reached": False,
                "missing_sources": ["OAIC Breach Notifications", "ASD Publications", "Daily Operational Resilience Briefs (GitHub)",
                                    "OAIC Privacy Determinations & News"], "collection_status": "ok"}
TEXT = "MORNING BRIEF. " + "An Optus network fault disrupted services across Victoria and the operator has not confirmed a cause. " * 3


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    for f in (lr.FLAG, ls.AUDIO_FLAG, req.FLAG_NAME, ps.FLAG, claim_gate.FLAG_NAME):
        monkeypatch.delenv(f, raising=False)

    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)


@pytest.fixture(scope="module")
def events():
    return [e for e in load_events(FIXTURE) if e["collected_at"] <= "2026-11-13T21:00:00+00:00"]


@pytest.fixture(scope="module")
def evidence(events):
    return be.build_evidence(events, now=NOW, window_hours=72)


def _ori(cov, **extra):
    return {"coverage": copy.deepcopy(cov), "generated_at": NOW.isoformat(), **extra}


# ── adapter: real interfaces ─────────────────────────────────────────────────────────────────────────────────────
def test_incident_input_uses_real_wp5_tagging_and_maps_view(evidence):
    pirs = req.load_pirs()
    assert evidence.incidents
    for v in evidence.incidents:
        d = ls.incident_input(v, pirs)
        assert isinstance(d["pir"], req.PirTagResult)
        assert d["incident_id"] == v.incident_id and d["priority"] == v.priority and d["materiality"] == v.materiality
        assert d["scope"] in ("domestic", "international", "unknown")
        lr.LayeredIncident.from_any(d)                      # the renderer accepts every adapted incident


def test_scope_and_state_mapping():
    assert ls.scope_of([{"geography": "AU"}, {"geography": "GLOBAL"}]) == "domestic"
    assert ls.scope_of([{"geography": "GLOBAL"}]) == "international" and ls.scope_of([{"geography": ""}]) == "unknown"
    v = {"incident_id": "inc-1", "headline": "h", "reports": [], "record": {"restoration_status": "partially_restored"}}
    assert ls.incident_input(v, [])["state"] == "partially restored"


def test_status_is_real_wp2_result_with_real_wp3_gate_and_no_delivery_input():
    failing = {"passed": False, "mode": "shadow", "claims_total": 4, "claims_supported": 2, "fabricated_citations": 1}
    st = ls.morning_status(text=TEXT, ori_brief=_ori({**COV_FULL, "claim_gate_v1": failing}), collection_caveat=None)
    assert isinstance(st, ps.StatusResult) and st.status is ps.ProductionStatus.DEGRADED and "claim_gate_not_passed:shadow" in st.reasons
    ok = ls.morning_status(text=TEXT, ori_brief=_ori(COV_FULL), collection_caveat=None)
    assert ok.status is ps.ProductionStatus.NORMAL
    caveat = ls.morning_status(text=TEXT, ori_brief=_ori(COV_FULL), collection_caveat="x")
    assert caveat.status is ps.ProductionStatus.DEGRADED and "collection_not_ready" in caveat.reasons
    import inspect
    assert not [p for p in inspect.signature(ls.morning_status).parameters if "deliver" in p]


def test_build_from_evidence_renders_axes_and_records_gate(evidence):
    gate = {"passed": True, "mode": "shadow", "claims_total": 3, "claims_supported": 3}
    result, items, meta = ls.build_from_evidence(evidence, text=TEXT, ori_brief=_ori({**COV_FULL, "claim_gate_v1": gate}), now=NOW)
    assert set(result["axes"]) == {"posture", "coverage", "confidence"} and result["axes"]["coverage"]["value"] == "FULL"
    assert "L1" in result and "L6" in result
    assert meta["claim_gate_recorded"] is True and meta["incidents_rendered"] == len(items)


def test_degraded_coverage_without_support_is_not_all_clear():
    ev = SimpleNamespace(incidents=[], n_events=0, generated_at=NOW)
    result, _, _ = ls.build_from_evidence(ev, text=TEXT, ori_brief=_ori(COV_DEGRADED), now=NOW)
    assert result["axes"]["posture"]["value"] == "UNKNOWN" and result["axes"]["coverage"]["value"] == "DEGRADED"
    assert "all-clear" in result["L6"]["statement"] or "not" in result["L1"]["text"].lower()


def test_health_domain_incidents_excluded_from_shadow():
    v = SimpleNamespace(incident_id="inc-h", headline="Measles cases rise", priority="WATCH", materiality="medium", event_type="health",
                        impact_status="unconfirmed", evidence_status="reported", independent_publishers=1, provisional=True,
                        reports=[{"report_id": "e1", "publisher": "p", "role": "original", "title": "Measles", "geography": "AU"}],
                        record={}, last_seen=NOW)
    ev = SimpleNamespace(incidents=[v], n_events=1, generated_at=NOW)
    result, items, meta = ls.build_from_evidence(ev, text=TEXT, ori_brief=_ori(COV_FULL), now=NOW)
    assert meta["excluded_health_domain"] == 1 and items == []
    assert "inc-h" not in json.dumps(result)


# ── shadow storage ────────────────────────────────────────────────────────────────────────────────────────────────
HEALTH = {"checkins_today": 2, "latest_pain_state": "usual", "nested": {"a": [1, 2]}}


def test_attach_adds_only_shadow_key_and_is_valid(evidence):
    result, items, meta = ls.build_from_evidence(evidence, text=TEXT, ori_brief=_ori(COV_FULL), now=NOW)
    snap = copy.deepcopy(HEALTH)
    out = ls.attach_shadow(HEALTH, result, pir_items=items, meta=meta, now=NOW)
    assert HEALTH == snap                                              # not mutated
    assert {k: v for k, v in out.items() if k != "shadow_v1"} == snap  # every existing key unchanged
    sh = out["shadow_v1"]
    assert sh["published"] is False and sh["schema"] == 1 and sh["kind"] == "layered_brief" and "generated_at" in sh
    assert len(json.dumps(sh).encode()) <= 24 * 1024 and "companions" not in sh   # PIR flag off


def test_pir_payload_nests_under_companions_when_its_flag_is_on(evidence, monkeypatch):
    monkeypatch.setenv(req.FLAG_NAME, "1")
    result, items, meta = ls.build_from_evidence(evidence, text=TEXT, ori_brief=_ori(COV_FULL), now=NOW)
    out = ls.attach_shadow(HEALTH, result, pir_items=items, meta=meta, now=NOW)
    sh = out["shadow_v1"]
    assert sh["kind"] == "layered_brief" and sh["companions"]["pir_tagging"]["kind"] == "pir_tagging"
    assert sh["layers"]["L1"] and len(json.dumps(sh).encode()) <= 24 * 1024
    assert {k: v for k, v in out.items() if k != "shadow_v1"} == HEALTH


def test_existing_health_snapshot_reader_ignores_shadow(evidence):
    result, items, meta = ls.build_from_evidence(evidence, text=TEXT, ori_brief=_ori(COV_FULL), now=NOW)
    out = ls.attach_shadow(HEALTH, result, pir_items=items, meta=meta, now=NOW)
    block = cb._format_capacity_block(out)         # the production reader of health_snapshot-shaped data
    assert block == cb._format_capacity_block(HEALTH)


def test_ori_coverage_readers_ignore_status_and_gate_keys():
    from intelligence.brief import ori_status
    cov = ori_status.attach({**COV_FULL, "claim_gate_v1": {"passed": True}}, {"status": "NORMAL"})
    assert lr.coverage_status_from(cov) == lr.coverage_status_from(COV_FULL)


# ── morning path hook ────────────────────────────────────────────────────────────────────────────────────────────
def _run_send_brief(monkeypatch, events, *, layered: bool, pir: bool = False):
    from intelligence import brief_event_links, db_size
    if layered:
        monkeypatch.setenv(lr.FLAG, "1")
    if pir:
        monkeypatch.setenv(req.FLAG_NAME, "1")
    persisted, sent = {}, []
    gap = SimpleNamespace(lookback_hours=24, missed=False)
    monkeypatch.setattr(cb, "_morning_gap", lambda: gap)
    monkeypatch.setattr(cb, "_collection_coverage_caveat", lambda k: None)
    monkeypatch.setattr(cb, "generate_morning_brief", lambda *a, **k: TEXT)
    monkeypatch.setattr(cb, "_get_recent_signals", lambda hours=24: [])
    monkeypatch.setattr(cb, "_get_capacity_today", lambda: copy.deepcopy(HEALTH))
    monkeypatch.setattr(cb, "_get_latest_ori_brief", lambda: _ori(COV_FULL))
    monkeypatch.setattr(cb, "_persist_brief", lambda brief_type, text, **kw: persisted.update(text=text, **kw))
    monkeypatch.setattr(cb, "_record_brief_events", lambda *a, **k: None)
    monkeypatch.setattr(cb, "_email_morning_brief", lambda t: None)
    monkeypatch.setattr(cb, "_send_telegram", lambda t: sent.append(t) or True)
    monkeypatch.setattr(db_size, "check_and_warn", lambda: None)
    monkeypatch.setattr(be, "load_events", lambda sb_get, **kw: events)
    monkeypatch.setattr(be, "build_evidence", lambda evs, **kw: _REAL_BUILD(evs, now=NOW, **kw))
    assert cb.send_brief("morning") is True
    return persisted, sent


def test_flag_off_payload_identical_and_adapter_never_imported(monkeypatch, events):
    monkeypatch.setitem(sys.modules, "intelligence.brief.layered_shadow", None)     # any import attempt raises ImportError
    persisted, sent = _run_send_brief(monkeypatch, events, layered=False)
    assert persisted["health"] == HEALTH and "shadow_v1" not in persisted["health"]
    assert sent == [TEXT]
    obj = {}
    assert cb._layered_shadow_health(obj, TEXT, None) is obj


def test_flag_on_attaches_shadow_without_changing_text_or_other_keys(monkeypatch, events):
    off, sent_off = _run_send_brief(monkeypatch, events, layered=False)
    on, sent_on = _run_send_brief(monkeypatch, events, layered=True, pir=True)
    assert sent_on == [TEXT] and sent_off == [TEXT]
    assert on["text"] == off["text"] == TEXT
    assert {k: v for k, v in on["health"].items() if k != "shadow_v1"} == off["health"]
    sh = on["health"]["shadow_v1"]
    assert sh["published"] is False and sh["kind"] == "layered_brief" and "pir_tagging" in sh["companions"]
    assert {k: v for k, v in on.items() if k not in ("health",)} == {k: v for k, v in off.items() if k != "health"}


def test_flag_on_failure_returns_health_unchanged(monkeypatch, events):
    monkeypatch.setenv(lr.FLAG, "1")
    monkeypatch.setattr(cb, "_get_latest_ori_brief", lambda: 1 / 0)
    h = copy.deepcopy(HEALTH)
    assert cb._layered_shadow_health(h, TEXT, None) == HEALTH


def test_none_health_gets_only_shadow(monkeypatch, events):
    result, items, meta = ls.build_from_evidence(be.build_evidence(events, now=NOW, window_hours=72), text=TEXT, ori_brief=_ori(COV_FULL), now=NOW)
    assert list(ls.attach_shadow(None, result, meta=meta, now=NOW)) == ["shadow_v1"]


# ── audio hook ───────────────────────────────────────────────────────────────────────────────────────────────────
def _row(evidence):
    result, items, meta = ls.build_from_evidence(evidence, text=TEXT, ori_brief=_ori(COV_FULL), now=NOW)
    return {"id": "r1", "brief_text": "<b>legacy</b> text", "health_snapshot": ls.attach_shadow(HEALTH, result, now=NOW)}


def test_audio_text_from_stored_shadow(evidence):
    txt = ls.audio_text_from_row(_row(evidence))
    assert txt and "inc-" not in txt and "http" not in txt
    assert ls.audio_text_from_row({"health_snapshot": HEALTH}) is None and ls.audio_text_from_row({}) is None
    bad = _row(evidence)
    bad["health_snapshot"]["shadow_v1"]["published"] = True
    assert ls.audio_text_from_row(bad) is None


def _pregen(monkeypatch, evidence, *, audio_flag):
    from intelligence import scheduler
    posted, queries = {}, []
    monkeypatch.setenv("KOKORO_SERVICE_URL", "http://tts.invalid")
    monkeypatch.setenv("KOKORO_SERVICE_SECRET", "s")
    if audio_flag:
        monkeypatch.setenv(ls.AUDIO_FLAG, "1")
    row = _row(evidence)
    import heartbeat
    import requests
    monkeypatch.setattr(heartbeat, "supabase_get", lambda q: queries.append(q) or [row])
    monkeypatch.setattr(requests, "post", lambda url, **kw: posted.update(kw) or SimpleNamespace(raise_for_status=lambda: None))
    scheduler._pregenerate_brief_audio("morning")
    return posted, queries, row


def test_audio_flag_off_uses_legacy_text_and_query(monkeypatch, evidence):
    posted, queries, _ = _pregen(monkeypatch, evidence, audio_flag=False)
    assert posted["json"]["text"] == "legacy text"
    assert queries == ["captains_daily_briefs?brief_type=eq.morning&order=generated_at.desc&limit=1&select=id,brief_text"]


def test_audio_flag_on_uses_layered_script(monkeypatch, evidence):
    posted, queries, row = _pregen(monkeypatch, evidence, audio_flag=True)
    assert posted["json"]["text"] == ls.audio_text_from_row(row) != "legacy text"
    assert queries[0].endswith("select=id,brief_text,health_snapshot")
    assert posted["json"]["cache_key"] == "brief-r1"


# ── stored 24-25 Nov facts: before (WP4 isolated, stubs) / after (integrated real interfaces) ────────────────────
def _view(d):
    geo = "AU" if d.get("scope") == "domestic" else "GLOBAL"
    return SimpleNamespace(
        incident_id=d["incident_id"], headline=d["headline"], priority=d["priority"], materiality=d["materiality"], event_type=d.get("event_type", ""),
        impact_status=d["impact_status"], evidence_status=d["evidence_status"], independent_publishers=d["independent_publishers"],
        provisional=d["provisional"], last_seen=NOW,
        reports=[{"report_id": r["report_id"], "publisher": r["publisher"], "source_name": r["publisher"], "role": "original", "title": d["headline"],
                  "geography": geo, "summary": d.get("summary", "")} for r in d["reports"]],
        record={"restoration_status": {"current status unknown": "unknown", "ongoing": "ongoing", "restored": "restored"}.get(d.get("state"), "unknown"),
                "critical_service_dependencies": d.get("sectors", []), "next_verification_action": d.get("next_step", "")})


def nov25_ev():
    return SimpleNamespace(incidents=[_view(d) for d in NOV25["incidents"]], n_events=len(NOV25["incidents"]), generated_at=NOW)


def test_nov25_after_integration_keeps_axes_and_single_treatment():
    before = lr.render_layered(NOV25["incidents"], posture=None, coverage=NOV25["coverage"], confidence=None)
    result, items, meta = ls.build_from_evidence(nov25_ev(), text=TEXT, ori_brief=_ori(NOV25["coverage"]), now=NOW)
    ids = {d["incident_id"] for d in NOV25["incidents"]}
    assert meta["incidents_rendered"] == len(ids) == 9
    assert all(c in (0, 1) for c in lr.treatment_counts(result).values())
    assert before["axes"]["coverage"]["value"] == result["axes"]["coverage"]["value"] == "FULL"
    assert result["axes"]["posture"]["value"] in ("AMBER", "RED")           # a provisional ESCALATE item: never GREEN
    tagged = [ls.incident_input(v, req.load_pirs())["pir"] for v in nov25_ev().incidents]
    assert any(t.matches for t in tagged)                                  # real WP5 tags on the stored headlines
    assert len(json.dumps(lr.build_shadow_payload(result)).encode()) <= 24 * 1024


def test_nov24_degraded_collection_is_not_rendered_as_disruption_or_all_clear():
    ev = SimpleNamespace(incidents=[], n_events=0, generated_at=NOW)
    result, _, _ = ls.build_from_evidence(ev, text="", ori_brief=_ori(COV_DEGRADED, narrative_available=False), collection_caveat=None, now=NOW)
    assert result["axes"]["posture"]["value"] == "UNKNOWN"
    assert "Production status" in result["L1"]["text"]            # empty text => WP2 status DEGRADED/FAILED shown, not hidden
    assert "OAIC Breach Notifications" in json.dumps(result["axes"]["coverage"])
