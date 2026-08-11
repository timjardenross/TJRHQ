"""Tests for the MSN-0092 Advisory Runtime (core/advisory).

These run fully offline — the specialist pipeline degrades deterministically
when SUPABASE_URL / Ollama are absent, and evidence/lessons are file-based.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ADVISORY = _REPO_ROOT / "core" / "advisory"
for _p in (str(_ADVISORY),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import schema  # noqa: E402
from _local_import_advisory import import_sibling  # noqa: E402

# Fleet Engineering Review 2026-08-11: evidence, lessons, service collide
# with same-named files elsewhere in the repo — see core/advisory/
# _local_import_advisory.py's own docstring. Routed through
# import_sibling() so this file can't be poisoned by (or poison) an
# unrelated same-named file loaded elsewhere in the same pytest session.
evidence_mod = import_sibling("evidence")
lessons_mod = import_sibling("lessons")
service = import_sibling("service")


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def test_confidence_bands():
    assert schema.ConfidenceLevel.from_value(0.9).band == "High"
    assert schema.ConfidenceLevel.from_value(0.6).band == "Medium"
    assert schema.ConfidenceLevel.from_value(0.2).band == "Low"
    # clamps
    assert schema.ConfidenceLevel.from_value(5.0).value == 1.0
    assert schema.ConfidenceLevel.from_value(-1.0).value == 0.0


def test_response_markdown_has_seven_sections():
    resp = schema.AdvisoryResponse(question="Test?", recommendation="Do X.")
    md = resp.to_markdown()
    for n, title in enumerate([
        "Executive Summary", "Recommendation", "Historical Evidence",
        "Related Lessons", "Risks and Challenges", "Confidence Level",
        "Officer Perspectives",
    ], start=1):
        assert f"## {n}. {title}" in md
    # advisory authority note always present
    assert "Advisory only" in md


def test_response_to_dict_roundtrip_keys():
    resp = schema.AdvisoryResponse(question="Q?")
    d = resp.to_dict()
    for key in ("question", "executive_summary", "recommendation",
                "historical_evidence", "related_lessons", "risks_and_challenges",
                "confidence", "officer_perspectives"):
        assert key in d


def test_slack_mrkdwn_strips_double_asterisks():
    resp = schema.AdvisoryResponse(question="Q?", recommendation="Do X.")
    txt = resp.to_slack_mrkdwn()
    assert "**" not in txt


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------

def test_score_confidence_without_evidence_is_low_basis():
    conf = evidence_mod.score_confidence(0.5, None, None)
    assert isinstance(conf, schema.ConfidenceLevel)
    assert "opinion" in conf.basis


def test_score_confidence_blends_officers():
    low = evidence_mod.score_confidence(0.5, None, [10, 20])
    high = evidence_mod.score_confidence(0.5, None, [90, 95])
    assert high.value > low.value


def test_gather_related_decisions_matches_known_topic():
    # The decision logs contain "Slack ... Voice Core" decisions.
    decisions = evidence_mod.gather_related_decisions("Should we prioritise Slack over Voice Core?")
    assert decisions, "expected at least one related decision"
    assert all(isinstance(d, schema.RelatedDecision) for d in decisions)
    assert decisions[0].decision_id


def test_gather_related_decisions_empty_for_nonsense():
    assert evidence_mod.gather_related_decisions("zzzqqq xyzzy") == []


def test_gather_evidence_returns_list():
    items, raw = evidence_mod.gather_evidence("Advisory", "activate runtime lessons evidence")
    assert isinstance(items, list)
    # raw may be None only if the store is unavailable; in this repo it exists.
    assert raw is not None


# --------------------------------------------------------------------------
# Lessons
# --------------------------------------------------------------------------

def test_related_lessons_returns_lessonrefs():
    refs = lessons_mod.related_lessons("Capability Activation", "activate advisory runtime")
    assert refs, "expected lessons to match the activation query"
    assert all(isinstance(r, schema.LessonRef) for r in refs)
    assert refs[0].lesson_id.startswith("LL-")


def test_lessons_brief_structure():
    brief = lessons_mod.lessons_brief("advisory runtime evidence")
    assert set(["query", "lessons", "similar_missions", "narrative"]).issubset(brief.keys())
    assert isinstance(brief["lessons"], list)


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------

def test_request_advice_returns_full_response():
    resp = service.request_advice(
        "Should we prioritise activating the advisory runtime over new subsystems?"
    )
    assert isinstance(resp, schema.AdvisoryResponse)
    assert resp.recommendation
    assert resp.officer_perspectives, "fan-out should yield officer perspectives offline"
    assert resp.related_lessons, "lessons should be attached"
    assert resp.decision_mode in ("strategic", "operational", "architectural", "governance")
    # evidence-based: at least one of evidence / lessons / decisions present
    assert resp.related_lessons or resp.historical_evidence or resp.related_decisions


def test_request_advice_empty_question_degrades():
    resp = service.request_advice("   ")
    assert resp.degraded
    assert resp.confidence.value == 0.0


def test_request_challenge_surfaces_reviewer():
    resp = service.request_challenge(
        "Should we prioritise Slack specialist collaboration over Voice Core?"
    )
    assert resp.reviewer, "challenge mode must select a reviewer"
    assert resp.disagreement, "challenge mode must surface a disagreement statement"


def test_invoke_dispatch():
    advice = service.invoke("advice", "Should we activate the advisory runtime?")
    assert isinstance(advice, schema.AdvisoryResponse)
    lessons = service.invoke("lessons", "advisory runtime")
    assert isinstance(lessons, dict) and "narrative" in lessons


def test_available_officers_nonempty():
    officers = service.available_officers()
    assert officers and all("title" in o for o in officers)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
