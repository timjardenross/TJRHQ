#!/usr/bin/env python3
"""USS-TJR-MSN-0087 — Narrative Intelligence Service tests (WP9). Network-free.

Run: python3 tests/test_learning_narrative.py   (or under pytest)
Covers explain_health, captain_narrative, captain_recommendations, compose, and the
offline-safe fetch wrappers. Evidence-backed; no invented observations.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "core" / "knowledge"))

import learning_narrative as ln  # noqa: E402


@dataclass
class _Status:
    data_available: bool = True
    health: str = "GREEN"
    outcomes_recorded: int = 73
    pending_outcomes: int = 25
    overdue_outcomes: int = 0
    learning_debt: int = 0
    sensitive_pending: int = 0
    reusable_insights: int = 21
    leadership_candidates: int = 24
    capture_compliance_pct: int = 74


def test_explain_health_green_amber_red_offline():
    assert "keeping pace" in ln.explain_health(_Status(health="GREEN"))
    amber = ln.explain_health(_Status(health="AMBER", capture_compliance_pct=40, overdue_outcomes=2))
    assert "attention" in amber.lower() and ("40%" in amber or "overdue" in amber)
    red = ln.explain_health(_Status(health="RED", learning_debt=3, overdue_outcomes=5))
    assert "risk" in red.lower() and "30 days" in red
    assert "offline" in ln.explain_health(_Status(data_available=False)).lower()


def test_captain_narrative_structure_and_evidence():
    s = _Status(overdue_outcomes=3, sensitive_pending=1, learning_debt=2, capture_compliance_pct=40)
    leads = [{"reusable_insight": "reuse before build"}, {"title": "RLS catch"}]
    n = ln.captain_narrative(s, leads, [])
    assert "73 outcome" in n["what_changed"]
    assert n["what_matters"]                      # significance, not blank
    # Every attention item references a real count.
    joined = " ".join(n["attention"])
    assert "3 overdue" in joined and "2 item" in joined and "1 sensitive" in joined and "40%" in joined
    assert "reuse before build" in n["leaders_should_know"]


def test_recommendations_are_evidence_backed_and_advisory():
    s = _Status(overdue_outcomes=3, sensitive_pending=2, learning_debt=1, leadership_candidates=24)
    recs = ln.captain_recommendations(s, [])
    assert recs
    for r in recs:
        assert r["evidence"] and r["confidence"] in ("HIGH", "MEDIUM", "LOW")
    texts = " ".join(r["action"] for r in recs)
    assert "overdue" in texts and "sensitive" in texts and "debt" in texts.lower()


def test_recommendations_clean_state():
    s = _Status(pending_outcomes=0, overdue_outcomes=0, learning_debt=0,
                sensitive_pending=0, leadership_candidates=0, capture_compliance_pct=100)
    recs = ln.captain_recommendations(s, [])
    assert any("No action required" in r["action"] for r in recs)


def test_compose_captain_brief_renders_sections():
    s = _Status(overdue_outcomes=2, sensitive_pending=1)
    n = ln.captain_narrative(s, [{"reusable_insight": "validate before deploy"}], [])
    recs = ln.captain_recommendations(s, [])
    out = ln.compose_captain_brief(n, recs, health="AMBER")
    assert "Captain Narrative" in out
    assert "What changed" in out and "Why it matters" in out
    assert "Needs attention" in out and "Recommended" in out
    assert "advisory" in out.lower()


def test_offline_wrappers_safe(monkeypatch=None):
    # Force the underlying service offline.
    ln._oc.learning_status = lambda: _Status(data_available=False)  # type: ignore
    assert "unavailable" in ln.captain_brief_text().lower()
    q = ln.pending_actions()
    assert q["data_available"] is False and q["overdue"] == []
    import importlib
    importlib.reload(ln)  # restore real bindings


def _run() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for t in tests:
        try:
            t(); print(f"  ✅ {t.__name__}"); p += 1
        except Exception as e:  # noqa
            print(f"  ❌ {t.__name__}: {e}"); f += 1
    print(f"\n── Narrative tests: {p} passed, {f} failed ──")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(_run())
