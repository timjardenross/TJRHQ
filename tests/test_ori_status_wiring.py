"""BRIEF_STATUS_V1 wiring for ORI briefs (integration of WP2 production status with WP3's return contract / claim-gate record).
Collection, store and LLM are mocks; nothing leaves the process."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from intelligence import brief_published_notifier as notifier
from intelligence import claim_gate
from intelligence import production_status as ps
from intelligence.brief import ori_status
from intelligence.brief.brief_generator import BriefGenerator
from tests.test_brief_generator_claim_gate import BAD, GOOD_STRICT

OK_RECORDS = [SimpleNamespace(status="ok", source_name="Src A", )]


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    for f in (ps.FLAG, claim_gate.FLAG_NAME):
        monkeypatch.delenv(f, raising=False)


def _generate(monkeypatch, reply, *, records=OK_RECORDS, gate=None, status_flag=True):
    from intelligence.brief.external_domains import DomainFetchResult
    from tests.test_intelligence_brief_generator import TestLLMFailureDegradation, _make_ranked_event
    top = [_make_ranked_event("Event 1", 1)]
    if gate:
        monkeypatch.setenv(claim_gate.FLAG_NAME, gate)
    if status_flag:
        monkeypatch.setenv(ps.FLAG, "1")
    store = TestLLMFailureDegradation()._patch_store()
    with patch("intelligence.brief.brief_generator.collect_all", return_value=([], records)), \
         patch("intelligence.brief.brief_generator.store", store), \
         patch("intelligence.brief.brief_generator.classify", side_effect=lambda x: x), \
         patch("intelligence.brief.brief_generator.rank", return_value=top), \
         patch("intelligence.brief.brief_generator.top_events", return_value=top), \
         patch("intelligence.brief.brief_generator.morning_cycle.get_status", return_value=None), \
         patch("intelligence.brief.brief_generator.external_domains.fetch_health_signals",
               return_value=DomainFetchResult(domain="health", available=True, signals=[])), \
         patch("intelligence.brief.brief_generator.external_domains.fetch_emergency_alerts",
               return_value=DomainFetchResult(domain="emergency", available=True, signals=[])), \
         patch("intelligence.brief.brief_generator.LLMProvider") as cls:
        llm = MagicMock()
        llm.generate.return_value = (reply if isinstance(reply, str) else json.dumps(reply), "p")
        llm.check_brief_quality.return_value = None
        llm.check_risk_rating.return_value = None
        cls.return_value = llm
        return BriefGenerator().generate()


def test_flag_off_coverage_has_no_status_key_and_is_unchanged(monkeypatch):
    on = _generate(monkeypatch, GOOD_STRICT, status_flag=True).coverage
    monkeypatch.delenv(ps.FLAG, raising=False)
    off = _generate(monkeypatch, GOOD_STRICT, status_flag=False).coverage
    assert ori_status.KEY not in off
    assert {k: v for k, v in on.items() if k != ori_status.KEY} == {k: v for k, v in off.items() if k != "production_status_v1"}
    assert off["degraded"] is False and off["expected"] == on["expected"]


def test_normal_brief_gets_normal_status(monkeypatch):
    rec = _generate(monkeypatch, GOOD_STRICT).coverage[ori_status.KEY]
    assert rec["status"] == "NORMAL" and rec["reasons"] == [] and rec["schema"] == 1 and rec["kind"] == "production_status"
    assert rec["inputs"]["narrative_available"] is True and rec["published"] is False


def test_unparseable_narrative_is_not_normal(monkeypatch):
    b = _generate(monkeypatch, "not json at all")           # WP3 contract: llm_used False => narrative_available False
    rec = b.coverage[ori_status.KEY]
    assert b.narrative_available is False
    assert rec["status"] == "DEGRADED" and any(r.startswith("narrative_") for r in rec["reasons"])


def test_enforce_fallback_is_degraded_with_reason(monkeypatch):
    b = _generate(monkeypatch, BAD, gate="enforce")
    rec = b.coverage[ori_status.KEY]
    assert b.narrative_available is False and b.coverage["claim_gate_v1"]["fallback_used"] is True
    assert rec["status"] == "DEGRADED"
    assert "evidence_fallback_in_use" in rec["reasons"] and "narrative_marked_unavailable" in rec["reasons"]
    assert any(r.startswith("claim_gate_not_passed:enforce") for r in rec["reasons"])
    assert rec["inputs"]["fallback_used"] is True


def test_shadow_gate_failure_published_narrative_is_degraded(monkeypatch):
    rec = _generate(monkeypatch, BAD, gate="shadow").coverage[ori_status.KEY]
    assert rec["status"] == "DEGRADED" and any(r.startswith("claim_gate_not_passed:shadow") for r in rec["reasons"])


def test_no_collected_source_and_no_narrative_is_failed(monkeypatch):
    rec = _generate(monkeypatch, "{}", records=[]).coverage[ori_status.KEY]
    assert rec["status"] == "FAILED" and "collection_not_ready" in rec["reasons"]


def test_failed_sources_degrade_even_with_good_narrative(monkeypatch):
    recs = [SimpleNamespace(status="ok", source_name="A"), SimpleNamespace(status="failed", source_name="B")]
    rec = _generate(monkeypatch, GOOD_STRICT, records=recs).coverage[ori_status.KEY]
    assert rec["status"] == "DEGRADED" and "sources_failed" in rec["reasons"]


def test_status_function_never_reads_delivery():
    import inspect
    sig = inspect.signature(ori_status.compute)
    assert not any("deliver" in p or "notif" in p or "telegram" in p or "email" in p for p in sig.parameters)
    cov = {"expected": 3, "completed": 3, "failed": 0, "degraded": False}
    base = dict(executive_snapshot="An Optus fault disrupted services in Victoria.", bottom_line="Optus services were disrupted by a fault.",
                llm_used=True, narrative_available=True, coverage=cov, collection_ready=True)
    from datetime import datetime, timezone
    now = datetime(2026, 11, 25, tzinfo=timezone.utc)
    a = ori_status.compute(**base, now=now)
    with patch.object(notifier, "send_email", return_value=False):         # a failed e-mail send changes nothing
        notifier.notify_published({"coverage": {ori_status.KEY: a}, "period_end": "2026-11-25"})
    assert ori_status.compute(**base, now=now) == a


def test_attach_preserves_every_existing_key():
    cov = {"expected": 3, "claim_gate_v1": {"passed": True}, "nested": {"a": 1}}
    snap = copy.deepcopy(cov)
    out = ori_status.attach(cov, {"status": "NORMAL"})
    assert cov == snap and all(out[k] == v for k, v in snap.items()) and out[ori_status.KEY] == {"status": "NORMAL"}


def test_claim_gate_record_round_trips_to_real_dataclass():
    g = ori_status.claim_gate_from_record({"passed": False, "mode": "enforce", "claims_total": 5, "claims_supported": 3, "fallback_used": True})
    assert isinstance(g, claim_gate.ClaimGateResult) and not g.passed and g.mode == "enforce" and g.claims_total == 5
    assert ori_status.claim_gate_from_record(None) is None and ori_status.claim_gate_from_record({}) is None
    assert ori_status.claim_gate_from_record({"mode": "shadow"}).passed is False        # a record that does not say passed fails closed
    assert ori_status.claim_gate_from_record({"passed": False, "parse_rejected": "x"}).reasons == ["parse_rejected:x"]


def test_notifier_status_line_only_when_flag_on_and_not_normal(monkeypatch):
    sent = {}
    monkeypatch.setattr(notifier, "send_email", lambda **kw: sent.update(kw) or True)
    row = {"period_end": "2026-11-25", "overall_risk": "AMBER", "executive_snapshot": "Snap.",
           "coverage": {ori_status.KEY: {"status": "DEGRADED", "reasons": ["evidence_fallback_in_use"]}}}
    notifier.notify_published(row)
    legacy_html = sent["html"]
    assert "Production status" not in legacy_html
    monkeypatch.setenv(ps.FLAG, "1")
    notifier.notify_published(row)
    assert "Production status: DEGRADED (evidence_fallback_in_use)" in sent["html"]
    assert sent["html"].replace(sent["html"][sent["html"].index("<p><em>"):sent["html"].index("</em></p>") + 9], "") == legacy_html
    row["coverage"][ori_status.KEY]["status"] = "NORMAL"
    notifier.notify_published(row)
    assert sent["html"] == legacy_html
