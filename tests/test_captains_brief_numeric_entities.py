"""Feed titles can arrive already entity-encoded ("&#x5b;Guest Diary&#x5d;" for "[Guest Diary]").
The brief's single escape turned the "&" into "&amp;", so the entity showed literally in Telegram,
the morning email and the Executive Brief card. Text is now decoded once and escaped once.
"""
import re
from unittest.mock import patch

from intelligence import captains_brief as cb

FEED_TITLE = "&#x5b;Guest Diary&#x5d; Detecting a thing"


def test_esc_decodes_numeric_entities_then_escapes_once():
    assert cb._esc(FEED_TITLE) == "[Guest Diary] Detecting a thing"
    assert cb._esc("&#91;x&#93;") == "[x]"


def test_esc_still_escapes_html_special_characters():
    assert cb._esc("AT&T") == "AT&amp;T"
    assert cb._esc("regarding <NRP> imports") == "regarding &lt;NRP&gt; imports"
    # an entity that decodes to a special character is escaped, not turned into markup
    assert cb._esc("&lt;b&gt;") == "&lt;b&gt;"
    assert cb._esc("&#x3c;script&#x3e;") == "&lt;script&gt;"


def _morning_text(brief, signals):
    with patch.object(cb, "_get_latest_ori_brief", return_value=brief), \
         patch.object(cb, "_get_capacity_today", return_value=None), \
         patch.object(cb, "_get_recent_signals", return_value=signals), \
         patch.object(cb, "_get_infra_verification", return_value=None), \
         patch.object(cb, "build_daily_digest", None):
        return cb.generate_morning_brief()


def test_item_title_and_new_line_show_brackets_not_entities():
    brief = {
        "overall_risk": "MODERATE",
        "top_events": [{"title": FEED_TITLE, "so_what": "Check exposure", "risk_rating": "HIGH"}],
        "comparison": {"new": [{"title": FEED_TITLE}]},
    }
    text = _morning_text(brief, [])
    assert "[Guest Diary] Detecting a thing" in text
    assert "&#x" not in text and "&amp;#" not in text
    new_lines = [line for line in text.split("\n") if "New:" in line]
    assert new_lines and "[Guest Diary]" in new_lines[0]


def test_signals_block_decodes_feed_titles_and_summaries():
    sig = {"raw_title": FEED_TITLE, "raw_summary": "Cost &#x24;5 &amp; more", "risk_rating": "HIGH"}
    text = _morning_text(None, [sig])
    assert "[Guest Diary] Detecting a thing" in text
    assert "&#x" not in text and "&amp;#" not in text
    assert "$5 &amp; more" in text  # decoded once, the ampersand then escaped once


def test_no_entity_text_and_no_raw_markup_in_any_line():
    brief = {"overall_risk": "LOW", "top_events": [{"title": FEED_TITLE + " <NRP>", "so_what": "x", "risk_rating": "HIGH"}]}
    text = _morning_text(brief, [])
    assert not re.search(r"&(?!amp;|lt;|gt;)", text)
    assert not re.search(r"<(?!/?(b|i|code)>)", text)
