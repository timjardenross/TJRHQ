"""Tests for tools/health-osint/health_signal_synthesis.py — cross-source
signal clustering + narrative synthesis.

_groups_from_dedup_result and _parse_narrative are pure and tested
directly. synthesize_cluster_narrative's provider fallback chain is tested
the same way tests/test_health_signal_curation_model_router.py already
tests health_signal_curation._classify's — mock.patch each
core.llm.provider_chain function at its source module, since both modules
import it with a local `from core.llm.provider_chain import ...` inside
the function body.

_cluster_published_signals itself (the one function that touches the real
semhash package) is exercised only via importorskip + a fully mocked
SemHash class — this repo's authoring sandbox could not install semhash's
Hugging Face Hub model download end-to-end (proxy blocks huggingface.co),
so this guards the test suite from failing in any environment where
semhash isn't installed yet, while still real-testing the module's own
integration code against the actual installed package where it is
available.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "tools" / "health-osint"))

import health_signal_synthesis as hss

from core.llm.provider_chain import LLMCallResult


def _signal(**overrides):
    base = {
        "signal_id": "sig-1", "title": "ADHD medication linked to reduced PEM symptoms",
        "description": "A new study finds...", "health_domain": "adhd",
        "canonical_url": "https://example.org/a", "source_name": "PubMed",
    }
    base.update(overrides)
    return base


# ── _groups_from_dedup_result — pure, duck-typed ─────────────────────────────

def _entry(record, duplicates):
    return SimpleNamespace(record=record, duplicates=duplicates)


def test_groups_from_dedup_result_drops_singletons():
    entries = [
        _entry(_signal(signal_id="a"), duplicates=[]),
        _entry(_signal(signal_id="b"), duplicates=[(_signal(signal_id="c"), 0.91)]),
    ]
    groups = hss._groups_from_dedup_result(entries)
    assert len(groups) == 1
    assert {s["signal_id"] for s in groups[0]} == {"b", "c"}


def test_groups_from_dedup_result_empty_when_all_singletons():
    entries = [_entry(_signal(signal_id="a"), duplicates=[]), _entry(_signal(signal_id="b"), duplicates=[])]
    assert hss._groups_from_dedup_result(entries) == []


def test_groups_from_dedup_result_handles_multiple_duplicates():
    entries = [
        _entry(
            _signal(signal_id="a"),
            duplicates=[(_signal(signal_id="b"), 0.95), (_signal(signal_id="c"), 0.88)],
        ),
    ]
    groups = hss._groups_from_dedup_result(entries)
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_cluster_published_signals_short_circuits_below_two_signals():
    assert hss._cluster_published_signals([]) == []
    assert hss._cluster_published_signals([_signal()]) == []


@pytest.mark.parametrize("mocked", [True])
def test_cluster_published_signals_with_mocked_semhash(mocked):
    pytest.importorskip("semhash")
    fake_result = SimpleNamespace(
        selected_with_duplicates=[
            _entry(_signal(signal_id="a"), duplicates=[(_signal(signal_id="b"), 0.9)]),
        ]
    )
    fake_sh = SimpleNamespace(self_deduplicate=lambda threshold: fake_result)
    with mock.patch("semhash.SemHash.from_records", return_value=fake_sh) as from_records_mock:
        groups = hss._cluster_published_signals([_signal(signal_id="a"), _signal(signal_id="b")], threshold=0.85)
    from_records_mock.assert_called_once()
    assert len(groups) == 1
    assert {s["signal_id"] for s in groups[0]} == {"a", "b"}


# ── _parse_narrative ──────────────────────────────────────────────────────────

def test_parse_narrative_valid():
    raw = json.dumps({
        "synthesis": "PubMed and ScienceDaily both report X.",
        "key_sources": ["PubMed", "ScienceDaily"],
        "confidence_note": "Sources agree.",
    })
    result = hss._parse_narrative(raw)
    assert result["synthesis"] == "PubMed and ScienceDaily both report X."
    assert result["key_sources"] == ["PubMed", "ScienceDaily"]


def test_parse_narrative_strips_markdown_fence():
    raw = "```json\n" + json.dumps({
        "synthesis": "s", "key_sources": ["A"], "confidence_note": "c",
    }) + "\n```"
    result = hss._parse_narrative(raw)
    assert result is not None
    assert result["synthesis"] == "s"


def test_parse_narrative_missing_keys_returns_none():
    assert hss._parse_narrative(json.dumps({"synthesis": "s"})) is None


def test_parse_narrative_empty_or_none_returns_none():
    assert hss._parse_narrative("") is None
    assert hss._parse_narrative(None) is None


def test_parse_narrative_coerces_non_list_key_sources():
    raw = json.dumps({"synthesis": "s", "key_sources": "PubMed", "confidence_note": "c"})
    result = hss._parse_narrative(raw)
    assert result["key_sources"] == ["PubMed"]


# ── synthesize_cluster_narrative — provider fallback chain ───────────────────

def test_synthesize_uses_gemini_when_available():
    gemini_result = LLMCallResult(
        text=json.dumps({"synthesis": "s", "key_sources": ["A"], "confidence_note": "c"}),
        model="gemini-3.5-flash-lite",
    )
    with mock.patch("core.llm.provider_chain.call_gemini", return_value=gemini_result) as gemini_mock, \
         mock.patch("core.llm.provider_chain.call_mistral") as mistral_mock:
        narrative, provider = hss.synthesize_cluster_narrative([_signal(signal_id="a"), _signal(signal_id="b")])
    gemini_mock.assert_called_once()
    mistral_mock.assert_not_called()
    assert provider == "gemini"
    assert narrative["synthesis"] == "s"


def test_synthesize_falls_back_through_chain_on_failure():
    ollama_result = LLMCallResult(
        text=json.dumps({"synthesis": "s2", "key_sources": ["B"], "confidence_note": "c2"}),
        model="qwen3:8b",
    )
    with mock.patch("core.llm.provider_chain.call_gemini", side_effect=RuntimeError("down")), \
         mock.patch("core.llm.provider_chain.call_mistral", side_effect=RuntimeError("down")), \
         mock.patch("core.llm.provider_chain.call_ollama", return_value=ollama_result):
        narrative, provider = hss.synthesize_cluster_narrative([_signal()])
    assert provider == "ollama"
    assert narrative["synthesis"] == "s2"


def test_synthesize_returns_none_when_every_provider_fails():
    with mock.patch("core.llm.provider_chain.call_gemini", side_effect=RuntimeError("down")), \
         mock.patch("core.llm.provider_chain.call_mistral", side_effect=RuntimeError("down")), \
         mock.patch("core.llm.provider_chain.call_ollama", side_effect=RuntimeError("down")):
        narrative, provider = hss.synthesize_cluster_narrative([_signal()])
    assert narrative is None
    assert provider is None


# ── _write_cluster ────────────────────────────────────────────────────────────

def test_write_cluster_dry_run_returns_none_and_writes_nothing():
    db = mock.MagicMock()
    result = hss._write_cluster(db, [_signal()], None, None, 0.85, dry_run=True)
    assert result is None
    db.table.assert_not_called()


def test_write_cluster_writes_cluster_and_updates_members():
    db = mock.MagicMock()
    db.table.return_value.insert.return_value.execute.return_value.data = [{"cluster_id": "clu-1"}]
    group = [_signal(signal_id="a"), _signal(signal_id="b")]
    narrative = {"synthesis": "s", "key_sources": ["A"], "confidence_note": "c"}

    cluster_id = hss._write_cluster(db, group, narrative, "gemini", 0.85, dry_run=False)

    assert cluster_id == "clu-1"
    insert_call = db.table.return_value.insert.call_args.args[0]
    assert insert_call["narrative"] == "s"
    assert insert_call["member_count"] == 2
    update_call = db.table.return_value.update.call_args.args[0]
    assert update_call == {"cluster_id": "clu-1"}
    in_call = db.table.return_value.update.return_value.in_.call_args.args
    assert in_call == ("signal_id", ["a", "b"])


def test_write_cluster_writes_row_even_when_narrative_failed():
    db = mock.MagicMock()
    db.table.return_value.insert.return_value.execute.return_value.data = [{"cluster_id": "clu-2"}]
    hss._write_cluster(db, [_signal(signal_id="a"), _signal(signal_id="b")], None, None, 0.85, dry_run=False)
    insert_call = db.table.return_value.insert.call_args.args[0]
    assert "narrative" not in insert_call
    assert insert_call["member_count"] == 2
