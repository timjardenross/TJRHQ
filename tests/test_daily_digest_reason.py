"""TJRHQ#398: build_daily_digest() read `CaptainBriefItem.reason`, which was renamed `_routing_reason`,
so it raised AttributeError whenever a domain section had items; the Captain's morning brief then
fell back to the raw signals block. The digest must build from the item's readable text (never the
internal routing trace), and that fallback block must be HTML-escaped like the normal path.
"""
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import patch

from core.platform.attention_engine import AttentionCategory
from core.platform.captain_brief_contract import CaptainBriefItem, Recommendation
from intelligence import captains_brief as cb
from intelligence.brief import daily_digest as dd

ROUTING = "importance=0.9 >= 0.5 AND confidence=0.8 >= 0.5 (internal scoring trace)"
NRP = "regarding <NRP> imports"
ORG = "and <ORGANIZATION> obligations & more"


def _item(**kw) -> CaptainBriefItem:
    base = {
        "event_id": "e1",
        "domain": "engineering",
        "event_type": "engineering.deploy.failed",
        "category": AttentionCategory.CAN_BE_DELAYED,
        "_routing_reason": ROUTING,
    }
    base.update(kw)
    return CaptainBriefItem(**base)


def _doc(**sections) -> SimpleNamespace:
    empty = {"health": [], "engineering": [], "learning": [], "opportunities": [], "operational_intelligence": []}
    empty.update(sections)
    return SimpleNamespace(**empty)


def test_domain_events_use_readable_text_not_the_routing_trace():
    doc = _doc(engineering=[_item(description="Deploy of service X failed on staging")])
    text = dd._format_domain_events(doc)  # raised AttributeError before the fix
    assert "Deploy of service X failed on staging" in text
    assert "importance=" not in text and "internal scoring" not in text


def test_recommendation_description_is_preferred():
    rec = Recommendation(description="Roll back release 42", action_type="rollback")
    doc = _doc(health=[_item(domain="health", recommendation=rec, description="fallback desc")])
    text = dd._format_domain_events(doc)
    assert "Roll back release 42" in text and "fallback desc" not in text


def test_item_with_nothing_readable_is_left_out_not_filled_with_the_trace():
    doc = _doc(engineering=[_item()])
    text = dd._format_domain_events(doc)
    assert text == "" and ROUTING not in text


def test_build_daily_digest_builds_with_a_brief_item():
    doc = _doc(engineering=[_item(description="Deploy of service X failed")])
    prompts = []

    def fake_generate(prompt, **kwargs):
        prompts.append(prompt)
        return "Today the deploy of service X failed.", "fake-provider"

    with patch.object(dd, "poll_events", return_value=[object()]), \
         patch.object(dd, "assemble_captain_brief_document", return_value=doc), \
         patch.object(dd._llm, "generate", side_effect=fake_generate):
        out = dd.build_daily_digest(signals=[])
    assert out == "Today the deploy of service X failed."
    assert "Deploy of service X failed" in prompts[0] and ROUTING not in prompts[0]


# ── the fallback path used when digest synthesis fails ────────────────────────

class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def test_fallback_when_digest_fails_has_no_unescaped_angle_brackets_or_ampersands():
    signals = [
        {"raw_title": f"Signal {NRP}", "raw_summary": f"Summary {ORG}", "risk_rating": "HIGH",
         "intelligence_source_registry": {"source_name": "Feed <ORGANIZATION> & Co Status"}},
        {"raw_title": "Medium & more <NRP>", "raw_summary": "", "risk_rating": "MEDIUM"},
    ]
    with patch.object(cb, "_get_latest_ori_brief", return_value=None), \
         patch.object(cb, "_get_capacity_today", return_value=None), \
         patch.object(cb, "_get_recent_signals", return_value=signals), \
         patch.object(cb, "_get_infra_verification", return_value=None), \
         patch.object(cb, "build_daily_digest", side_effect=AttributeError("'CaptainBriefItem' object has no attribute 'reason'")):
        text = cb.generate_morning_brief()
    assert "OTHER SIGNALS (24h)" in text  # the fallback path really ran
    p = _Tags()
    p.feed(text)
    assert set(p.tags) <= {"b", "i", "code"}, p.tags
    assert "<NRP>" not in text and "<ORGANIZATION>" not in text
    assert "&lt;NRP&gt;" in text and "&lt;ORGANIZATION&gt;" in text and "&amp;" in text
    # every '&' is the start of an entity, every '<' the start of an allowed tag
    import re
    assert not re.search(r"&(?!amp;|lt;|gt;)", text)
    assert not re.search(r"<(?!/?(b|i|code)>)", text)


# ── "PLATFORM, TODAY" uses the local model only (no cloud tier) ───────────────

import pytest

from intelligence.brief import llm_provider as lp


def _cloud_tripwires(monkeypatch):
    """Every non-local tier raises if touched; returns the list of tiers that were called."""
    called: list[str] = []

    def boom(name):
        def _f(self, prompt):
            called.append(name)
            raise AssertionError(f"cloud tier {name} was called")
        return _f

    for name in ("_model_router", "_mistral_pipeline", "_gemini", "_mistral"):
        monkeypatch.setattr(lp.LLMProvider, name, boom(name))
    return called


def test_generate_local_only_selects_only_the_local_model(monkeypatch):
    called = _cloud_tripwires(monkeypatch)
    monkeypatch.setattr(lp.LLMProvider, "_ollama", lambda self, prompt: "local narrative")
    text, provider = lp.LLMProvider().generate("prompt", local_only=True)
    assert (text, provider) == ("local narrative", lp.OLLAMA_MODEL)
    assert called == []


def test_generate_default_still_tries_the_cloud_chain_first(monkeypatch):
    # unchanged for every other caller: local_only defaults to False
    called = []
    monkeypatch.setattr(lp.LLMProvider, "_model_router", lambda self, p: called.append("router") or "from router")
    _text, provider = lp.LLMProvider().generate("prompt")
    assert provider == "model-router" and called == ["router"]


def test_digest_never_reaches_a_cloud_tier(monkeypatch):
    called = _cloud_tripwires(monkeypatch)
    prompts = []
    monkeypatch.setattr(lp.LLMProvider, "_ollama", lambda self, p: prompts.append(p) or "Local summary of the day.")
    doc = _doc(engineering=[_item(description="Deploy of service X failed")])
    with patch.object(dd, "poll_events", return_value=[object()]), \
         patch.object(dd, "assemble_captain_brief_document", return_value=doc):
        out = dd.build_daily_digest(signals=[{"risk_rating": "HIGH", "raw_title": "T", "raw_summary": "S"}])
    assert out == "Local summary of the day."
    assert called == [] and len(prompts) == 1  # only the local model saw the prompt


def test_digest_passes_local_only_to_the_provider():
    seen = {}

    def fake_generate(prompt, *args, **kwargs):
        seen.update(kwargs)
        return "ok", "x"

    doc = _doc(engineering=[_item(description="Deploy failed")])
    with patch.object(dd, "poll_events", return_value=[object()]), \
         patch.object(dd, "assemble_captain_brief_document", return_value=doc), \
         patch.object(dd._llm, "generate", side_effect=fake_generate):
        dd.build_daily_digest(signals=[])
    assert seen.get("local_only") is True


@pytest.mark.parametrize("exc", [TimeoutError("timed out"), OSError("connection refused")])
def test_local_timeout_or_error_falls_back_to_the_escaped_signals_block(monkeypatch, exc):
    called = _cloud_tripwires(monkeypatch)

    def failing(self, prompt):
        raise exc

    monkeypatch.setattr(lp.LLMProvider, "_ollama", failing)
    signals = [{"raw_title": f"Signal {NRP}", "raw_summary": f"S {ORG}", "risk_rating": "HIGH"}]
    doc = _doc(engineering=[_item(description="Deploy failed")])
    with patch.object(dd, "poll_events", return_value=[object()]), \
         patch.object(dd, "assemble_captain_brief_document", return_value=doc), \
         patch.object(cb, "_get_latest_ori_brief", return_value=None), \
         patch.object(cb, "_get_capacity_today", return_value=None), \
         patch.object(cb, "_get_recent_signals", return_value=signals), \
         patch.object(cb, "_get_infra_verification", return_value=None), \
         patch.object(cb, "build_daily_digest", dd.build_daily_digest):
        assert dd.build_daily_digest(signals=signals) is None  # nothing from the model: no digest, no raise
        text = cb.generate_morning_brief()
    assert called == []  # a failing local model did not push the call to a cloud tier
    assert "OTHER SIGNALS (24h)" in text and "PLATFORM, TODAY" not in text
    p = _Tags()
    p.feed(text)
    assert set(p.tags) <= {"b", "i", "code"}
    assert "<NRP>" not in text and "&lt;NRP&gt;" in text


def test_local_model_output_is_escaped_in_the_brief(monkeypatch):
    _cloud_tripwires(monkeypatch)
    monkeypatch.setattr(lp.LLMProvider, "_ollama", lambda self, p: f"Summary {NRP} {ORG}")
    doc = _doc(engineering=[_item(description="Deploy failed")])
    with patch.object(dd, "poll_events", return_value=[object()]), \
         patch.object(dd, "assemble_captain_brief_document", return_value=doc), \
         patch.object(cb, "_get_latest_ori_brief", return_value=None), \
         patch.object(cb, "_get_capacity_today", return_value=None), \
         patch.object(cb, "_get_recent_signals", return_value=[]), \
         patch.object(cb, "_get_infra_verification", return_value=None), \
         patch.object(cb, "build_daily_digest", dd.build_daily_digest):
        text = cb.generate_morning_brief()
    assert "PLATFORM, TODAY" in text
    p = _Tags()
    p.feed(text)
    assert set(p.tags) <= {"b", "i", "code"}
    assert "<NRP>" not in text and "<ORGANIZATION>" not in text
    assert "&lt;NRP&gt;" in text and "&amp;" in text
