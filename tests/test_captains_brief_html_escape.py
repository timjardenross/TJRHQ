"""The Captain's briefs are sent as Telegram HTML via notify(template="raw"), which does not
escape the body. Every builder must escape its own dynamic text.

Regression: a stored intelligence brief whose text contained redaction placeholders such as
"<NRP>" or "<ORGANIZATION>" would make Telegram reject the whole message ("unsupported start
tag"), failing the push with only a logged error.
"""
from html.parser import HTMLParser
from unittest.mock import patch

from intelligence import captains_brief as cb

_ALLOWED_TAGS = {"b", "i", "code"}
NRP = "regarding <NRP> imports"
ORG = "and <ORGANIZATION> obligations & more"


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def _tags(text: str) -> set[str]:
    p = _Tags()
    p.feed(text)
    return set(p.tags)


def _ok(lines) -> str:
    text = lines if isinstance(lines, str) else "\n".join(lines)
    assert _tags(text) <= _ALLOWED_TAGS, _tags(text)
    assert "<NRP>" not in text and "<ORGANIZATION>" not in text
    return text


# ── individual builders ───────────────────────────────────────────────────────

def test_signals_block_escapes_title_and_commentary():
    sig = {"raw_title": f"Sanctions {NRP}", "raw_summary": f"Summary {ORG}", "risk_rating": "HIGH"}
    text = _ok(cb._format_signals_block([sig], "📡 OTHER SIGNALS (24h)"))
    assert "&lt;NRP&gt;" in text and "&lt;ORGANIZATION&gt;" in text and "&amp; more" in text
    assert "<b>📡 OTHER SIGNALS (24h)</b>" in text


def test_midday_update_escapes_titles():
    text = _ok(cb.generate_midday_update([{"raw_title": f"Title {NRP}", "risk_rating": "HIGH"}]))
    assert "&lt;NRP&gt;" in text


def test_infra_block_escapes_narrative():
    text = _ok(cb._format_infra_block({"state": "unsure", "narrative": f"Check {NRP} {ORG}"}))
    assert "&lt;NRP&gt;" in text


def test_infra_unchanged_marker_still_matches_the_persisted_escaped_text():
    infra = {"state": "unsure", "narrative": f"Check {NRP}"}
    morning = "\n".join(cb._format_infra_block(infra))  # what the morning send persisted
    eod = "\n".join(cb._format_infra_block(infra, morning))
    assert "(unchanged since this morning)" in eod


def test_capacity_block_escapes_state_labels_and_checkin_label():
    cap = {
        "has_checked_in": True, "latest_capacity_state": "green",
        "latest_regulation_state": "set<NRP>tled", "latest_executive_function": "go<ORGANIZATION>od",
        "checkin_label": f"Check-in {NRP}",
    }
    text = "\n".join(cb._format_capacity_block(cap))
    assert _tags(text) <= _ALLOWED_TAGS
    assert "&lt;NRP&gt;" in text


def test_weekly_osint_block_escapes_summary_headlines_and_caveat():
    rows = [{"confidence_field": "HIGH", "raw_title": f"Headline {NRP}", "rank_score": 1}]
    with_summary = _ok(cb._format_weekly_osint_block(
        "TECH OSINT", "🛰", rows, "confidence_field", "raw_title", summary=f"Summary {ORG}"))
    assert "&lt;ORGANIZATION&gt;" in with_summary
    fallback = _ok(cb._format_weekly_osint_block("TECH OSINT", "🛰", rows, "confidence_field", "raw_title"))
    assert "&lt;NRP&gt;" in fallback
    empty = _ok(cb._format_weekly_osint_block(
        "HEALTH OSINT", "🩺", [], "confidence_field", "title", empty_caveat=f"Collector {NRP}"))
    assert "&lt;NRP&gt;" in empty


def test_weekly_content_and_outage_blocks_escape():
    content = _ok(cb._format_weekly_content_block(
        [{"title": f"Post {NRP}", "status": "re<ORGANIZATION>view", "pillar": "a<NRP>b"}]))
    assert "&lt;NRP&gt;" in content
    outage = _ok(cb._format_weekly_outage_alerts_block(
        [{"outcome": "sent", "details": {"event_title": f"Outage {NRP}", "customer_impact": "hi<ORGANIZATION>gh", "confidence": 0.9}}]))
    assert "&lt;ORGANIZATION&gt;" in outage


def test_weekly_capacity_block_escapes_all_three_sources():
    log_ = _ok(cb._format_weekly_capacity_block(
        {"source": "log", "entries": [{"captain_capacity_rating": "gr<NRP>een"}]}))
    pulse = _ok(cb._format_weekly_capacity_block(
        {"source": "pulse", "entries": [{"log_date": "2026-10-14", "energy": "hi<NRP>gh"}]}))
    checkin = _ok(cb._format_weekly_capacity_block(
        {"source": "checkin", "entries": [{"log_date": "2026-10-14", "capacity_state": "or<ORGANIZATION>ange"}]}))
    # .capitalize() in the builders lower-cases the rest of the word, so compare case-insensitively
    assert "&lt;nrp&gt;" in log_.lower() and "&lt;nrp&gt;" in pulse.lower() and "&lt;organization&gt;" in checkin.lower()


def test_intelligence_posture_block_escapes_what_matters_changed_and_coverage():
    brief = {
        "overall_risk": "MODERATE",
        "top_events": [{"title": "A normal title", "so_what": f"secondary sanctions {NRP} {ORG}", "risk_rating": "HIGH"}],
        "comparison": {"new": [{"title": f"New {NRP}"}], "escalated": [], "improved": []},
        "coverage": {"degraded": True, "reason": f"Degraded {ORG}"},
    }
    text = _ok(cb._format_intelligence_posture_block(brief))
    assert "A normal title — secondary sanctions regarding &lt;NRP&gt; imports" in text
    assert "&lt;ORGANIZATION&gt;" in text and "- New: New regarding &lt;NRP&gt; imports" in text
    assert "<b>📡 INTELLIGENCE POSTURE</b>" in text and "<b>What matters today</b>" in text


def test_weekly_debrief_digest_escapes_user_text():
    logs = [{"stressors": [f"Stress {NRP}"], "follow_up_candidate": f"Call {ORG}", "change_talk": None},
            {"stressors": [f"Stress {NRP}"]}]
    with patch.object(cb, "_get_recent_debrief_logs", return_value=logs):
        text = _ok(cb.generate_weekly_debrief_digest())
    assert "&lt;NRP&gt;" in text and "<b>😣 RECURRING STRESSORS</b>" in text


# ── whole morning brief, end to end ───────────────────────────────────────────

def test_morning_brief_with_placeholders_everywhere_is_valid_telegram_html():
    brief = {
        "overall_risk": "MODERATE",
        "top_events": [{"title": "Title", "so_what": f"x {NRP} {ORG}", "risk_rating": "HIGH"}],
    }
    capacity = {"has_checked_in": True, "latest_capacity_state": "green", "checkin_label": f"label {NRP}"}
    signals = [{"raw_title": f"Signal {NRP}", "raw_summary": f"S {ORG}", "risk_rating": "HIGH"}]
    with patch.object(cb, "_get_latest_ori_brief", return_value=brief), \
         patch.object(cb, "_get_capacity_today", return_value=capacity), \
         patch.object(cb, "_get_recent_signals", return_value=signals), \
         patch.object(cb, "_get_infra_verification", return_value={"state": "unsure", "narrative": f"N {NRP}"}), \
         patch.object(cb, "build_daily_digest", None):
        text = _ok(cb.generate_morning_brief())
    assert text.count("&lt;NRP&gt;") >= 3
    assert "<b>☀️ MORNING BRIEF" in text


def test_plain_text_passes_through_unchanged():
    sig = {"raw_title": "GitHub Status: Degraded performance", "raw_summary": "Plain summary.", "risk_rating": "HIGH"}
    text = "\n".join(cb._format_signals_block([sig], "📡 OTHER SIGNALS (24h)"))
    assert "GitHub Status: Degraded performance" in text and "Plain summary." in text
    assert "&" not in text
