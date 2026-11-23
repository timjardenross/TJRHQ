"""#669 — WORTH KNOWING: credible, relevant technology developments that do not meet an escalation threshold."""
from dataclasses import replace
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


def test_an_aggregator_item_attributed_to_a_specialist_outlet_is_allowed_and_labelled_as_such():
    es = be.build_evidence([_ev(1, "FBI warns hackers weaponizing AI framework to automate attacks on energy, manufacturing, telecom - Industrial Cyber",
                                "Google News - Critical Infrastructure/Energy Cyberattack AU")], now=NOW, window_hours=72)
    es.incidents = [replace(i, priority="REFERENCE") for i in es.incidents]       # as the Australian-relevance gate (#677) demotes it
    items = be.worth_knowing(es)
    assert len(items) == 1 and items[0][0].evidence_status == "unverified"
    line = "\n".join(be.worth_knowing_lines(es))
    assert "single source via aggregator feed (publisher: industrial cyber)" in line


def test_a_hedged_aggregator_item_is_still_excluded():
    es = be.build_evidence([_ev(1, "Hackers reportedly weaponizing AI framework to automate attacks on energy, telecom - Industrial Cyber",
                                "Google News - Critical Infrastructure/Energy Cyberattack AU")], now=NOW, window_hours=72)
    es.incidents = [replace(i, priority="REFERENCE") for i in es.incidents]
    assert be.worth_knowing(es) == []


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


# ── Clean summaries and attribution ─────────────────────────────────────────────────────────────────────────────

def _line_for(title, source, summary):
    es = be.build_evidence([_ev(1, title, source, summary)], now=NOW, window_hours=72)
    es.incidents = [replace(i, priority="REFERENCE") for i in es.incidents]
    return "\n".join(be.worth_knowing_lines(es)), es


def test_a_summary_ends_at_a_complete_sentence_never_mid_sentence():
    long_first = ("Energy authorities warned the government that its plan to attract more data centres would present a major structural "
                  "challenge to the state's electricity network, according to documents seen by the newspaper over the weekend. Second sentence.")
    text, _ = _line_for("Energy officials warned of data centre risk to the state electricity network", "Bloomberg", long_first)
    assert "…" not in text and "Energy authorities warned" not in text          # too long for one clean sentence: omitted, not cut
    ok = "Energy authorities warned that the plan would present a major structural challenge to the grid. More detail follows later."
    text, _ = _line_for("Energy officials warned of data centre risk to the state electricity network", "Bloomberg", ok)
    assert "Energy authorities warned that the plan would present a major structural challenge to the grid." in text
    assert "More detail follows" not in text


def test_abbreviations_do_not_end_a_sentence_early():
    text, _ = _line_for("US regulators warn cloud providers over concentration of critical workloads", "Financial Times",
                        "The U.S. regulator told cloud providers to report concentration risk by March. A second sentence follows here.")
    assert "The U.S. regulator told cloud providers to report concentration risk by March." in text


def test_an_official_confirmation_names_who_confirmed():
    text, _ = _line_for("Vulnerabilities in nginx Affecting Cisco Products: November 2026", "Cisco Security Advisories",
                         "On November 18, 2026, nginx announced the availability of a fix for multiple critical vulnerabilities in nginx. Cisco is evaluating its products.")
    assert "officially confirmed by Cisco Security Advisories" in text
    assert "On November 18, 2026, nginx announced the availability of a fix for multiple critical vulnerabilities in nginx." in text


def test_same_development_from_two_publishers_uses_one_slot():
    _, items = _wk([_ev(1, "OpenAI releases new AI model for enterprise customers", "iTnews", "The model targets enterprise software teams building agents."),
                    _ev(2, "OpenAI releases new AI model for enterprise customers", "Reuters", "The model targets enterprise software teams building agents.")])
    assert len(items) == 1


def test_summary_hedge_or_anonymous_sourcing_excludes_item():
    _, items = _wk([_ev(1, "OpenAI prepares new AI model release for enterprise customers", "iTnews",
                        "Unnamed sources say the company may have developed a new model for enterprise customers.")])
    assert items == []


def test_ambiguous_cloud_and_payments_words_need_technology_context():
    _, items = _wk([_ev(1, "Rare cloud formations create spectacular sunset over Sydney", "ABC News"),
                    _ev(2, "Trump promises new tariff payments to American households", "Reuters")])
    assert items == []
    _, items = _wk([_ev(3, "Provider adds new sovereign cloud region for government agencies", "iTnews",
                        "The region keeps workloads onshore for regulated customers.")])
    assert len(items) == 1


def test_non_profit_description_is_not_company_results():
    _, items = _wk([_ev(1, "Linux Foundation launches new software security initiative", "iTnews",
                        "The non-profit organisation launched a new programme to harden open-source software projects.")])
    assert len(items) == 1


def test_aggregator_headline_with_detector_hedge_words_is_not_admitted():
    for head in ("OpenAI likely to release new AI model for enterprise customers", "Anonymous sources: OpenAI new AI model for enterprise customers"):
        _, items = _wk([_ev(1, head + " - iTnews", "Google News - AI")])
        assert items == [], head


def test_similar_headlines_naming_different_vendors_are_separate_developments():
    """Codex P2: 'OpenAI releases new AI model ...' and 'Anthropic releases new AI model ...' are two launches, not duplicate coverage."""
    _, items = _wk([_ev(1, "OpenAI releases new AI model for enterprise customers", "iTnews"),
                    _ev(2, "Anthropic releases new AI model for enterprise customers", "Financial Times")])
    assert len(items) == 2


def test_the_same_vendor_reported_by_two_publishers_is_still_one_development():
    _, items = _wk([_ev(1, "OpenAI releases new AI model for enterprise customers", "iTnews"),
                    _ev(2, "OpenAI releases new AI model for enterprise customers this week", "Financial Times")])
    assert len(items) == 1
