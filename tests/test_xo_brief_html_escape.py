"""XO /brief must escape database-derived text before sending it as Telegram HTML.

Regression: a stored brief containing redaction placeholders such as "<NRP>" made Telegram
reject the whole message ("Can't parse entities: unsupported start tag "nrp"").
"""
import asyncio
import importlib
import importlib.util
import sys
import types
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (_REPO_ROOT, _REPO_ROOT / "telegram-bots", _REPO_ROOT / "telegram-bots" / "xo"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

_ALLOWED_TAGS = {"b", "i"}


class _TagCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def _tags_in(message: str) -> list[str]:
    c = _TagCollector()
    c.feed(message)
    return c.tags


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return types.SimpleNamespace(data=self._rows)


def _load_xo_app():
    """Load telegram-bots/xo/app.py under a private module name (the capacitybot also has an `app`)."""
    name = "xo_app_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _REPO_ROOT / "telegram-bots" / "xo" / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run_brief(brief_overrides: dict) -> list[dict]:
    from intelligence.brief.morning_cycle import cycle_id_for

    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "1"}):
        app = _load_xo_app()
    row = {
        "morning_cycle_id": cycle_id_for(),
        "brief_id": "abcd1234efgh",
        "generated_at": "2026-10-14T19:05:51+00:00",
        "period_start": "2026-10-13T00:00:00",
        "period_end": "2026-10-14T00:00:00",
        "overall_risk": "MODERATE",
        "executive_snapshot": "Plain snapshot",
        "bottom_line": "Plain bottom line",
        "emerging_themes": [],
        "forward_watch": None,
        "top_events": [],
        "comparison": None,
        "coverage": None,
        "events_included": 3,
        "events_evaluated": 5,
        "sources_checked": 7,
        "narrative_available": True,
    }
    row.update(brief_overrides)
    db = MagicMock()
    db.table.side_effect = lambda _name: _FakeQuery([row])
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = 1
    context = MagicMock()
    view = {
        "what_matters": [
            {"title": "Sanctions on <NRP> diesel imports", "so_what": "affects <ORGANIZATION> obligations"},
            {"title": "A normal title", "so_what": "a normal reason"},
        ],
        "changed": {"new": ["New <NRP> item"], "escalated": [], "improved": []},
        "coverage_note": "Coverage gap for <ORGANIZATION>",
    }
    voice = types.ModuleType("core.voice.tts_edge")
    voice.send_voice_reply = AsyncMock()
    with patch.object(app, "_get_supabase", return_value=db), \
         patch("intelligence.brief.render.build_morning_intelligence_view", return_value=view), \
         patch.dict(sys.modules, {"core.voice.tts_edge": voice}):
        asyncio.run(app.cmd_brief(update, context))
    return [c for c in update.message.reply_text.call_args_list]


def _sent_html(calls) -> str:
    return next(c.args[0] for c in calls if c.kwargs.get("parse_mode") == "HTML")


def test_placeholders_in_every_field_are_escaped_not_parsed_as_tags():
    calls = _run_brief({
        "bottom_line": "Risk of <NRP> and <ORGANIZATION> exposure",
        "executive_snapshot": "Snapshot with <NRP>",
        "emerging_themes": ["Theme <ORGANIZATION>"],
        "forward_watch": "Watch <NRP> & <ORGANIZATION>",
    })
    msg = _sent_html(calls)
    assert set(_tags_in(msg)) <= _ALLOWED_TAGS, _tags_in(msg)
    assert "&lt;NRP&gt;" in msg and "&lt;ORGANIZATION&gt;" in msg
    assert "Watch &lt;NRP&gt; &amp; &lt;ORGANIZATION&gt;" in msg
    assert "<NRP>" not in msg and "<ORGANIZATION>" not in msg


def test_normal_brief_keeps_its_bold_and_italic_wrappers():
    calls = _run_brief({})
    msg = _sent_html(calls)
    assert _tags_in(msg).count("b") >= 3
    assert "i" in _tags_in(msg)
    assert "<b>Bottom Line</b>" in msg
    assert "Plain bottom line" in msg and "A normal title" in msg
    assert "&lt;" not in msg.replace("&lt;NRP&gt;", "").replace("&lt;ORGANIZATION&gt;", "")
