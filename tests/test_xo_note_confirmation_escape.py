"""XO /note: the confirmation is sent as HTML, so the echoed note must be HTML-escaped.

Regression: the confirmation used the MarkdownV2 escaper, so a note containing "<" or ">" made
Telegram reject the confirmation (and the handler then reported "Capture failed" although the
note had been saved), and ordinary punctuation showed stray backslashes.
"""
import asyncio
import importlib.util
import sys
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (_REPO_ROOT, _REPO_ROOT / "telegram-bots", _REPO_ROOT / "telegram-bots" / "xo"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _load_xo_app():
    """Load telegram-bots/xo/app.py under a private module name (the capacitybot also has an `app`)."""
    name = "xo_app_note_under_test"
    if name in sys.modules:
        return sys.modules[name]
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "1"}):
        spec = importlib.util.spec_from_file_location(name, _REPO_ROOT / "telegram-bots" / "xo" / "app.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def _run_note(args: list[str]):
    app = _load_xo_app()
    db = MagicMock()
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.message_id = 42
    context = MagicMock()
    context.args = args
    with patch.object(app, "_get_supabase", return_value=db):
        asyncio.run(app.cmd_note(update, context))
    return db, update.message.reply_text.call_args_list


def test_confirmation_escapes_angle_brackets_and_ampersand():
    _db, calls = _run_note(["a<b", "c>d", "&", "e&amp;f"])
    msg = calls[-1].args[0]
    assert calls[-1].kwargs["parse_mode"] == "HTML"
    tags = _Tags()
    tags.feed(msg)
    assert set(tags.tags) <= {"b", "i"}, tags.tags
    assert "a&lt;b c&gt;d &amp; e&amp;amp;f" in msg
    assert "Capture failed" not in msg


def test_confirmation_has_no_markdownv2_backslashes():
    _db, calls = _run_note(["Follow", "up", "(draft)", "-", "v1.2!"])
    msg = calls[-1].args[0]
    assert "Follow up (draft) - v1.2!" in msg
    assert "\\" not in msg


def test_the_note_is_still_saved_exactly_as_typed():
    db, _calls = _run_note(["a<b", "c>d", "&", "(x)", "-", "1.5!"])
    inserted = db.table.return_value.insert.call_args.args[0]
    assert inserted["raw_text"] == "a<b c>d & (x) - 1.5!"
    assert inserted["title"] == "a<b c>d & (x) - 1.5!"
    assert inserted["item_type"] == "text_note"
    assert inserted["processing_status"] == "pending"
    db.table.assert_called_with("captured_items")


def test_long_note_is_truncated_before_escaping():
    # 199 chars then "<": the 200-char cut keeps one "<", which must come out as the whole entity "&lt;".
    note = "x" * 199 + "<" + "tail"
    _db, calls = _run_note([note])
    msg = calls[-1].args[0]
    assert ("x" * 199 + "&lt;") in msg
    assert "tail" not in msg
