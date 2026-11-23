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
