"""WP2: production status is computed from content + collection only, never from delivery."""
import inspect
from types import SimpleNamespace

import pytest

from intelligence import production_status as ps
from intelligence.production_status import ProductionStatus as S
from intelligence.production_status import compute_production_status

GOOD = "Overnight collection found two material resilience incidents affecting Australian providers; both are assessed below."
OK_COV = {"degraded": False, "failed": 0, "missing_sources": []}


def run(**kw):
    base = {"narrative_text": GOOD, "llm_used": True, "narrative_available": True, "claim_gate": None, "coverage": OK_COV,
                "row_stored": True, "collection_ready": True}
    base.update(kw)
    return compute_production_status(**base)


def test_normal_when_everything_is_sound():
    r = run()
    assert r.status is S.NORMAL and r.reasons == []


@pytest.mark.parametrize("text,reason", [
    (None, "narrative_missing"), ("", "narrative_empty"), ("   \n ", "narrative_empty"), ("...", "narrative_empty"),
    ("N/A", "narrative_boilerplate"), ("Narrative unavailable.", "narrative_boilerplate"),
    ("No narrative was generated", "narrative_boilerplate"), ("Unable to generate summary at this time", "narrative_boilerplate"),
    ("LLM unavailable", "narrative_boilerplate"), ("Nothing currently requires immediate action.", "narrative_boilerplate"),
    ("TBD", "narrative_boilerplate"), ("Short text only", "narrative_too_short"),
])
def test_empty_boilerplate_placeholder_is_never_normal(text, reason):
    r = run(narrative_text=text, narrative_available=True)
    assert r.status is not S.NORMAL
    assert reason in r.reasons


def test_available_flag_true_does_not_rescue_empty_text():
    assert run(narrative_text="", narrative_available=True).status is S.DEGRADED


def test_marked_unavailable_is_degraded_even_with_text():
    r = run(narrative_available=False)
    assert r.status is S.DEGRADED and "narrative_marked_unavailable" in r.reasons


def test_no_usable_narrative_and_collection_down_is_failed():
    assert run(narrative_text="", collection_ready=False).status is S.FAILED


def test_row_not_stored_is_failed():
    r = run(row_stored=False)
    assert r.status is S.FAILED and "row_not_stored" in r.reasons


def test_deterministic_fallback_is_degraded_not_failed():
    r = run(llm_used=False)
    assert r.status is S.DEGRADED and "deterministic_fallback_narrative" in r.reasons


def test_claim_gate_failure_degrades_in_any_mode():
    for mode in ("shadow", "enforce"):
        r = run(claim_gate=SimpleNamespace(passed=False, mode=mode))
        assert r.status is S.DEGRADED and f"claim_gate_not_passed:{mode}" in r.reasons
    assert run(claim_gate=SimpleNamespace(passed=True, mode="shadow")).status is S.NORMAL


@pytest.mark.parametrize("cov,reason", [({"degraded": True}, "coverage_degraded"), ({"failed": 2}, "sources_failed"),
                                         ({"missing_sources": ["X"]}, "sources_missing")])
def test_degraded_coverage(cov, reason):
    r = run(coverage=cov)
    assert r.status is S.DEGRADED and reason in r.reasons


def test_collection_not_ready_with_narrative_is_degraded():
    assert run(collection_ready=False).status is S.DEGRADED


def test_independence_signature_has_no_delivery_input():
    params = set(inspect.signature(compute_production_status).parameters)
    assert not any("deliver" in p or "telegram" in p or "send" in p for p in params)


def test_independence_delivery_outcome_cannot_change_status(monkeypatch):
    from intelligence import delivery_record as dr
    before = run().status
    for outcome in dr.DeliveryOutcome:
        monkeypatch.setattr(dr, "enabled", lambda: True)
        assert run().status is before                       # delivery state present or absent: same result
    broken = run(narrative_text="")
    assert broken.status is S.DEGRADED                      # and a perfect send elsewhere cannot repair it


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(ps.FLAG, raising=False)
    assert ps.enabled() is False
