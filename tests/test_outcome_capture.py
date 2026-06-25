#!/usr/bin/env python3
"""
USS-TJR-MSN-0076 — Outcome & Learning Capture tests (WP7).

Network-free: the Supabase client functions are stubbed in the module
namespace, and the lessons_learned promotion path is stubbed via sys.modules.
Runnable two ways:
    python3 tests/test_outcome_capture.py        # standalone, prints PASS/FAIL
    pytest tests/test_outcome_capture.py          # discovered as test_* funcs

Coverage:
  - controlled-vocabulary + confidence validation
  - safe operation when Supabase is unavailable (no crash, no persist)
  - successful upsert + idempotent on_conflict key (no duplicate records)
  - row mapping (arrays default, cleaning)
  - content-reuse flagging + external-exposure sensitivity guard
  - lesson promotion into the existing lessons_learned store (+ opt-out)
  - retrieval filters (content-worthy excludes not_for_publication)
  - briefing snapshot + daily-brief integration line
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "core" / "knowledge"))
sys.path.insert(0, str(_REPO_ROOT / "slack-bot" / "lib"))

import outcome_capture as oc  # noqa: E402


# ---------------------------------------------------------------------------
# Test helpers — a tiny in-memory Supabase stub
# ---------------------------------------------------------------------------

class _Recorder:
    """Captures upsert calls so we can assert on them."""
    def __init__(self):
        self.calls = []

    def upsert(self, table, payload, on_conflict, timeout=20):
        self.calls.append({"table": table, "payload": payload, "on_conflict": on_conflict})
        return payload


def _set_online(monkey_rec: _Recorder | None):
    """Make outcome_capture think Supabase is online and route upserts to recorder."""
    oc.is_configured = lambda: True  # type: ignore
    if monkey_rec is not None:
        oc.supabase_upsert = monkey_rec.upsert  # type: ignore


def _set_offline():
    oc.is_configured = lambda: False  # type: ignore


def _restore():
    # Reload-free restore: re-point to the real implementations.
    import importlib
    importlib.reload(oc)


def _stub_lessons(returned_id="LL-999"):
    """Inject a fake lesson_capture module so promotion does no real I/O."""
    fake = types.ModuleType("lesson_capture")

    class LessonInput:  # minimal shape
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _Res:
        def __init__(self):
            self.lesson_id = returned_id
            self.success = True
            self.errors = []

    def capture_lesson(_inp):
        return _Res()

    fake.LessonInput = LessonInput
    fake.capture_lesson = capture_lesson
    sys.modules["lesson_capture"] = fake


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_validation_rejects_bad_input():
    _set_offline()
    res = oc.record_outcome(oc.OutcomeInput(source_type="banana", source_id="", title=""))
    assert not res.success
    assert any("source_type" in e for e in res.errors)
    assert any("source_id" in e for e in res.errors)
    assert any("title" in e for e in res.errors)

    res2 = oc.record_outcome(oc.OutcomeInput(
        source_type="mission", source_id="MSN-1", title="t",
        outcome_status="explosive", confidence=9, content_potential="huge",
    ))
    assert not res2.success
    assert any("outcome_status" in e for e in res2.errors)
    assert any("confidence" in e for e in res2.errors)
    assert any("content_potential" in e for e in res2.errors)


def test_offline_is_safe():
    _set_offline()
    res = oc.record_outcome(oc.OutcomeInput(
        source_type="decision", source_id="D-001", title="A decision",
        outcome_status="worked", promote_lesson=False,
    ))
    assert res.success            # validated ok
    assert res.persisted is False  # but not persisted offline
    assert any("not configured" in w for w in res.warnings)


def test_successful_upsert_uses_dedup_key():
    rec = _Recorder()
    _set_online(rec)
    res = oc.record_outcome(oc.OutcomeInput(
        source_type="mission", source_id="MSN-0075", title="Discovery",
        outcome_status="worked", reusable_insight="parallel sweeps scale",
        reuse_tags=["discovery"], promote_lesson=False,
    ))
    assert res.success and res.persisted
    assert len(rec.calls) == 1
    call = rec.calls[0]
    assert call["table"] == "outcome_records"
    # Idempotency / no-duplicate guarantee: upsert on the source key.
    assert call["on_conflict"] == "source_type,source_id"
    assert call["payload"]["source_id"] == "MSN-0075"
    assert call["payload"]["reuse_tags"] == ["discovery"]
    assert call["payload"]["outcome_id"].startswith("OUTR-")
    _restore()


def test_row_mapping_defaults_and_cleaning():
    inp = oc.OutcomeInput(source_type="note", source_id="N-1", title="  Hi  ",
                          outcome_summary="   ", reuse_tags=[], evidence_links=[])
    row = oc._row(inp, "OUTR-X", "internal_work", None)
    assert row["title"] == "Hi"
    assert row["outcome_summary"] is None         # whitespace cleaned to None
    assert row["reuse_tags"] == [] and row["evidence_links"] == []
    assert row["content_classification"] == "internal_work"


def test_sensitivity_guard_downgrades_external_publication():
    rec = _Recorder()
    _set_online(rec)
    res = oc.record_outcome(oc.OutcomeInput(
        source_type="decision", source_id="D-SEC", title="Rotated the API key",
        outcome_status="worked", lesson_learned="store secrets in vault",
        content_potential="high", content_classification="linkedin",
        promote_lesson=False,
    ))
    assert res.persisted
    # The sensitive marker must force not_for_publication.
    assert rec.calls[0]["payload"]["content_classification"] == "not_for_publication"
    assert any("downgraded" in w for w in res.warnings)
    _restore()


def test_lesson_promotion_links_and_opt_out():
    _stub_lessons("LL-123")
    rec = _Recorder()
    _set_online(rec)
    # With a lesson + promote_lesson default True → promoted + linked.
    res = oc.record_outcome(oc.OutcomeInput(
        source_type="mission", source_id="MSN-9", title="Shipped",
        outcome_status="worked", lesson_learned="ship small",
    ))
    assert res.lesson_id == "LL-123"
    assert rec.calls[0]["payload"]["lesson_id"] == "LL-123"

    # Opt-out → no promotion.
    rec2 = _Recorder()
    _set_online(rec2)
    res2 = oc.record_outcome(oc.OutcomeInput(
        source_type="mission", source_id="MSN-10", title="Shipped2",
        outcome_status="worked", lesson_learned="ship small", promote_lesson=False,
    ))
    assert res2.lesson_id is None
    assert rec2.calls[0]["payload"]["lesson_id"] is None
    sys.modules.pop("lesson_capture", None)
    _restore()


def test_content_worthy_excludes_not_for_publication():
    _set_online(None)
    oc.supabase_get = lambda q: [  # type: ignore
        {"outcome_id": "OUTR-1", "content_potential": "high",
         "content_classification": "linkedin", "title": "Good"},
        {"outcome_id": "OUTR-2", "content_potential": "high",
         "content_classification": "not_for_publication", "title": "Secret"},
    ]
    rows = oc.list_content_worthy()
    ids = [r["outcome_id"] for r in rows]
    assert "OUTR-1" in ids and "OUTR-2" not in ids
    _restore()


def test_brief_snapshot_offline_quiet():
    _set_offline()
    snap = oc.learning_brief_snapshot()
    assert snap.data_available is False
    assert snap.has_signal is False


def test_daily_brief_renders_learning_line():
    import daily_brief as db

    class _Dom:
        def __init__(self): self.label, self.band = "Physical", "GREEN"

    class _Cap:
        headline = "Steady"
        overall_band = "GREEN"
        overall_score = 80
        domains = [_Dom()]

    class _Rec:
        escalation = ""
        primary = "Do the thing"
        expected_impact = "impact"
        opportunity_cost = "cost"
        recommended_deferral = "later"
        strategic_alignment = "aligned"
        def _confidence_label(self): return "High"

    class _Load:
        data_available = True
        open_count = 2

    snap = oc.LearningSnapshot(
        recent_lessons=[{"lesson_id": "LL-1", "title": "Reuse beats rebuild"}],
        uncaptured_count=3, reusable_count=1, content_worthy_count=2,
        data_available=True,
    )
    out = db.compose_daily_brief(capacity=_Cap(), recommendation=_Rec(),
                                 load=_Load(), learning=snap)
    assert "Learning" in out
    assert "3 item(s) missing outcomes" in out
    assert "Reuse beats rebuild" in out

    # No learning param → no learning line (backward compatible).
    out2 = db.compose_daily_brief(capacity=_Cap(), recommendation=_Rec(), load=_Load())
    assert "Learning (" not in out2


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def _run() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {t.__name__}: {e}")
            failed += 1
        except Exception as e:  # unexpected
            print(f"  💥 {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
        finally:
            # Ensure clean module state between tests.
            try:
                import importlib
                importlib.reload(oc)
            except Exception:
                pass
    print(f"\n── Outcome Capture Tests: {passed} passed, {failed} failed ──")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
