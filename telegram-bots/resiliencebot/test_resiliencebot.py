"""Tests for the Resilience Crosswalk bot — conversation logic and handler wiring.

Handlers are driven with fake Update/Context objects; the crosswalk pipeline is
replaced with a fake, so nothing here calls Telegram or a model.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from lib.resilience import audit
from lib.resilience.corpus import load_corpus
from lib.resilience.pipeline import CrosswalkRun
from lib.resilience.schema import Crosswalk, CrosswalkDraft, VerificationItem

from telegram_bots.resiliencebot import app
from telegram_bots.resiliencebot import conversation as cv

FWS = ["APRA-CPS-230", "BCBS-d516", "EU-DORA", "ISO-22301-2019"]


# ── conversation: session ─────────────────────────────────────────────────────

def test_new_session_defaults_to_cps230_and_truncates():
    s = cv.new_session("x" * 900, FWS)
    assert s.source == "APRA-CPS-230"
    assert len(s.request) == cv.MAX_REQUEST_CHARS
    assert s.targets == set()


def test_toggle_adds_removes_and_ignores_source_and_bad_index():
    s = cv.new_session("q", FWS)
    assert s.toggle(1) and s.targets == {"BCBS-d516"}
    assert s.toggle(1) and s.targets == set()
    assert not s.toggle(0)       # the source itself
    assert not s.toggle(99)
    assert s.targets == set()


def test_cycle_source_drops_it_from_targets():
    s = cv.new_session("q", FWS)
    s.toggle(1)
    s.cycle_source()
    assert s.source == "BCBS-d516"
    assert "BCBS-d516" not in s.targets


def test_cycle_use_wraps():
    s = cv.new_session("q", FWS)
    for _ in cv.USES:
        s.cycle_use()
    assert s.use == cv.USES[0]


def test_keyboard_hides_source_marks_targets_and_fits_callback_limit():
    s = cv.new_session("q", FWS)
    s.toggle(2)
    rows = cv.intake_keyboard(s)
    labels = [label for row in rows for label, _ in row]
    assert "APRA-CPS-230" not in labels
    assert "✅ EU-DORA" in labels
    assert all(len(data.encode()) <= 64 for row in rows for _, data in row)


# ── conversation: callbacks ───────────────────────────────────────────────────

@pytest.mark.parametrize(("data", "kind"), [
    ("xw|t|3", "toggle"), ("xw|src", "source"), ("xw|use", "use"), ("xw|run", "run"), ("xw|x", "cancel"),
    ("rv|xw-abc123def456|a", "review"),
    ("xw|t|x", "unknown"), ("rv|nope|a", "unknown"), ("rv|xw-1|z", "unknown"), ("", "unknown"), ("zz", "unknown"),
])
def test_parse_callback(data, kind):
    assert cv.parse_callback(data).kind == kind


def test_review_callback_maps_decision():
    cb = cv.parse_callback("rv|xw-abc123def456|e")
    assert (cb.run_id, cb.decision) == ("xw-abc123def456", "edited")
    assert all(len(d.encode()) <= 64 for row in cv.review_keyboard("xw-abc123def456") for _, d in row)


# ── conversation: summaries ───────────────────────────────────────────────────

def _ok_run():
    draft = CrosswalkDraft.model_validate({
        "source": {"framework_id": "APRA-CPS-230", "clause_id": None, "requirement_text": "Test BCP"},
        "components": ["testing"],
        "mappings": [
            {"component": "testing", "framework_id": "BCBS-d516", "clause_id": "BCBS-d516-P3",
             "requirement_summary": "BCP testing", "alignment": "PARTIAL", "confidence": "MEDIUM"},
            {"component": "testing", "framework_id": "EU-DORA", "clause_id": None,
             "requirement_summary": "ICT testing", "alignment": "PARTIAL", "confidence": "LOW"},
        ],
        "narrative": {"critical_gaps": ["No frequency in BCBS"]},
        "applicability": [{"framework_id": "BCBS-d516", "applicability": "comparative"}],
        "assumptions": ["Profile assumed"],
    })
    xw = Crosswalk(draft=draft, verification=[
        VerificationItem(framework_id="EU-DORA", clause_id=None, reason="Reference not confirmed", check="c")])
    return CrosswalkRun(run_id="xw-000000000001", status="ok", markdown="## Crosswalk", crosswalk=xw)


def test_run_summary_ok():
    text = cv.run_summary(_ok_run())
    assert "2 mappings across 2 frameworks (MEDIUM 1, LOW 1)" in text
    assert "1 items to verify, 1 with reference not confirmed" in text
    assert "No frequency in BCBS" in text and "xw-000000000001" in text


def test_run_summary_not_ok_passes_message_through():
    run = CrosswalkRun(run_id="xw-1", status="refused", markdown="Not run: contains an email address")
    assert cv.run_summary(run).startswith("Not run: contains an email address")


def test_coverage_text_from_real_corpus():
    text = cv.coverage_text(load_corpus().coverage())
    assert "BCBS-d516: heading only 7" in text
    assert "APRA-CPS-230: metadata only" in text


# ── handlers (fake Telegram objects) ──────────────────────────────────────────

class _Msg:
    def __init__(self, text=""):
        self.text = text
        self.replies: list[tuple[str, object]] = []
        self.documents: list[str] = []

    async def reply_text(self, text, reply_markup=None):
        self.replies.append((text, reply_markup))

    async def reply_document(self, document, filename):
        self.documents.append(filename)


class _Query:
    def __init__(self, data, message):
        self.data = data
        self.message = message
        self.edits: list[str] = []

    async def answer(self):
        return None

    async def edit_message_text(self, text, reply_markup=None):
        self.edits.append(text)


def _ctx(args=None):
    return SimpleNamespace(args=args or [], chat_data={})


def _run(coro):
    return asyncio.run(coro)


def test_auth_gate_blocks_unknown_chat(monkeypatch):
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=999))
    with pytest.raises(app.ApplicationHandlerStop):
        _run(app._global_auth_gate(update, _ctx()))


def test_crosswalk_without_args_waits_for_next_message():
    msg, ctx = _Msg(), _ctx()
    _run(app.cmd_crosswalk(SimpleNamespace(message=msg), ctx))
    assert ctx.chat_data[app._AWAITING_KEY] is True
    follow = _Msg("CPS 230 tolerance levels")
    _run(app.handle_text(SimpleNamespace(message=follow), ctx))
    session = ctx.chat_data[app._SESSION_KEY]
    assert session.request == "CPS 230 tolerance levels"
    assert follow.replies[0][1] is not None  # intake keyboard attached


def test_run_callback_sends_document_and_review_buttons(monkeypatch):
    seen = {}

    def fake_run(request, intake):
        seen["request"], seen["intake"] = request, intake
        return _ok_run()

    monkeypatch.setattr(app, "run_crosswalk", fake_run)
    ctx = _ctx(["CPS", "230", "testing"])
    _run(app.cmd_crosswalk(SimpleNamespace(message=_Msg()), ctx))
    ctx.chat_data[app._SESSION_KEY].targets = {"BCBS-d516"}

    msg = _Msg()
    query = _Query("xw|run", msg)
    _run(app.handle_intake_callback(SimpleNamespace(callback_query=query), ctx))

    assert seen["request"] == "CPS 230 testing"
    assert seen["intake"].targets == ["BCBS-d516"]
    assert msg.documents == ["xw-000000000001.md"]
    assert "CROSSWALK READY" in msg.replies[0][0]
    assert app._SESSION_KEY not in ctx.chat_data


def test_expired_session_callback_is_handled():
    query = _Query("xw|run", _Msg())
    _run(app.handle_intake_callback(SimpleNamespace(callback_query=query), _ctx()))
    assert "expired" in query.edits[0]


def test_review_callback_writes_audit(monkeypatch, tmp_path):
    log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("RESILIENCE_AUDIT_LOG", str(log))
    msg = _Msg("CROSSWALK READY")
    query = _Query("rv|xw-000000000001|a", msg)
    _run(app.handle_review_callback(SimpleNamespace(callback_query=query), _ctx()))
    record = json.loads(log.read_text().splitlines()[0])
    assert record == {**record, "type": "review", "run_id": "xw-000000000001", "decision": "accepted"}
    assert audit.read_log(log)[0]["decision"] == "accepted"
    assert "Review recorded: accepted" in query.edits[0]
