"""HQ V1 Integration QA §28 regression: tools/health-osint/health_signal_curation.py
must try Model Router first (tier-0), falling back to the direct LLM
provider chain only when Model Router itself is unreachable — matching
intelligence/adhd/task_decomposition.py's existing ordering, closing the
one confirmed Model Router bypass found in that audit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "tools" / "health-osint"))

import health_signal_curation as hsc  # noqa: E402


def _signal(**overrides):
    base = {
        "signal_id": "sig-1", "title": "Test signal", "description": "desc",
        "signal_type": "study", "health_domain": "chronic_pain",
        "contributing_factor_type": None, "population_description": None,
        "study_design": None, "fda_flagged": False, "adverse_event_text": None,
        "source_name": "Test Source", "canonical_url": None,
    }
    base.update(overrides)
    return base


def test_parse_classification_valid_response():
    raw = json.dumps({"decision": "publish", "reason": "clear signal", "mission_relevance": "high", "safety_relevance": True})
    result = hsc._parse_classification(raw, "test")
    assert result["decision"] == "PUBLISH"
    assert result["safety_relevance"] is True


def test_parse_classification_empty_returns_none_for_fallthrough():
    assert hsc._parse_classification("", "test") is None
    assert hsc._parse_classification(None, "test") is None


def test_parse_classification_unrecognised_decision_escalates():
    raw = json.dumps({"decision": "MAYBE", "reason": "unsure"})
    result = hsc._parse_classification(raw, "test")
    assert result["decision"] == "ESCALATE"


def test_classify_tries_model_router_first():
    """Model Router succeeding must short-circuit before any direct
    provider call is attempted."""
    router_response = json.dumps({"decision": "REJECT", "reason": "noise"})
    with mock.patch.object(hsc, "_call_model_router", return_value=router_response) as router_mock, \
         mock.patch("core.llm.provider_chain.call_gemini") as gemini_mock:
        result = hsc._classify(_signal())
    router_mock.assert_called_once()
    gemini_mock.assert_not_called()
    assert result["decision"] == "REJECT"


def test_classify_falls_back_to_direct_providers_when_model_router_unreachable():
    with mock.patch.object(hsc, "_call_model_router", side_effect=RuntimeError("Model Router unavailable")), \
         mock.patch("core.llm.provider_chain.call_gemini", return_value=json.dumps({"decision": "PUBLISH", "reason": "ok"})) as gemini_mock:
        result = hsc._classify(_signal())
    gemini_mock.assert_called_once()
    assert result["decision"] == "PUBLISH"


def test_classify_escalates_when_every_provider_fails():
    with mock.patch.object(hsc, "_call_model_router", side_effect=RuntimeError("down")), \
         mock.patch("core.llm.provider_chain.call_gemini", side_effect=RuntimeError("down")), \
         mock.patch("core.llm.provider_chain.call_mistral", side_effect=RuntimeError("down")), \
         mock.patch("core.llm.provider_chain.call_ollama", side_effect=RuntimeError("down")):
        result = hsc._classify(_signal())
    assert result["decision"] == "ESCALATE"
    assert result["safety_relevance"] is False
