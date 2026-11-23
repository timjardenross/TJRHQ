"""Gate 1 corrective tests (Captain's review, weekly intelligence uplift).

Covers: future-dated capacity records, the mislabelled "recovery confidence"
metric, sample-sufficiency, absence-vs-normality wording, and fail-closed
handling of personal health data (no cloud LLM unless explicitly opted in).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

import intelligence.captains_brief as cb


def _fake(responses):
    return lambda table, *a, **k: responses.get(table, [])


FUTURE_PULSES = [
    {"log_date": "2099-01-01", "pulse_type": "morning", "energy": "low"},
    {"log_date": "2099-01-01", "pulse_type": "evening", "energy": "low"},
]


class TestFutureDatedRecords:
    def test_future_pulses_are_excluded_and_next_tier_is_reached(self):
        checkins = [{"log_date": "2026-11-03", "capacity_state": "green"}]
        with mock.patch.object(cb, "_sb_get", side_effect=_fake({
            "recovery_pulses": FUTURE_PULSES, "capacity_checkins": checkins,
        })):
            r = cb._get_weekly_capacity(days=7)
        assert r["source"] == "checkin"
        assert r["excluded_future"] == 2

    def test_only_future_rows_means_none_not_a_pulse_week(self):
        with mock.patch.object(cb, "_sb_get", side_effect=_fake({"recovery_pulses": FUTURE_PULSES})):
            r = cb._get_weekly_capacity(days=7)
        assert r["source"] == "none" and r["entries"] == []
        assert r["excluded_future"] == 2

    def test_every_tier_is_bounded_at_the_database(self):
        with mock.patch.object(cb, "_sb_get", side_effect=_fake({})) as g:
            cb._get_weekly_capacity(days=7)
        for call in g.call_args_list:
            assert "log_date=lte." in call.args[1], call.args[0]

    def test_shape_unchanged_when_nothing_excluded(self):
        rows = [{"log_date": "2026-09-10", "capacity_state": "green"}]
        with mock.patch.object(cb, "_sb_get", side_effect=_fake({"capacity_checkins": rows})):
            assert cb._get_weekly_capacity(days=7) == {"source": "checkin", "entries": rows}

    def test_exclusion_is_reported_in_the_block(self):
        text = "\n".join(cb._format_weekly_capacity_block(
            {"source": "none", "entries": [], "excluded_future": 2}))
        assert "2 future-dated record(s) excluded" in text


class TestRecoveryMetric:
    PULSES = ({"log_date": "2026-11-03", "pulse_type": "morning", "energy": "low"},)

    def test_no_recovery_confidence_wording_remains(self):
        text = "\n".join(cb._format_weekly_capacity_block({"source": "pulse", "entries": list(self.PULSES)}))
        assert "Recovery confidence" not in text
        assert "logging coverage" in text and "not a measure of recovery" in text

    def test_small_sample_withholds_inference(self):
        text = "\n".join(cb._format_weekly_capacity_block({"source": "pulse", "entries": list(self.PULSES)}))
        assert "Not enough observations (1 over 1 day(s)" in text
        assert "no inference made" in text

    def test_sufficient_sample_has_no_withholding_line(self):
        rows = [{"log_date": f"2026-11-0{d}", "capacity_state": "green"} for d in (3, 4, 5)] + \
               [{"log_date": "2026-11-05", "capacity_state": "orange"}]
        text = "\n".join(cb._format_weekly_capacity_block({"source": "checkin", "entries": rows}))
        assert "Not enough observations" not in text

    def test_many_entries_on_two_days_is_still_insufficient(self):
        rows = [{"log_date": "2026-11-03", "capacity_state": "green"}] * 3 + \
               [{"log_date": "2026-11-04", "capacity_state": "green"}] * 3
        text = "\n".join(cb._format_weekly_capacity_block({"source": "checkin", "entries": rows}))
        assert "Not enough observations (6 over 2 day(s)" in text

    def test_no_data_is_not_observed_not_fine(self):
        text = "\n".join(cb._format_weekly_capacity_block({"source": "none", "entries": []}))
        assert "Not observed" in text and "not evidence that capacity was fine" in text
        assert "stable" not in text.lower()


class TestPersonalDataPrivacy:
    def _provider(self, monkeypatch, external):
        import health_llm as h
        if external:
            monkeypatch.setenv("HEALTH_LLM_EXTERNAL_ALLOWED", "1")
        else:
            monkeypatch.delenv("HEALTH_LLM_EXTERNAL_ALLOWED", raising=False)
        return h, h.HealthLLMProvider()

    def test_default_permits_only_the_local_provider(self, monkeypatch):
        h, p = self._provider(monkeypatch, external=False)
        assert p.permitted_providers() == [h._OLLAMA_MODEL]

    def test_default_never_calls_a_cloud_provider(self, monkeypatch):
        h, p = self._provider(monkeypatch, external=False)
        with mock.patch.object(p, "_gemini", side_effect=AssertionError("cloud call")), \
             mock.patch.object(p, "_mistral", side_effect=AssertionError("cloud call")), \
             mock.patch.object(p, "_ollama", return_value="local text"):
            assert p.generate("personal prompt") == ("local text", h._OLLAMA_MODEL)

    def test_local_failure_falls_back_to_none_without_trying_cloud(self, monkeypatch):
        _h, p = self._provider(monkeypatch, external=False)
        with mock.patch.object(p, "_gemini", side_effect=AssertionError("cloud call")), \
             mock.patch.object(p, "_mistral", side_effect=AssertionError("cloud call")), \
             mock.patch.object(p, "_ollama", return_value=None):
            assert p.generate("personal prompt") == (None, None)

    def test_local_exception_is_contained(self, monkeypatch):
        _h, p = self._provider(monkeypatch, external=False)
        with mock.patch.object(p, "_ollama", side_effect=RuntimeError("down")):
            assert p.generate("x") == (None, None)

    def test_explicit_opt_in_restores_legacy_order(self, monkeypatch):
        h, p = self._provider(monkeypatch, external=True)
        assert p.permitted_providers() == ["gemini-3.5-flash-lite", "mistral-small", h._OLLAMA_MODEL]

    def test_unrecognised_flag_value_stays_closed(self, monkeypatch):
        _h, p = self._provider(monkeypatch, external=False)
        import health_llm as h
        monkeypatch.setenv("HEALTH_LLM_EXTERNAL_ALLOWED", "maybe")
        assert p.permitted_providers() == [h._OLLAMA_MODEL]
