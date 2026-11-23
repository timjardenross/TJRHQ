"""#669 (morning-quality concern 2): an international incident needs demonstrated Australian relevance or dependency before it
is escalated into the Australian operational brief.

Written to FAIL on the pre-fix behaviour: 'Explosion on Russian ship at Libya port' and 'US ports face wave of cyberattacks'
(collected as GLOBAL) reached VERIFY in the Australian morning brief with nothing connecting them to Australia.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from intelligence import brief_evidence as be
from intelligence import event_detection as ed

NOW = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)
ACTIONABLE = ("ESCALATE", "VERIFY", "WATCH")


def e(i, title, source, age_hours=3, geo="GLOBAL"):
    return {"id": i, "title": title, "source": source, "geography": geo, "summary": "",
            "collected_at": (NOW - timedelta(hours=age_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def one(events):
    ds = ed.run(events, now=NOW)
    assert len(ds) == 1, [sorted(m.event_id for m in d.group.members) for d in ds]
    return ds[0]


def core(events):
    cands = [ed.detect_candidate(x) for x in events]
    return next(ed._decide_core(g, now=NOW) for g in ed.correlate(cands))


LIBYA = "Explosion on Russian ship at Libya port likely caused by drone attack, officials say"
US_PORTS = "US ports face wave of cyberattacks as Los Angeles blocks 120 million attempts - Gulf News"


def test_a_global_physical_incident_with_no_australian_link_is_kept_as_reference():
    evs = [e("a", LIBYA, "BBC News")]
    assert core(evs).priority in ACTIONABLE                                  # the gate is what changes it (pre-fix: VERIFY)
    d = one(evs)
    assert d.priority == "REFERENCE"
    assert any("no demonstrated Australian relevance" in r for r in d.reasons)


def test_a_global_cyber_incident_with_no_australian_link_is_kept_as_reference():
    evs = [e("a", US_PORTS, "Google News - Critical Infrastructure/Energy Cyberattack AU")]
    assert core(evs).priority in ACTIONABLE
    assert one(evs).priority == "REFERENCE"


def test_an_incident_naming_australia_or_an_australian_organisation_is_kept():
    for title in ("Qantas systems outage disrupts flights across Europe and Asia",
                  "Cyberattack on Sydney hospital network disrupts services"):
        evs = [e("a", title, "ABC News")]
        d = one(evs)
        assert d.priority == core(evs).priority and d.priority in ACTIONABLE, title
        assert any(r.startswith("Australian relevance") for r in d.reasons)


def test_a_global_platform_outage_is_an_australian_dependency():
    evs = [e("a", "Microsoft Azure outage disrupts services worldwide for thousands of customers", "BBC News")]
    d = one(evs)
    assert d.priority == core(evs).priority and d.priority in ACTIONABLE
    assert any("depends on a global platform" in r for r in d.reasons)


def test_a_payments_platform_outage_is_an_australian_dependency():
    """Found in the real-export audit: an Apple Pay outage hitting retailers was demoted by the first version of the gate."""
    evs = [e("a", "Apple Pay outage a difficult situation for retailers in Black Friday sales mode - SmartCompany", "SmartCompany")]
    d = one(evs)
    assert d.priority == core(evs).priority and d.priority in ACTIONABLE
    assert any("depends on a global platform" in r for r in d.reasons)


def test_an_australian_audience_outlet_is_editorial_relevance_never_operational_impact():
    """Captain: Australian publisher identity can support editorial relevance but must not alone establish Australian operational impact."""
    mand = [e("a", "Staff didn\u2019t work because of an outage on Friday\u2026 did somebody say SLA? - The Mandarin", "The Mandarin")]
    assert core(mand).priority in ACTIONABLE
    d = one(mand)
    assert d.priority == "WATCH"                                            # visible, but capped
    assert any("editorial relevance" in r and "not established" in r for r in d.reasons)
    assert not any(r.startswith("Australian relevance") for r in d.reasons)  # and never recorded as operational relevance
    g = ed.correlate([ed.detect_candidate(mand[0])])[0]
    assert ed.australian_relevance(g) is None and ed.australian_editorial_relevance(g)


def test_an_outlet_only_incident_is_never_escalated_or_verified_by_its_outlet():
    for src, title in (("The Mandarin", "Cyberattack disrupts government payments system - The Mandarin"),
                       ("SmartCompany", "Cyberattack on retailer takes online store offline - SmartCompany"),
                       ("Google News - Government", "Cyberattack disrupts agency systems - The Mandarin")):
        evs = [e("a", title, src)]
        if core(evs).priority in ACTIONABLE:
            assert one(evs).priority in ("WATCH", "REFERENCE"), title


def test_general_outlets_are_not_even_editorial_relevance():
    for src in ("BBC News", "iTWire"):
        assert one([e("a", LIBYA, src)]).priority == "REFERENCE", src


def test_australian_geography_is_relevance_enough():
    evs = [e("a", "Power outage hits 20,000 customers in SA", "ABC News", geo="AU")]
    d = one(evs)
    assert d.priority == core(evs).priority
    assert any("australian geography" in r for r in d.reasons)


def test_one_australian_report_makes_the_whole_incident_relevant():
    evs = [e("a", "Telstra mobile outage leaves customers unable to make calls", "ABC News", 4, geo="AU"),
           e("b", "Telstra mobile network outage across Australia, customers unable to make calls", "The Guardian", 3, geo="GLOBAL")]
    d = one(evs)
    assert d.priority in ACTIONABLE


def test_vulnerability_advisories_are_exempt_from_the_geography_gate():
    evs = [e("a", "CISA adds actively exploited critical remote code execution flaw in Acme router to KEV catalog", "CISA")]
    c = ed.detect_candidate(evs[0])
    if c and c.is_candidate:
        assert one(evs).priority == core(evs).priority


def test_ordinary_english_words_are_not_platform_dependencies():
    """'visa', 'swift' and 'square' are common words; they must not make an unrelated international story Australian."""
    for title in ("US visa processing outage disrupts consulates", "Taylor Swift concert venue power outage in Chicago",
                  "Power outage hits Times Square in New York"):
        c = ed.detect_candidate(e("a", title, "BBC News"))
        if c and c.is_candidate:
            assert one([e("a", title, "BBC News")]).priority == "REFERENCE", title


def test_reference_items_gain_no_extra_reason_noise():
    d = one([e("a", "Telstra reports half-year profit rise as dividend lifted", "ABC News", geo="GLOBAL")])
    assert d.priority == "REFERENCE"
    assert not any("Australian" in r for r in d.reasons)


def test_australian_relevance_helper_reports_why():
    def g(title, geo="GLOBAL"):
        return ed.correlate([ed.detect_candidate(e("a", title, "BBC News", geo=geo))])[0]
    assert ed.australian_relevance(g(LIBYA)) is None
    assert ed.australian_relevance(g("Outage hits Optus customers", "GLOBAL")) == "names Australia or an Australian organisation"
    assert ed.australian_relevance(g("Any title here with an outage", "AU")) == "australian geography"
    assert ed.australian_relevance(g("Cloudflare outage takes sites offline")) == "depends on a global platform used in Australia"


def test_the_morning_view_no_longer_lists_the_unrelated_international_incidents():
    ev = be.build_evidence([e("a", LIBYA, "BBC News"), e("b", US_PORTS, "Google News - Critical Infrastructure/Energy Cyberattack AU", 4)],
                           now=NOW, window_hours=72)
    text = "\n".join(be.morning_view(ev))
    assert "Libya" not in text and "US ports" not in text


# ── Captain's check 2: credible dependencies by category; summaries; provider status pages ───────────────────────────
def _kept(title, source="BBC News", summary=""):
    ev = e("a", title, source)
    ev["summary"] = summary
    d = one([ev])
    return d.priority in ACTIONABLE and any("depends on a global platform" in r or r.startswith("Australian relevance") for r in d.reasons)


def test_credible_dependencies_are_kept_in_each_category():
    cases = {
        "cloud": "Cloudflare outage takes thousands of websites offline worldwide",
        "payments": "Mastercard network outage leaves cardholders unable to pay in shops worldwide",
        "telecommunications": "Internet outage across Asia after undersea cable cut",
        "critical software": "Fortinet customers hit by outage after cyberattack",
        "supply chain": "Maersk hit by cyberattack, port terminals disrupted",
    }
    for cat, title in cases.items():
        ev = e("a", title, "BBC News")
        assert core([ev]).priority in ACTIONABLE, cat                       # the underlying rules surface it (the gate is the test)
        d = one([ev])
        assert d.priority == core([ev]).priority, cat                       # and the gate does not demote it
        assert any("depends on a global platform" in r for r in d.reasons), cat


def test_a_providers_own_status_page_is_a_dependency_report():
    """Found in the audit: 'Gateway availability disruption' from Supabase Status (a dependency of this platform) was hidden."""
    ev = e("a", "Gateway availability disruption", "Supabase Status")
    ev["summary"] = "Between 18:00 and 18:20 UTC, an upstream provider experienced an issue that affected gateway availability for some customers."
    assert core([ev]).priority in ACTIONABLE
    d = one([ev])
    assert d.priority in ACTIONABLE and any("depends on a global platform" in r for r in d.reasons)


def test_the_summary_can_demonstrate_relevance_or_dependency():
    """Found in the audit: two US 'series of tech outages' stories name Microsoft only in their summary."""
    ev = e("a", "US tech outages blamed on rush to fix bugs found by AI", "Financial Times")
    ev["summary"] = "Experts say a race to patch software flaws likely created instability in computer systems at Microsoft, JPMorgan, the FAA and others"
    assert core([ev]).priority in ACTIONABLE
    assert one([ev]).priority in ACTIONABLE
    ev2 = e("a", LIBYA, "BBC News")
    ev2["summary"] = "Australian-flagged vessels were also in the port at the time."
    assert one([ev2]).priority in ACTIONABLE


def test_a_summary_with_no_link_changes_nothing():
    ev = e("a", LIBYA, "BBC News")
    ev["summary"] = "The ship was moored at the port when the blast occurred, officials said."
    assert one([ev]).priority == "REFERENCE"


def test_unverified_third_party_software_is_not_assumed_to_be_an_australian_dependency():
    """Optimizely Web is credible critical software, but nothing shows Australian use, so it stays for human review."""
    ev = e("a", "Cyberattack via Optimizely Web exposes banking, media and insurance websites to malware - Beinsure", "Google News - Critical Infrastructure/Energy Cyberattack AU")
    ev["summary"] = "Cyberattack via Optimizely Web exposes banking, media and insurance websites to malware"
    if core([ev]).priority in ACTIONABLE:
        assert one([ev]).priority == "REFERENCE"


def test_generic_words_are_not_markers():
    """'ASIC' (chips) and 'nab' (the verb) are not Australian markers; bare 'visa' / 'swift' / 'square' are not dependencies."""
    for title in ("Bitcoin ASIC miners lose power in Texas blackout", "Police nab suspect after Ohio blackout cuts power to thousands",
                  "US visa processing outage disrupts consulates", "Power outage hits Times Square in New York"):
        c = ed.detect_candidate(e("a", title, "BBC News"))
        if c and c.is_candidate:
            assert one([e("a", title, "BBC News")]).priority == "REFERENCE", title


# ── Codex review findings (P2 ×3) ───────────────────────────────────────────────────────────────────────────

def test_microsoft_product_names_without_the_provider_are_a_dependency():
    for title in ("Global Outlook outage leaves millions of users unable to access email", "M365 outage takes services offline worldwide"):
        assert core([e("a", title, "BBC News")]).priority in ACTIONABLE
        assert one([e("a", title, "BBC News")]).priority in ACTIONABLE, title


def test_an_australian_outlet_name_in_the_aggregator_suffix_does_not_establish_relevance():
    for outlet in ("The Australian", "Guardian Australia"):
        d = one([e("a", f"{US_PORTS.rsplit(' - ', 1)[0]} - {outlet}", "Google News - Critical Infrastructure/Energy Cyberattack AU")])
        assert d.priority == "REFERENCE", outlet


def test_an_outlet_name_repeated_in_the_summary_does_not_establish_relevance():
    ev = e("a", "US ports face wave of cyberattacks as Los Angeles blocks 120 million attempts - The Australian",
           "Google News - Critical Infrastructure/Energy Cyberattack AU")
    ev["summary"] = "US ports face wave of cyberattacks &nbsp;The Australian"
    assert one([ev]).priority == "REFERENCE"


def test_a_demoted_incident_is_not_published_as_a_dated_forward_watch_notice():
    ev = e("a", "Planned power outage in Chicago on 24/11/2026", "BBC News")
    es = be.build_evidence([ev], now=NOW, window_hours=72)
    assert es.incidents[0].priority == "REFERENCE"
    assert be.forward_dated_items(es) == []
    assert "Chicago" not in "\n".join(be.morning_view(es))


def test_a_direct_source_dash_clause_is_content_not_a_publisher_suffix():
    """Codex P2: only an aggregator's trailing ' - Outlet' is attribution; a BBC headline's own dash clause can carry the dependency."""
    d = one([e("a", "Global email outage - Microsoft investigates disruption", "BBC News")])
    assert d.priority in ACTIONABLE, d.reasons


def test_a_direct_source_dash_clause_is_headline_content_not_a_publisher_suffix():
    """Codex P2: 'Global email outage - Microsoft investigates disruption' (BBC, GLOBAL) lost 'Microsoft' as a fake publisher suffix."""
    ev = e("a", "Global email outage - Microsoft investigates disruption", "BBC News")
    assert core([ev]).priority in ACTIONABLE
    d = one([ev])
    assert d.priority == core([ev]).priority and any("depends on a global platform" in r for r in d.reasons)
