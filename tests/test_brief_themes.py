"""Topic & Theme lane for the Morning brief (Phase 2): flag-gated (default OFF), deterministic, never breaks the brief.

Fixtures replay the real cases that motivated it: the Nvidia/Huang reinstatement (a story the incident picture ignored), a sustained
Anthropic-IPO story, the 'tech outages' running theme, and the false matches the first watchlist produced ('equities outlook', a visa fraud
scheme, 'breach trade rules', a Telstra AFL-draft post).
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import brief_themes as bt
from intelligence import captains_brief as cb

NOW = datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)
FLAGS = (bt.MASTER_FLAG, bt.MORNING_FLAG, "BRIEF_EVIDENCE_V1", "BRIEF_EVIDENCE_V1_MORNING")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in FLAGS:
        monkeypatch.delenv(k, raising=False)


def rep(i, title, source, hours_ago, *, published_hours_ago=None, summary=""):
    stamp = lambda h: (NOW - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"id": str(i), "title": title, "summary": summary, "source": source, "geography": "GLOBAL", "collected_at": stamp(hours_ago),
            "published_at": stamp(hours_ago if published_hours_ago is None else published_hours_ago), "url": f"https://x/{i}"}


def nvidia_story(n_hours=(2, 3, 4, 5, 6, 7, 8, 9)):
    titles = [("Nvidia Rehires Huang in Stunning Comeback", "Bloomberg"),
              ("Analyst Backs Huang’s Return, Cautiously", "Bloomberg"),
              ("Huang’s return is a triumph of money over morals", "Financial Times"),
              ("US lawmakers vow to sharpen Huang probes as he returns to Nvidia", "Financial Times"),
              ("Jensen Huang reinstated as Nvidia chief executive", "ABC News"),
              ("Live: Wall Street roars back as Nvidia's Jensen Huang reinstated", "ABC News Business"),
              ("Jensen Huang reinstated at Nvidia; DV and smart car warnings", "Guardian Australia"),
              ("Nvidia’s Big Rebound Hammers Leveraged Funds Betting on a Fall", "Bloomberg")]
    return [rep(100 + k, t, s, h) for k, ((t, s), h) in enumerate(zip(titles, n_hours, strict=True))]


# ── flag ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_off_by_default_and_for_falsey_values(monkeypatch):
    assert bt.enabled() is False
    for val in ("", "0", "false", "no", "off"):
        monkeypatch.setenv(bt.MORNING_FLAG, val)
        monkeypatch.setenv(bt.MASTER_FLAG, val)
        assert bt.enabled() is False


@pytest.mark.parametrize("flag", [bt.MORNING_FLAG, bt.MASTER_FLAG])
def test_explicit_opt_in_enables(monkeypatch, flag):
    monkeypatch.setenv(flag, "1")
    assert bt.enabled() is True


def test_no_theme_flag_is_set_in_any_committed_deploy_or_service_config():
    hits = []
    for pat in ("deploy", ".github", "systemd"):
        for p in (_REPO / pat).rglob("*") if (_REPO / pat).exists() else []:
            if p.is_file():
                try:
                    if "BRIEF_THEMES" in p.read_text(errors="ignore"):
                        hits.append(str(p))
                except OSError:
                    pass
    assert hits == []


def test_flag_off_reads_nothing():
    def boom(*a, **k):
        raise AssertionError("database read while the theme flag is off")
    assert bt.theme_lines(boom, NOW) == []


# ── watchlist config ──────────────────────────────────────────────────────────────────────────────────────────
def test_the_watchlist_loads_and_every_theme_can_match_something():
    themes = bt.load_watchlist()
    assert len(themes) == 7 and all(t.pillar for t in themes)
    assert all(t.match.pattern != "(?!x)x" for t in themes)
    assert not any(t.match.search("") for t in themes)


# ── stories ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_new_multi_publisher_story_is_surfaced_with_a_lead_that_says_what_happened():
    lane = bt.build_lane(nvidia_story(), NOW)
    assert len(lane.stories) == 1
    s = lane.stories[0]
    assert s.theme == "AI & chips" and s.why == "spike" and s.publishers >= 4
    assert "Nvidia" in s.names or "Huang" in s.names
    direct = {"Nvidia Rehires Huang in Stunning Comeback", "Jensen Huang reinstated as Nvidia chief executive"}
    assert s.lead_title in direct                                                     # a headline that states what happened
    for soft in ("Analyst Backs Huang’s Return, Cautiously", "Live: Wall Street roars back as Nvidia's Jensen Huang reinstated",
                 "Jensen Huang reinstated at Nvidia; DV and smart car warnings", "Huang’s return is a triumph of money over morals"):
        assert s.lead_title != soft                                                    # not analyst chatter, a live blog, a roundup or an opinion


def test_content_feeds_never_count_toward_a_story():
    inc = [rep(300 + k, f"Jensen Huang Is Back at Nvidia: lesson {k}", "Inc. Magazine — Leadership", 2 + k) for k in range(12)]
    assert bt.build_lane(inc, NOW).stories == []


def test_a_sustained_story_is_shown_even_when_it_is_not_a_spike():
    reports = [rep(400 + k, f"Anthropic IPO update {k}: shares trade", src, 1 + k)
               for k, src in enumerate(["Bloomberg", "Financial Times", "ABC News", "Bloomberg", "Financial Times", "ABC News", "BBC News",
                                        "Bloomberg", "Financial Times", "ABC News", "BBC News", "Bloomberg"])]
    reports += [rep(500 + k, "Anthropic IPO preview", "Bloomberg", 26 + 2 * k) for k in range(40)]          # a heavy prior 3 days: no spike
    lane = bt.build_lane(reports, NOW)
    assert [s.why for s in lane.stories] == ["sustained"]


def test_an_old_article_collected_today_is_not_new():
    stale = [rep(600 + k, "Microsoft outage continues with fraud warnings", src, 3, published_hours_ago=24 * 11)
             for k, src in enumerate(["Bloomberg", "Financial Times", "ABC News", "BBC News", "iTnews", "Guardian Australia", "Reuters"])]
    lane = bt.build_lane(stale, NOW)
    assert lane.stories == [] and lane.running == [] and lane.themed_reports == 0         # published 11 days ago: outside the window


def test_published_time_beats_collection_time_for_the_24h_window():
    # collected today but published 40h ago: not part of the last-24h story, though inside the week
    old = [rep(650 + k, "Anthropic IPO prices at $83", src, 2, published_hours_ago=40)
           for k, src in enumerate(["Bloomberg", "Financial Times", "ABC News", "BBC News", "Guardian Australia", "iTnews", "Reuters"])]
    assert bt.build_lane(old, NOW).stories == []


# ── false matches from the first watchlist ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("title", [
    "Rates, stagflation risks cloud Australian equities outlook",
    "Mexican Peso Hits 17-Month Low as Fed Outlook Rattles Markets",
    "How a dodgy visa scheme put a NSW premier's secret partner in jail",
    "Australia Warns China Iron Ore Push Could Breach Trade Rules",
    "Meet Mitchell Harris | 2026 Telstra AFL Draft",
    "Gemini crypto exchange files for IPO",
])
def test_known_false_matches_do_not_match_any_theme(title):
    assert bt.build_lane([rep(1, title, "Bloomberg", 2)], NOW).themed_reports == 0


@pytest.mark.parametrize("title,theme", [
    ("Microsoft says three-month-old bug behind global M365 outage", "Tech outages & resilience"),
    ("Surge in complaints, compensation claims after Telstra outage", "Telco & payments (AU)"),
    ("FBI warns hackers weaponizing AI framework to automate attacks", "Cyber"),
    ("Visa and Mastercard say third-party vendors targeted", "Telco & payments (AU)"),
    ("Anthropic prices blockbuster IPO at $83 a share", "AI & chips"),
])
def test_real_cases_do_match_their_theme(title, theme):
    pool = bt._prepare([rep(1, title, "Bloomberg", 2)], NOW, bt.load_watchlist())
    assert pool and theme in pool[0]["themes"]


# ── running themes ────────────────────────────────────────────────────────────────────────────────────────────
def outage_reports(newest_hours):
    items = [("Australians told to prepare for more disruption after spate of tech outages", "ABC News"),
             ("White House removes cyber-security chief after series of tech outages", "BBC News"),
             ("US tech outages blamed on rush to fix bugs found by AI", "Financial Times"),
             ("Microsoft says bug behind global M365 outage", "iTnews"),
             ("Authorities investigating four-minute Triple Zero outage in Canberra", "ABC News"),
             ("APRA calls Microsoft outage a near miss for financial system", "Insurance Business")]
    return [rep(700 + k, t, s, newest_hours + 20 * k) for k, (t, s) in enumerate(items)]


def test_a_running_theme_needs_new_items_in_the_last_48h_and_shows_one_headline_per_publisher():
    lane = bt.build_lane(outage_reports(newest_hours=5), NOW)
    run = {r.theme: r for r in lane.running}
    assert "Tech outages & resilience" in run
    r = run["Tech outages & resilience"]
    assert r.new_48h >= 1 and r.publishers >= 3 and len(r.picks) <= 2
    assert len({src for src, _ in r.picks}) == len(r.picks)


def test_a_theme_with_nothing_new_in_48h_is_not_shown():
    assert not any(r.theme == "Tech outages & resilience" for r in bt.build_lane(outage_reports(newest_hours=60), NOW).running)


def test_the_lane_is_capped():
    themes = bt.load_watchlist()
    reports = []
    for k, t in enumerate(themes):
        sample = {"AI & chips": "Nvidia news {}", "Tech outages & resilience": "Cloudflare outage {} hits customers", "Cyber": "ransomware attack {} on retailer",
                  "Cloud & data centres": "Equinix data centre {} opens", "Telco & payments (AU)": "Telstra outage {} drives complaints",
                  "AI policy & governance": "eSafety AI safety rules {}", "Work & AI adoption": "AI agents jobs {} workforce"}[t.name]
        for j in range(30):
            reports.append(rep(2000 + k * 100 + j, sample.format(j), ["Bloomberg", "ABC News", "BBC News", "Financial Times"][j % 4], 1 + j % 20))
    lane = bt.build_lane(reports, NOW)
    assert len(lane.stories) <= bt.MAX_STORY_LINES and len(lane.running) <= bt.MAX_RUNNING_LINES


# ── formatting ────────────────────────────────────────────────────────────────────────────────────────────────
def test_an_empty_lane_says_so_instead_of_vanishing():
    lines = bt.format_lane(bt.build_lane([], NOW))
    assert lines[0].startswith("DEVELOPMENTS & THEMES") and "Nothing new in your watched topics" in lines[1]


def test_lines_are_plain_language_and_say_why_they_are_shown():
    lines = bt.format_lane(bt.build_lane(nvidia_story() + outage_reports(5), NOW))
    story = next(line for line in lines if line.startswith("- AI & chips"))
    assert "Coverage is" in story and "independent publisher" in story and story.count("(") == 1
    running = next(line for line in lines if "is active this week" in line)
    assert "Latest:" in running
    # no dashboard numbers: no counts, ratios or averages in the wording
    assert not re.search(r"\d+ reports|\dx|per day|/day|prior-3-day|new in 48h", "\n".join(lines))


def test_the_story_line_names_the_lead_and_how_unusual_coverage_is():
    lane = bt.build_lane(nvidia_story(), NOW)
    s = lane.stories[0]
    assert bt._how_much(s) in ("far above normal", "well above normal", "heavy and sustained across several publishers")
    text = bt.format_lane(lane)[1]
    assert text.startswith("- AI & chips: ") and s.lead_title[:40] in text and s.lead_source in text


@pytest.mark.parametrize("why,ratio,expected", [("spike", 2.5, "well above normal"), ("spike", 4.0, "far above normal"),
                                                ("sustained", 1.0, "heavy and sustained across several publishers")])
def test_how_unusual_wording(why, ratio, expected):
    s = bt.StoryLine("AI & chips", ["Nvidia"], 9, 4, 1.0, ratio, why, "t", "ABC News")
    assert bt._how_much(s) == expected


def test_running_theme_latest_items_prefer_real_publishers_over_aggregators():
    reports = outage_reports(6) + [rep(500, "Telstra outage hits thousands of customers across Victoria", "Google News - Telstra cyber", 3),
                                   rep(501, "Optus outage knocks out services in Sydney", "ABC News", 5)]
    lane = bt.build_lane(reports, NOW)
    picks = [src for r in lane.running for src, _ in r.picks]
    assert picks and all(not src.startswith("Google News") for src in picks[:1])


def test_aggregators_do_not_count_as_independent_publishers():
    # eight reports of one story, but only one non-aggregator publisher: Google News re-serving it is not corroboration
    titles = [f"Nvidia reinstates Jensen Huang as chief executive, report {i}" for i in range(8)]
    reports = [rep(300 + i, t, f"Google News - Source {i}", 2 + i) for i, t in enumerate(titles)]
    reports.append(rep(399, "Nvidia reinstates Jensen Huang as chief executive", "Bloomberg", 2))
    assert bt.build_lane(reports, NOW).stories == []


# ── loading ───────────────────────────────────────────────────────────────────────────────────────────────────
def _row(i):
    return {"event_id": f"e{i}", "raw_title": f"Nvidia report {i}", "raw_summary": "", "geography": "GLOBAL", "collected_at": "2026-11-23T10:00:00Z",
            "published_at": "2026-11-23T09:00:00Z", "canonical_url": "https://x", "intelligence_source_registry": {"source_name": "Bloomberg"}}


def test_load_reports_pages_past_a_single_page_and_dedupes():
    pages = {0: [_row(i) for i in range(bt.PAGE_SIZE)], 1: [_row(i) for i in range(bt.PAGE_SIZE, bt.PAGE_SIZE + 7)] + [_row(0)]}
    seen = []

    def sb(table, query):
        offset = int(query.split("&offset=")[1].split("&")[0])
        seen.append(offset)
        return pages.get(offset // bt.PAGE_SIZE, [])
    out = bt.load_reports(sb, now=NOW)
    assert len(out) == bt.PAGE_SIZE + 7 and seen == [0, bt.PAGE_SIZE]
    assert out[0]["source"] == "Bloomberg" and out[0]["published_at"] == "2026-11-23T09:00:00Z"


def test_load_reports_fails_soft():
    def sb(table, query):
        raise RuntimeError("db down")
    assert bt.load_reports(sb, now=NOW) == []


# ── theme_lines: never silent when it cannot work ─────────────────────────────────────────────────────────────
def test_flag_on_with_no_reports_says_unavailable_not_quiet(monkeypatch):
    monkeypatch.setenv(bt.MORNING_FLAG, "1")
    lines = bt.theme_lines(lambda *a, **k: [], NOW)
    assert "Unavailable" in lines[1] and "should be read as quiet" in lines[1]


def test_flag_on_and_the_builder_failing_is_contained(monkeypatch):
    monkeypatch.setenv(bt.MORNING_FLAG, "1")
    with patch.object(bt, "build_lane", side_effect=RuntimeError("boom")):
        lines = bt.theme_lines(lambda *a, **k: [_row(1)], NOW)
    assert "Unavailable" in lines[1]


# ── integration with the real morning brief ──────────────────────────────────────────────────────────────────
BRIEF = {"overall_risk": "MODERATE", "top_events": [], "comparison": {"new": [], "escalated": [], "improved": []}, "coverage": {"degraded": False}}


def _raw_rows():
    now = datetime.now(timezone.utc)
    out = []
    titles = [("Nvidia Rehires Huang in Stunning Comeback", "Bloomberg"), ("Jensen Huang reinstated as Nvidia chief executive", "ABC News"),
              ("Nvidia’s Big Rebound Hammers Leveraged Funds", "Bloomberg"), ("US lawmakers vow to sharpen Huang probes as he returns to Nvidia", "Financial Times"),
              ("Huang’s return is a triumph of money over morals", "Financial Times"), ("Jensen Huang reinstated at Nvidia", "Guardian Australia"),
              ("AI-Linked Stocks Take Off After Nvidia Restores Jensen Huang", "Bloomberg"), ("Nvidia stock soars as Huang returns", "BBC News")]
    for k, (t, src) in enumerate(titles):
        ts = (now - timedelta(hours=2 + k)).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"event_id": f"n{k}", "raw_title": t, "raw_summary": "", "geography": "GLOBAL", "collected_at": ts, "published_at": ts,
                    "canonical_url": "https://x", "intelligence_source_registry": {"source_name": src}})
    return out


def _morning(monkeypatch, *, themes_on, rows):
    if themes_on:
        monkeypatch.setenv(bt.MORNING_FLAG, "1")
    with patch.object(cb, "_get_latest_ori_brief", return_value=BRIEF), \
         patch.object(cb, "_get_capacity_today", return_value={"has_checked_in": True, "latest_capacity_state": "green"}), \
         patch.object(cb, "_get_recent_signals", return_value=[]), \
         patch.object(cb, "_get_infra_verification", return_value={"state": "ok"}), \
         patch.object(cb, "_sb_get", lambda *a, **k: rows), \
         patch.object(cb, "build_daily_digest", None):
        return cb.generate_morning_brief()


def test_flag_off_the_morning_brief_has_no_theme_lane(monkeypatch):
    text = _morning(monkeypatch, themes_on=False, rows=_raw_rows())
    assert "DEVELOPMENTS &amp; THEMES" not in text and "DEVELOPMENTS & THEMES" not in text


def test_flag_off_output_is_identical_to_the_baseline_without_the_lane(monkeypatch):
    with patch.object(cb, "_theme_lines", return_value=[]):
        baseline = _morning(monkeypatch, themes_on=False, rows=_raw_rows())
    assert _morning(monkeypatch, themes_on=False, rows=_raw_rows()) == baseline


def test_flag_on_the_lane_appears_in_the_morning_brief(monkeypatch):
    text = _morning(monkeypatch, themes_on=True, rows=_raw_rows())
    assert "DEVELOPMENTS &amp; THEMES" in text
    assert "AI &amp; chips" in text and "Nvidia" in text and "Coverage is" in text


def test_flag_on_and_the_lane_crashing_leaves_the_brief_intact(monkeypatch):
    with patch("intelligence.brief_themes.theme_lines", side_effect=RuntimeError("boom")):
        text = _morning(monkeypatch, themes_on=True, rows=_raw_rows())
    assert "MORNING BRIEF" in text and "DEVELOPMENTS" not in text


# ── aggregator-only coverage stays visible but unverified ────────────────────────────────────────────────────────
def _agg_reports(n=8, extra=()):
    titles = [f"Nvidia reinstates Jensen Huang as chief executive, report {i}" for i in range(n)]
    return [rep(300 + i, t, f"Google News - Source {i}", 2 + i) for i, t in enumerate(titles)] + list(extra)


def _lines(reports):
    return bt.format_lane(bt.build_lane(reports, NOW))


def test_aggregator_only_surge_is_shown_as_unverified_never_corroborated():
    lane = bt.build_lane(_agg_reports(), NOW)
    assert lane.stories == [] and not lane.empty
    text = "\n".join(bt.format_lane(lane))
    assert "(seen only through aggregators so far; unverified)" in text and "Nvidia" in text
    assert "independent publisher" not in text and "Coverage is" not in text


def test_one_independent_publisher_plus_aggregators_is_counted_as_one_only():
    lines = _lines(_agg_reports(extra=[rep(399, "Nvidia reinstates Jensen Huang as chief executive", "Bloomberg", 2)]))
    text = "\n".join(lines)
    assert "unverified" in text and "independent publishers" not in text and "other independent" not in text
    assert "1 independent publisher" in text and "aggregators" in text


def test_unverified_lines_are_capped_at_two():
    reports = _agg_reports() + [rep(700 + i, f"Telstra outage hits customers again, report {i}", f"Google News - Feed {i}", 2 + i) for i in range(8)] \
        + [rep(800 + i, f"OpenAI releases model update, report {i}", f"Google News - Wire {i}", 2 + i) for i in range(8)]
    assert sum("unverified" in l for l in _lines(reports)) <= bt.MAX_UNVERIFIED_LINES == 2


def test_no_aggregator_content_leaves_output_unchanged():
    lines = bt.format_lane(bt.build_lane(nvidia_story(), NOW))
    assert not any("unverified" in l for l in lines) and any("independent publisher" in l for l in lines)
    assert bt.format_lane(bt.build_lane([], NOW)) == ["DEVELOPMENTS & THEMES (what moved in your watched topics)", "- Nothing new in your watched topics."]


def test_content_feeds_never_count_even_as_aggregator_style_lift():
    reports = [rep(900 + i, f"Nvidia reinstates Jensen Huang as chief executive, report {i}", f"Psychology Today {i}", 2 + i) for i in range(8)]
    assert bt.build_lane(reports, NOW).empty


def test_aggregator_only_running_theme_is_unverified_not_active():
    reports = [rep(950 + i, f"Telstra outage hits customers, report {i}", f"Google News - Feed {i}", 3 + 30 * (i % 3)) for i in range(6)]
    lane = bt.build_lane(reports, NOW)
    assert lane.running == [] and lane.unverified and "unverified" in "\n".join(bt.format_lane(lane))
