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


def _candidate_rows():
    return [
        {"outcome_id": "OUTR-1", "title": "A", "content_classification": "linkedin",
         "content_potential": "high", "reusable_insight": "share X"},
        {"outcome_id": "OUTR-2", "title": "B", "content_classification": "leadership",
         "content_potential": "medium", "reusable_insight": "lead Y"},
        {"outcome_id": "OUTR-3", "title": "C", "content_classification": "internal_work",
         "content_potential": "high", "reusable_insight": "ops Z"},
        {"outcome_id": "OUTR-4", "title": "D", "content_classification": "personal_story",
         "content_potential": "high", "reusable_insight": "recovery story"},
        {"outcome_id": "OUTR-5", "title": "E", "content_classification": "not_for_publication",
         "content_potential": "high", "reusable_insight": "secret"},
    ]


def test_get_content_candidates_excludes_internal_personal_and_nfp():
    oc.list_content_worthy = lambda limit=25: _candidate_rows()  # type: ignore
    rows = oc.get_content_candidates(limit=10)
    ids = {r["outcome_id"] for r in rows}
    # linkedin + leadership kept; internal_work, personal_story, not_for_publication excluded.
    assert ids == {"OUTR-1", "OUTR-2"}, ids
    _restore()


def test_get_content_candidates_audience_filter():
    oc.list_content_worthy = lambda limit=25: _candidate_rows()  # type: ignore
    rows = oc.get_content_candidates(audience="linkedin", limit=10)
    assert [r["outcome_id"] for r in rows] == ["OUTR-1"]
    _restore()


def test_get_content_candidates_include_internal_optin():
    oc.list_content_worthy = lambda limit=25: _candidate_rows()  # type: ignore
    rows = oc.get_content_candidates(limit=10, include_internal=True)
    ids = {r["outcome_id"] for r in rows}
    # internal_work + personal_story now included; not_for_publication still excluded.
    assert "OUTR-3" in ids and "OUTR-4" in ids
    assert "OUTR-5" not in ids
    _restore()


def test_get_content_candidates_offline_empty():
    _set_offline()
    # list_content_worthy returns [] offline → no candidates, no crash.
    assert oc.get_content_candidates(limit=10) == []
    _restore()


def test_personal_story_in_vocabulary():
    assert "personal_story" in oc.CONTENT_CLASSIFICATIONS
    # It must be internal/sensitive by default (not auto-surfaced).
    assert "personal_story" in oc._INTERNAL_BY_DEFAULT


def test_requires_approval_for_sensitive_classes():
    for cls in ("coaching", "wellness", "personal_story", "internal_work"):
        assert oc.requires_approval(cls) is True, cls
    for cls in ("linkedin", "leadership", "operational_resilience", None, ""):
        assert oc.requires_approval(cls) is False, cls


def test_closure_prompt_requests_when_no_outcome_and_never_invents():
    oc.has_outcome = lambda st, sid: False  # type: ignore
    prompt = oc.closure_prompt("mission", "MSN-0079", "Auto-capture")
    assert prompt is not None
    # It asks; it must not assert any lesson content itself.
    assert "outcome pending" in prompt.lower()
    assert "What was learned?" in prompt
    assert "record_outcome.py record" in prompt
    _restore()


def test_closure_prompt_silent_when_outcome_exists():
    oc.has_outcome = lambda st, sid: True  # type: ignore
    assert oc.closure_prompt("decision", "D-1", "X") is None
    _restore()


def test_pending_outcomes_offline_empty():
    _set_offline()
    assert oc.pending_outcomes() == []
    _restore()


def test_learning_metrics_offline_safe():
    _set_offline()
    m = oc.learning_metrics()
    assert m.data_available is False
    assert m.as_dict()["OUTCOMES RECORDED"] == 0


def test_aging_band_thresholds():
    assert oc.aging_band(0) == "GREEN"
    assert oc.aging_band(7) == "GREEN"
    assert oc.aging_band(8) == "AMBER"
    assert oc.aging_band(14) == "AMBER"
    assert oc.aging_band(15) == "RED"
    assert oc.aging_band(99) == "RED"
    assert oc.aging_band(None) == "UNKNOWN"


def test_age_days_parses_iso():
    from datetime import datetime, timezone, timedelta
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    ts = (now - timedelta(days=10)).isoformat()
    assert oc._age_days(ts, _now=now) == 10
    assert oc._age_days(None) is None
    assert oc._age_days("not-a-date") is None


def test_learning_health_model():
    # RED: overdue with no recent capture.
    h, _ = oc.learning_health(pending=4, overdue=2, velocity=0, outcomes=4)
    assert h == "RED"
    # RED: high backlog.
    h, _ = oc.learning_health(pending=12, overdue=0, velocity=5, outcomes=20)
    assert h == "RED"
    # GREEN: low backlog + active capture.
    h, _ = oc.learning_health(pending=2, overdue=0, velocity=3, outcomes=10)
    assert h == "GREEN"
    # GREEN: nothing pending.
    h, _ = oc.learning_health(pending=0, overdue=0, velocity=0, outcomes=10)
    assert h == "GREEN"
    # AMBER: moderate backlog, no recent capture, not overdue.
    h, reasons = oc.learning_health(pending=6, overdue=0, velocity=0, outcomes=6)
    assert h == "AMBER" and reasons


def test_velocity_and_trend_buckets():
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    rows = [
        {"created_at": (now - timedelta(days=1)).isoformat()},   # week 0
        {"created_at": (now - timedelta(days=3)).isoformat()},   # week 0
        {"created_at": (now - timedelta(days=9)).isoformat()},   # week 1
        {"created_at": "bad"},                                    # ignored
    ]
    last7, weeks = oc._velocity_and_trend(rows)
    assert last7 == 2
    assert weeks[0] == 2 and weeks[1] == 1


def test_learning_status_offline_safe():
    _set_offline()
    s = oc.learning_status()
    assert s.data_available is False
    assert s.health == "UNKNOWN"
    assert s.as_dict()["PENDING OUTCOMES"] == 0


def test_learning_status_block_offline():
    _set_offline()
    block = oc.learning_status_block()
    assert "LEARNING STATUS" in block
    assert "Unavailable" in block


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


def test_daily_brief_shows_health_overdue_and_sensitive():
    import daily_brief as db

    class _Dom:
        def __init__(self): self.label, self.band = "Physical", "GREEN"

    class _Cap:
        headline = "Steady"; overall_band = "GREEN"; overall_score = 80; domains = [_Dom()]

    class _Rec:
        escalation = ""; primary = "x"; expected_impact = "i"; opportunity_cost = "c"
        recommended_deferral = "l"; strategic_alignment = "a"
        def _confidence_label(self): return "High"

    class _Load:
        data_available = True; open_count = 1

    snap = oc.LearningSnapshot(
        uncaptured_count=5, overdue_count=2, reusable_count=1, content_worthy_count=0,
        sensitive_pending=1, health="AMBER", data_available=True,
    )
    out = db.compose_daily_brief(capacity=_Cap(), recommendation=_Rec(), load=_Load(),
                                 learning=snap)
    assert "2 overdue" in out
    assert "sensitive pending approval" in out
    assert "🟠" in out  # AMBER health tag


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
