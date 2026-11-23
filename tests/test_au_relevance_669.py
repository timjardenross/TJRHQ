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


def capped(priority):
    """A dependency-only incident (no Australian impact evidence) is never above VERIFY."""
    return "VERIFY" if priority == "ESCALATE" else priority


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
    assert d.priority == capped(core(evs).priority) and d.priority in ACTIONABLE
    assert any("plausible dependency on" in r for r in d.reasons)


def test_a_payments_platform_outage_is_an_australian_dependency():
    """Found in the real-export audit: an Apple Pay outage hitting retailers was demoted by the first version of the gate."""
    evs = [e("a", "Apple Pay outage a difficult situation for retailers in Black Friday sales mode - SmartCompany", "SmartCompany")]
    d = one(evs)
    assert d.priority == capped(core(evs).priority) and d.priority in ACTIONABLE
    assert any("plausible dependency on" in r for r in d.reasons)


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
    assert ed.australian_relevance(g("Cloudflare outage takes sites offline")) == "plausible dependency on Cloudflare (Australian impact not established)"


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
    return d.priority in ACTIONABLE and any("plausible dependency on" in r or r.startswith("Australian relevance") for r in d.reasons)


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
        assert d.priority == capped(core([ev]).priority), cat               # and the gate does not demote it (it only caps ESCALATE at VERIFY)
        assert any("plausible dependency on" in r for r in d.reasons), cat


def test_a_providers_own_status_page_is_a_dependency_report():
    """Found in the audit: 'Gateway availability disruption' from Supabase Status (a dependency of this platform) was hidden."""
    ev = e("a", "Gateway availability disruption", "Supabase Status")
    ev["summary"] = "Between 18:00 and 18:20 UTC, an upstream provider experienced an issue that affected gateway availability for some customers."
    assert core([ev]).priority in ACTIONABLE
    d = one([ev])
    assert d.priority in ACTIONABLE and any("plausible dependency on" in r for r in d.reasons)


def test_the_summary_can_demonstrate_relevance_or_dependency():
    """Found in the audit: two US 'series of tech outages' stories name Microsoft only in their summary."""
    ev = e("a", "US tech outages blamed on rush to fix bugs found by AI", "Financial Times")
    ev["summary"] = "Experts say a race to patch software flaws likely created instability in computer systems at Microsoft, JPMorgan, the FAA and others"
    assert core([ev]).priority in ACTIONABLE
    assert one([ev]).priority in ACTIONABLE
    ev2 = e("a", LIBYA, "BBC News")
    ev2["summary"] = "Australian-flagged vessels were also damaged in the blast."
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
    assert d.priority == capped(core([ev]).priority) and any("plausible dependency on" in r for r in d.reasons)


# ── Release review (HIGH): a dependency must be tied to the AFFECTED service ────────────────────────────────────────
def test_a_communication_channel_mention_in_the_summary_is_not_a_dependency():
    ev = e("a", "Power outage leaves 200,000 customers without electricity in Texas", "BBC News")
    ev["summary"] = "The utility posted an update on Microsoft Teams."
    assert core([ev]).priority in ACTIONABLE
    d = one([ev])
    assert d.priority == "REFERENCE", d.reasons
    assert not any("plausible dependency" in r for r in d.reasons)


def test_a_summary_sentence_describing_the_platform_disrupted_still_counts():
    ev = e("a", "Widespread collaboration outage reported by businesses worldwide", "BBC News")
    ev["summary"] = "Users report a Microsoft Teams outage affecting messaging and calls."
    assert core([ev]).priority in ACTIONABLE
    d = one([ev])
    assert d.priority in ACTIONABLE, d.reasons
    assert any("plausible dependency on Microsoft" in r for r in d.reasons), d.reasons


def test_a_plausible_dependency_is_worded_as_unproven_and_a_proven_link_is_not():
    d = one([e("a", "Global Outlook outage disrupts email for millions", "BBC News")])
    assert d.priority in ACTIONABLE
    assert any(r.startswith("Australian relevance: plausible dependency on ") and r.endswith("(Australian impact not established)")
               for r in d.reasons), d.reasons
    d2 = one([e("a", "Outage hits Optus customers", "BBC News")])
    assert "Australian relevance: names Australia or an Australian organisation" in d2.reasons


# ── Independent review round 2 ────────────────────────────────────────────────────────────────────────────────────
def _final(title, summary="", src="BBC News", geo="GLOBAL"):
    ev = e("a", title, src, geo=geo)
    ev["summary"] = summary
    return core([ev]).priority, one([ev])


def test_a_platform_in_the_headline_must_itself_be_what_is_disrupted():
    """1: a platform used as a channel, or named beside an unrelated physical event, is not a dependency."""
    for title in ("Texas power outage hits Microsoft Teams users after grid failure", "Hospital outage in Houston, Texas; staff used Zoom",
                  "Cisco warns of outage in Houston plant", "Oracle plant fire causes outage in Texas"):
        before, d = _final(title)
        assert before in ACTIONABLE, title
        assert d.priority == "REFERENCE", (title, d.reasons)
        assert not any("plausible dependency" in r for r in d.reasons), title


def test_a_dependency_only_match_is_never_escalated():
    before, d = _final("Blackout hits Texas, Slack down")
    assert before == "ESCALATE" and d.priority == "VERIFY", d.reasons
    assert any("capped at VERIFY" in r for r in d.reasons)
    # negative control: a proven Australian link is not capped
    assert _final("Blackout hits Sydney, NSW")[1].priority == "ESCALATE"


def test_a_genuine_platform_outage_still_passes_as_a_plausible_dependency():
    for title in ("Microsoft 365 outage hits Outlook users", "Cloudflare outage takes thousands of websites offline", "Microsoft Azure outage after data centre fire"):
        d = _final(title)[1]
        assert d.priority in ("VERIFY", "WATCH"), (title, d.reasons)
        assert any("plausible dependency on" in r for r in d.reasons), title


def test_ambiguous_place_names_followed_by_a_foreign_region_are_not_australian():
    """2"""
    for title in ("Major outage at Sydney, Nova Scotia hospital", "Power outage across Adelaide, Michigan",
                  "Ransomware attack hits Perth, Scotland council", "Power outage in Darwin, Montana", "Power outage in Melbourne, Florida",
                  "Power outage in Victoria, British Columbia", "Blackout in Newcastle upon Tyne", "Power outage hits Victoria Falls Zimbabwe"):
        before, d = _final(title)
        assert before in ACTIONABLE and d.priority == "REFERENCE", (title, d.reasons)
    g = ed.correlate([ed.detect_candidate(e("a", "Outage at Perth Amboy New Jersey substation", "BBC News"))])
    assert not g or ed.australian_relevance(g[0]) is None
    # negative controls: the Australian readings, and an Australian co-signal, still count
    for title in ("Power outage in Melbourne, Victoria", "Blackout in Sydney, NSW", "Power outage in Perth, Western Australia",
                  "Power outage in Adelaide, SA", "Outage across Sydney, Nova Scotia and NSW"):
        assert _final(title)[1].priority in ACTIONABLE, title


def test_a_dateline_or_bureau_credit_and_a_passing_summary_mention_are_not_australian_impact():
    """3"""
    title = "Major outage at refinery plant leaves thousands without fuel"
    for summary in ("SYDNEY (Reuters) - Fuel supply was disrupted at the plant on Monday.",
                    "The plant outage was reported by the Sydney bureau of the agency."):
        assert _final(title, summary)[1].priority == "REFERENCE", summary
    assert _final("Airline systems outage hits passengers in Europe", "Qantas passengers unaffected, the airline said.")[1].priority == "REFERENCE"
    # negative control: a summary sentence that reports an Australian incident still counts
    assert _final("Airline systems outage hits passengers in Europe", "Qantas flights were cancelled after the outage.")[1].priority in ACTIONABLE


def test_real_australian_impacts_are_not_demoted():
    """4"""
    for title in ("Power outage hits Victoria", "Blackout hits Gold Coast and Newcastle", "Aussie telco outage", "Cyberattack on NAB disrupts services",
                  "Endeavour Energy outage leaves thousands without power", "Cyberattack on Transurban disrupts tolling",
                  "Outage hits Cairns and Townsville", "Outage hits Geelong and Wollongong", "Ergon Energy outage in the north",
                  "Energex outage leaves homes without power"):
        d = _final(title)[1]
        assert d.priority in ACTIONABLE, (title, d.reasons)
        assert any(r.startswith("Australian relevance: names") for r in d.reasons), title
    # negative controls: the verb 'nab' is not the bank
    assert _final("Police nab suspect after Ohio blackout cuts power to thousands")[1].priority == "REFERENCE"


def test_geography_must_be_exactly_au():
    def rel(geo):
        return ed.australian_relevance(ed.correlate([ed.detect_candidate(e("a", "Outage hits customers across the region", "BBC News", geo=geo))])[0])
    assert rel("AU") == "australian geography" and rel("au") == "australian geography"
    assert rel("AUT") is None and rel("AUSTRIA") is None


# ---- Codex round 3 (P2 x4) ----
def _with_summary(title, summary=""):
    ev = e("a", title, "BBC News")
    ev["summary"] = summary
    return [ev]


def test_attack_or_outage_on_a_platform_is_a_dependency_incident_at_the_verify_cap():
    for title in ("Cyberattack on Microsoft disrupts services worldwide", "Global outage on AWS leaves millions of users offline"):
        evs = _with_summary(title)
        d = one(evs)
        assert core(evs).priority == "ESCALATE", title
        assert d.priority == "VERIFY", title
        assert any("plausible dependency on" in r for r in d.reasons)


def test_a_platform_used_as_a_channel_is_still_not_a_dependency():
    for title in ("Hospital outage in Houston, Texas; staff used Zoom", "Power outage in Ohio as officials chatted on Zoom"):
        assert one(_with_summary(title)).priority == "REFERENCE", title


def test_an_organisation_name_containing_bureau_keeps_its_australian_marker():
    for title, summary in (("Cyberattack disrupts Australian Bureau of Statistics systems", ""),
                           ("Australian Bureau of Meteorology outage disrupts weather services", ""),
                           ("Global outage disrupts services", "The Australian Bureau of Statistics said its systems were hit by the outage.")):
        evs = _with_summary(title, summary)
        d = one(evs)
        assert d.priority == core(evs).priority and d.priority in ACTIONABLE, title
        assert any("names Australia" in r for r in d.reasons)


def test_a_bureau_byline_credit_is_still_stripped():
    d = one(_with_summary("Cyberattack hits firm", "Sydney bureau staff said. Reporting by Reuters Sydney bureau."))
    assert d.priority == "REFERENCE"


def test_a_platform_stated_down_is_a_dependency_even_with_a_physical_cause_named():
    for title in ("Power failure knocks Microsoft Azure offline worldwide", "Cloudflare outage takes hospital websites offline worldwide"):
        evs = _with_summary(title)
        d = one(evs)
        assert core(evs).priority == "ESCALATE", title
        assert d.priority == "VERIFY", title


def test_a_physical_event_with_an_incidental_platform_is_still_vetoed():
    for title in ("Oracle plant fire causes outage in Texas", "Cisco warns of outage in Houston plant"):
        assert one(_with_summary(title)).priority == "REFERENCE", title


def test_a_summary_that_denies_impact_does_not_establish_australian_relevance():
    for summary in ("Australian ports were not affected by the cyberattack.", "Qantas passengers unaffected by the outage.",
                    "Services in Australia had no impact from the outage.", "Australian operations were spared."):
        evs = _with_summary("Cyberattack disrupts ports across Europe after outage", summary)
        assert core(evs).priority in ACTIONABLE
        assert one(evs).priority == "REFERENCE", summary


def test_a_summary_that_affirms_impact_still_establishes_australian_relevance():
    evs = _with_summary("Cyberattack disrupts ports across Europe", "Australian ports were also affected by the cyberattack.")
    assert one(evs).priority in ACTIONABLE


# --- geography=AU is a weak keyword tag (classifier.py), not proof the event is in Australia -----------------------------------

def eg(i, title, summary, geo="AU", source="Reuters"):
    x = e(i, title, source, geo=geo)
    x["summary"] = summary
    return x


def test_au_geography_does_not_override_an_explicit_australia_not_affected_denial():
    evs = [eg("a", "California port outage halts container terminals at Los Angeles and Long Beach",
              "Australian ports were not affected.")]
    assert core(evs).priority in ACTIONABLE
    assert ed.australian_relevance(next(iter(ed.correlate([ed.detect_candidate(evs[0])])))) is None
    d = one(evs)
    assert d.priority == "REFERENCE" and d.priority != "ESCALATE"


def test_au_geography_alone_is_weak_when_text_names_a_foreign_place_and_no_australian_marker():
    evs = [eg("a", "Port outage halts container terminals in Los Angeles", "Operators are restoring systems.")]
    assert one(evs).priority == "REFERENCE"


def test_genuine_australian_impact_with_au_geography_still_passes():
    for title, summary in (("Port of Melbourne outage halts container terminals", "Terminal operators are investigating."),
                           ("Telstra outage leaves customers unable to make calls", "")):
        evs = [eg("a", title, summary)]
        d = one(evs)
        assert d.priority == core(evs).priority and d.priority in ACTIONABLE, title


def test_au_geography_with_no_denial_and_no_foreign_marker_is_unchanged():
    evs = [eg("a", "Power outage hits 20,000 customers in SA", "Crews are working to restore supply.")]
    d = one(evs)
    assert d.priority == core(evs).priority
    assert any("australian geography" in r for r in d.reasons)
