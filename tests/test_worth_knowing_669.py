"""#669 — WORTH KNOWING: credible, relevant technology developments that do not meet an escalation threshold."""
from datetime import datetime, timezone

from intelligence import brief_evidence as be

NOW = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)


def _ev(i, title, source, summary="", hours_ago=6, geography="Global"):
    ts = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc).timestamp() - (hours_ago - 6) * 3600 + i * 60
    return {"id": f"w{i}", "title": title, "summary": summary, "source": source, "geography": geography,
            "collected_at": datetime.fromtimestamp(ts, timezone.utc).isoformat(), "url": f"https://example.org/{i}"}


def _wk(events):
    es = be.build_evidence(events, now=NOW, window_hours=72)
    return es, be.worth_knowing(es)


def _heads(items):
    return [i.headline for i, _, _ in items]


def test_credible_specialist_technology_story_is_included_without_any_outage():
    es, items = _wk([_ev(1, "Researchers detail new phishing technique aimed at enterprise cloud accounts", "iTnews",
                         "The technique abuses legitimate sign-in prompts. Researchers recommend phishing-resistant authentication.")])
    assert _heads(items) == ["Researchers detail new phishing technique aimed at enterprise cloud accounts"]
    assert items[0][0].priority == "REFERENCE"      # selection never changes priority
    lines = "\n".join(be.worth_knowing_lines(es))
    assert "WORTH KNOWING" in lines and "single-source report" in lines and "[inc-" in lines


def test_disposition_brief_noise_is_not_mapped_in():
    _, items = _wk([_ev(1, "Bellamy to end Storm coaching stint after 2027 NRL season", "ABC News"),
                    _ev(2, "Seven in 10 MPs say politics has damaged their mental health", "ABC News"),
                    _ev(3, "Diversa pays $1,009,800 APRA penalty over superannuation failures", "Financial Newswire")])
    assert items == []


def test_actionable_incidents_stay_in_their_own_sections_not_worth_knowing():
    es, items = _wk([_ev(1, "Researchers disclose critical vulnerability in widely used router firmware", "iTnews",
                         "A flaw allows remote code execution on unpatched devices.")])
    assert es.incidents[0].priority in ("WATCH", "VERIFY", "ESCALATE") and items == []


def test_editorial_quality_excludes_promotional_awards_howto_and_speculative_headlines():
    heads = ["Deloitte Tech Fast 50 highlights strong growth among local tech firms",
             "How to protect your cloud accounts from ransomware in five steps",
             "Could Iran-linked cyberattacks reach Europe's homes and critical infrastructure?",
             "Best cybersecurity software deals this week for small business owners"]
    _, items = _wk([_ev(i, h, "ZDNet") for i, h in enumerate(heads, 1)])
    assert items == []


def test_company_results_and_funding_news_are_not_technology_intelligence():
    _, items = _wk([_ev(1, "Arinco sees growth as AI agents reshape delivery of cloud services", "ARN",
                        "Arinco has achieved 26.8 per cent year-on-year revenue growth across the region."),
                    _ev(2, "Record Anthropic IPO set to trigger global cash crunch for AI models", "Financial Newswire")])
    assert items == []


def test_ai_is_a_technology_subject_not_a_market_talking_point():
    _, items = _wk([_ev(1, "Barclays nervously overweight equities on AI strength", "Financial Newswire"),
                    _ev(2, "Tech suppliers raise AI server prices up to 45% months after deals are signed", "Financial Times")])
    assert _heads(items) == ["Tech suppliers raise AI server prices up to 45% months after deals are signed"]


def test_aggregator_only_and_unverified_items_are_excluded():
    _, items = _wk([_ev(1, "Malware campaign targets cloud servers worldwide - Some Outlet", "Google News - Cyber")])
    assert items == []


def test_international_item_is_labelled_not_dropped_and_australian_named_item_is_labelled():
    es, items = _wk([_ev(1, "Undersea cable cut slows Pacific telecommunications traffic for carriers", "iTnews"),
                     _ev(2, "Telstra and Optus face scrutiny over mobile network resilience planning", "iTnews")])
    text = "\n".join(be.worth_knowing_lines(es))
    assert "no Australian operational impact established" in text
    assert "Australian relevance stated in report" in text
    assert len(items) == 2


def test_publisher_identity_alone_does_not_make_it_australian():
    es, _ = _wk([_ev(1, "Chipmaker discloses firmware vulnerability affecting server boards", "ABC News")])
    assert "Australian relevance stated" not in "\n".join(be.worth_knowing_lines(es))


def test_retrospective_report_is_labelled_and_never_described_as_ongoing():
    es, items = _wk([_ev(1, "Post-mortem: how a cloud provider outage last month cascaded across customers", "iTnews",
                         "The provider published its root cause analysis of the incident, which ended weeks ago.")])
    text = "\n".join(be.worth_knowing_lines(es)).lower()
    if items:
        assert "retrospective report" in text
    assert "ongoing" not in text and "restoration" not in text


def test_limit_and_per_category_cap_and_recency_window():
    titles = [f"Researchers detail phishing technique {c} aimed at enterprise cloud accounts" for c in "ABCDEFG"]
    events = [_ev(i, t, "iTnews") for i, t in enumerate(titles, 1)]
    events.append(_ev(99, "Researchers detail older phishing technique aimed at enterprise software suites", "iTnews", hours_ago=100))
    _, items = _wk(events)
    assert 1 <= len(items) <= 5
    assert sum(1 for _, c, _ in items if c == "cyber") <= 2
    assert all("Old critical" not in i.headline for i, _, _ in items)


def test_existing_priorities_are_unchanged_by_selection():
    events = [_ev(1, "Researchers detail new phishing technique aimed at enterprise cloud accounts", "iTnews")]
    before = [(i.incident_id, i.priority, i.evidence_status) for i in be.build_evidence(events, now=NOW, window_hours=72).incidents]
    es = be.build_evidence(events, now=NOW, window_hours=72)
    be.worth_knowing_lines(es)
    assert [(i.incident_id, i.priority, i.evidence_status) for i in es.incidents] == before


def test_morning_view_carries_the_section_last_and_stays_short():
    events = [_ev(i, f"Researchers detail phishing technique {c} aimed at enterprise cloud accounts", "iTnews") for i, c in enumerate("ABCDEFG", 1)]
    view = be.morning_view(be.build_evidence(events, now=NOW, window_hours=72))
    idx = [n for n, ln in enumerate(view) if ln.startswith("WORTH KNOWING")]
    assert len(idx) == 1 and idx[0] > max(n for n, ln in enumerate(view) if ln.startswith("Forward watch"))
    assert len(view[idx[0]:]) <= 1 + 5 + 1
