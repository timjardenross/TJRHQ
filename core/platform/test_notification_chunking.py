"""notify(chunk=True) on a "raw" (Telegram HTML) body must not split inside a tag pair: each chunk
has balanced tags, in order, with the same text (own file so it does not collide with
test_notification_service.py edits)."""

from __future__ import annotations

import pytest

import core.platform.notification_service as ns


@pytest.fixture(autouse=True)
def _reset_sender(monkeypatch):
    calls = []

    def fake_telegram(text, reply_markup=None, chat_id=None, severity=ns.Severity.INFO):
        calls.append({"text": text, "reply_markup": reply_markup, "chat_id": chat_id, "severity": severity})
        return True, None, 12345

    monkeypatch.setitem(ns._SENDERS, ns.Transport.TELEGRAM, fake_telegram)
    ns._CALL_LOG.clear()
    return calls


# ── chunking a "raw" (Telegram HTML) body must not split inside a tag pair ─────

from html.parser import HTMLParser


class _Balance(HTMLParser):
    """Parses a chunk the way Telegram would need it: every opened tag closed, in order."""

    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.ok = True
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.ok = False
        else:
            self.stack.pop()

    def handle_data(self, data):
        self.text.append(data)


def _check_chunk(chunk: str) -> str:
    p = _Balance()
    p.feed(chunk)
    p.close()
    assert p.ok and not p.stack, f"unbalanced chunk: starts {chunk[:60]!r} ends {chunk[-60:]!r}"
    assert len(chunk) <= ns._TELEGRAM_MAX_LEN
    return "".join(p.text)


def _words(s: str) -> list[str]:
    return s.split()


def test_long_nested_html_splits_into_balanced_chunks_in_order(_reset_sender):
    para = "alpha beta gamma delta epsilon " * 40
    body = (
        "<b>HEADER</b>\n"
        + "<b>" + ("bold " * 300) + "<i>" + (para * 6) + "</i> tail of bold</b>\n"
        + "<i>" + ("italic words " * 200) + "</i>\n"
        + "plain trailing text " * 30
    )
    assert len(body) > ns._TELEGRAM_MAX_LEN * 2
    ns.notify(body, template="raw", transport=ns.Transport.TELEGRAM, chunk=True)
    chunks = [c["text"] for c in _reset_sender]
    assert len(chunks) >= 3
    texts = [_check_chunk(c) for c in chunks]
    # same text, same order
    expected = _Balance()
    expected.feed(body)
    assert _words(" ".join(texts)) == _words("".join(expected.text))


def test_split_reopens_the_tags_it_closed():
    body = "<b>" + "word " * 2000 + "</b>"
    chunks = ns._split_html_aware(body, 500)
    assert len(chunks) > 5
    for c in chunks:
        assert c.startswith("<b>") and c.endswith("</b>")
        _check_chunk_len(c, 500)


def _check_chunk_len(chunk: str, limit: int) -> None:
    p = _Balance()
    p.feed(chunk)
    assert p.ok and not p.stack and len(chunk) <= limit


def test_split_never_cuts_inside_a_tag_and_keeps_attributes():
    link = '<a href="https://example.com/a b c">link text here</a>'
    body = ("filler " * 60 + link + " ") * 20
    chunks = ns._split_html_aware(body, 400)
    for c in chunks:
        _check_chunk_len(c, 400)
    joined = "".join(chunks)
    assert joined.count('<a href="https://example.com/a b c">') == 20
    assert all(c.count("<") == c.count(">") for c in chunks)


def test_nested_tags_reopen_in_original_order():
    body = "<b><i>" + "x " * 600 + "</i></b>"
    for c in ns._split_html_aware(body, 300):
        assert c.startswith("<b><i>") and c.endswith("</i></b>")
        _check_chunk_len(c, 300)


def test_short_and_plain_bodies_are_unchanged():
    assert ns._split_html_aware("<b>hi</b> there", 4096) == ["<b>hi</b> there"]
    plain = "no tags " * 1000
    chunks = ns._split_html_aware(plain, 4096)
    assert all(len(c) <= 4096 for c in chunks)
    assert _words(" ".join(chunks)) == _words(plain)


def test_unclosed_tag_in_the_input_is_left_as_written_in_the_last_chunk():
    chunks = ns._split_html_aware("<b>" + "w " * 400, 300)
    assert chunks[-1].startswith("<b>") and not chunks[-1].endswith("</b>")
    assert all(c.endswith("</b>") for c in chunks[:-1])


def test_non_raw_templates_still_use_the_word_splitter(_reset_sender):
    # plain/alert bodies are escaped after the split, so they carry no markup to balance
    ns.notify(("word " * 2000).strip(), template="plain", chunk=True)
    assert len(_reset_sender) > 1
    assert all(len(c["text"]) <= ns._TELEGRAM_MAX_LEN for c in _reset_sender)
