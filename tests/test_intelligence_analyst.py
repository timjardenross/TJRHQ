"""
Unit tests for intelligence/analysis/intelligence_analyst.py (Phase A Stages 8–9).

Covers:
- Heuristic scoring: valid 1–5 dims, 0–50 total, correct risk banding
- Telstra-style signal -> HIGH; low-impact signal -> LOW
- LLM path via injected fake provider (method='llm', provider recorded)
- Graceful fallback to heuristic on: no LLM, empty output, garbage JSON, exception
- risk_rating thresholds; as_event_columns sets signal_status SCORED
- score_event adapter over a ClassifiedEvent-like object
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.analysis.intelligence_analyst import (
    DIMENSIONS,
    IntelligenceAnalyst,
    SignalScore,
    risk_rating_for,
)


class FakeLLM:
    """Stand-in for LLMProvider with configurable generate() behaviour."""

    def __init__(self, raw, provider="fake-llm", raises=False):
        self._raw = raw
        self._provider = provider
        self._raises = raises

    def generate(self, prompt):
        if self._raises:
            raise RuntimeError("provider down")
        return self._raw, self._provider


TELSTRA = {
    "title": "Telstra network outage hits millions",
    "summary": "Nationwide Telstra mobile and internet outage.",
    "sector": "telecom",
    "event_type": "telecom_outage",
    "geography": "AU",
    "customer_impact": "high",
    "banking_relevance": "high",
    "cps230_relevance": False,
    "dependency_risk": True,
    "operational_relevance": 0.9,
}

LOW_SIGNAL = {
    "title": "Minor vendor blog post about a UI tweak",
    "summary": "A small cosmetic change with no operational impact.",
    "sector": "media",
    "event_type": "other",
    "geography": "GLOBAL",
    "customer_impact": "low",
    "banking_relevance": "low",
    "cps230_relevance": False,
    "dependency_risk": False,
    "operational_relevance": 0.1,
}


class TestHeuristicScoring(unittest.TestCase):
    def setUp(self):
        # Inject a fake that yields no usable output -> forces heuristic path.
        self.analyst = IntelligenceAnalyst(llm_provider=FakeLLM(raw=None))

    def test_all_dims_in_range(self):
        score = self.analyst.score_signal(TELSTRA)
        self.assertEqual(set(score.score_breakdown), set(DIMENSIONS))
        for dim, v in score.score_breakdown.items():
            self.assertTrue(1 <= v <= 5, f"{dim}={v} out of range")
        self.assertTrue(0 <= score.total_score <= 50)
        self.assertTrue(1.0 <= score.relevance_score <= 5.0)

    def test_telstra_is_high(self):
        score = self.analyst.score_signal(TELSTRA)
        self.assertEqual(score.method, "heuristic")
        self.assertEqual(score.risk_rating, "HIGH")
        self.assertGreaterEqual(score.total_score, 40)
        self.assertEqual(score.score_breakdown["criticality"], 5)
        self.assertEqual(score.score_breakdown["australian_relevance"], 5)

    def test_low_signal_is_low(self):
        score = self.analyst.score_signal(LOW_SIGNAL)
        self.assertEqual(score.risk_rating, "LOW")
        self.assertLess(score.total_score, 32)

    def test_deterministic(self):
        a = self.analyst.score_signal(TELSTRA)
        b = self.analyst.score_signal(TELSTRA)
        self.assertEqual(a.score_breakdown, b.score_breakdown)

    def test_as_event_columns(self):
        cols = self.analyst.score_signal(TELSTRA).as_event_columns()
        self.assertEqual(cols["signal_status"], "SCORED")
        self.assertEqual(cols["risk_rating"], "HIGH")
        self.assertIn("score_breakdown", cols)
        self.assertEqual(cols["rank_score"], float(cols["score_breakdown"] and
                                                   sum(cols["score_breakdown"].values())))


class TestLLMPath(unittest.TestCase):
    def test_valid_llm_json(self):
        raw = (
            'Sure! {"score_breakdown": {"criticality": 5, "scale": 5, "duration": 4, '
            '"customer_harm": 5, "systemic_relevance": 5, "dependency_risk": 5, '
            '"regulatory_relevance": 4, "learning_value": 5, "australian_relevance": 5, '
            '"forward_significance": 4}}'
        )
        analyst = IntelligenceAnalyst(llm_provider=FakeLLM(raw=raw, provider="model-router"))
        score = analyst.score_signal(TELSTRA)
        self.assertEqual(score.method, "llm")
        self.assertEqual(score.provider, "model-router")
        self.assertEqual(score.total_score, 47)
        self.assertEqual(score.risk_rating, "HIGH")

    def test_llm_out_of_range_clamped(self):
        raw = '{"score_breakdown": {' + ", ".join(f'"{d}": 9' for d in DIMENSIONS) + '}}'
        analyst = IntelligenceAnalyst(llm_provider=FakeLLM(raw=raw))
        score = analyst.score_signal(TELSTRA)
        self.assertEqual(score.total_score, 50)  # all clamped to 5
        for v in score.score_breakdown.values():
            self.assertEqual(v, 5)

    def test_garbage_json_falls_back(self):
        analyst = IntelligenceAnalyst(llm_provider=FakeLLM(raw="not json at all"))
        score = analyst.score_signal(TELSTRA)
        self.assertEqual(score.method, "heuristic")

    def test_partial_json_falls_back(self):
        # Fewer than half the dimensions present -> untrusted -> heuristic.
        raw = '{"score_breakdown": {"criticality": 5, "scale": 4}}'
        analyst = IntelligenceAnalyst(llm_provider=FakeLLM(raw=raw))
        score = analyst.score_signal(TELSTRA)
        self.assertEqual(score.method, "heuristic")

    def test_provider_exception_falls_back(self):
        analyst = IntelligenceAnalyst(llm_provider=FakeLLM(raw="x", raises=True))
        score = analyst.score_signal(TELSTRA)
        self.assertEqual(score.method, "heuristic")


class TestMisc(unittest.TestCase):
    def test_risk_rating_thresholds(self):
        self.assertEqual(risk_rating_for(40), "HIGH")
        self.assertEqual(risk_rating_for(39), "MEDIUM")
        self.assertEqual(risk_rating_for(32), "MEDIUM")
        self.assertEqual(risk_rating_for(31), "LOW")

    def test_score_event_adapter(self):
        class Ev:
            raw_title = "Optus payments disruption"
            raw_summary = "EFTPOS down nationwide"
            sector = "payments"
            event_type = "payments_disruption"
            geography = "AU"
            customer_impact = "high"
            banking_relevance = "high"
            cps230_relevance = True
            dependency_risk = True
            operational_relevance = 0.8

        analyst = IntelligenceAnalyst(llm_provider=FakeLLM(raw=None))
        score = analyst.score_event(Ev())
        self.assertIsInstance(score, SignalScore)
        self.assertEqual(score.risk_rating, "HIGH")
        self.assertEqual(score.score_breakdown["regulatory_relevance"], 5)  # cps230


if __name__ == "__main__":
    unittest.main()
