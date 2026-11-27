"""The original independent review's nine reproductions against baseline 1fd85ea3. Synthetic and in memory."""
from datetime import date, timedelta

import pytest

from core.security import public_judgement_route as route
from intelligence import judgement_checks as checks
from intelligence import judgements as jd

DAY = date(2026, 11, 27)


def source(ref, title, summary="", *, publisher="", official=False, name="Example News"):
    return {"ref": ref, "event_id": ref, "publisher": publisher or ref, "official": official, "source": name, "geography": "AU",
            "title": title, "summary": summary or title, "published_at": "2026-11-24", "url": f"https://example.com.au/{ref}"}


NORTHSTAR = "Banks depend on shared supplier Northstar for card payments"
OFFICIAL = source("a", NORTHSTAR, official=True, name="APRA")
PRESS = source("b", "Lenders route card transactions through Northstar", "Industry figures show several lenders send card traffic "
                                                                       "through Northstar.")
FERRY = source("f", "Ferry operators share a fuel supplier", "Ferry operators share a fuel supplier for harbour services.")
EVIDENCE = [OFFICIAL, PRESS]


def draft(**over):
    base = {"area": "sector", "assessment": "Card payments at the banks could be exposed to the same interruption.",
            "facts": [{"text": NORTHSTAR + ".", "refs": ["a"]}],
            "reasoning": "If both banks use the shared supplier, a supplier outage could cause simultaneous disruption to card payments.",
            "key_assumption": "The reported arrangement is still current.",
            "connection": {"statement": NORTHSTAR + ".", "refs": ["a"]}, "australian_relevance": "",
            "implications": "Correlated failure is plausible.", "uncertainty": "Whether there is another route is not reported.",
            "competing_explanation": "The arrangement may be narrower than reported.",
            "indicators": [{"indicator": "A further report", "threshold": "any", "check_by": str(DAY + timedelta(days=30))}],
            "review_by": str(DAY + timedelta(days=20))}
    return {**base, **over}


def validate(**over):
    return jd.validate_one(draft(**over), {"a": OFFICIAL, "b": PRESS, "f": FERRY}, None, DAY)


def test_1_text_removed_before_sending_cannot_support_anything():
    prompt, refs = route.build_prompt({"as_of": str(DAY), "standing": [], "records": [
        {"event_id": "a", "publisher": "p", "published": "2026-11-24", "title": "Bank card outage", "summary": "Card payments stopped."}]})
    local = [{"sources": [source("a", "Bank card outage", "Card payments stopped. Northstar admitted a defect in its ledger.")]}]
    shown = jd.shown_sources(route.projection(prompt), refs, local, {})
    assert "admitted" not in shown["a"]["summary"]
    assert not jd._gate("Northstar admitted a defect in its ledger.", [shown["a"]], "digest")


def test_2_denying_a_reported_dependence_is_a_contradiction():
    text = "Card payments carry no concentration exposure through the shared supplier."
    assert checks.analytic_problem("assessment", text, EVIDENCE) == "contradicts the cited evidence"


def test_3_conditional_inference_and_a_plausibility_judgement_are_accepted():
    accepted, why = validate()
    assert accepted, why


@pytest.mark.parametrize("text", ["A supplier outage caused simultaneous disruption to card payments.",
                                  "Card payments stopped because the banks cut testing.",
                                  "The disruption could be due to budget cuts at Northstar.",
                                  "Northstar admitted the defect, which could recur.",
                                  "A supplier outage at Atlassian could cause disruption to card payments."])
def test_3_guard_asserted_or_explanatory_causes_and_fabrications_stay_rejected(text):
    assert checks.analytic_problem("reasoning", text, EVIDENCE)


def test_4_an_unrelated_sourced_link_does_not_satisfy_the_connection():
    accepted, why = validate(connection={"statement": "Ferry operators share a fuel supplier.", "refs": ["f"]})
    assert accepted is None and "connection" in why


def test_5_a_fabricated_assumption_is_rejected():
    accepted, why = validate(key_assumption="A regulator had revoked 9999 banking licences in Atlantis.")
    assert accepted is None and why.startswith("key_assumption")


def test_6_publication_date_is_not_the_incident_date():
    delay = source("d", "Card payments delayed for customers", "Card payments were delayed for customers of a bank.")
    assert not jd._gate("Card payments were delayed on 24 November.", [delay], "digest")


def test_7_one_dispatch_under_two_publisher_labels_is_one_origin():
    text = ("Card payments delayed at lenders", "Card payments were delayed for customers of several lenders, the dispatch said.")
    level, basis = jd.confidence_for([source("x", *text, publisher="one"), source("y", *text, publisher="two")])
    assert level is None and basis.startswith("1 independent")


def test_8_an_unrelated_citation_cannot_close_a_judgement():
    open_ = {"jdg-synaaa": {"id": "jdg-synaaa", "assessment": "Card payments could be exposed.", "evidence": [OFFICIAL],
                            "review_by": "2026-12-10"}}
    reply = {"retire": [{"id": "jdg-synaaa", "status": "closed", "reason": "no longer true", "refs": ["f"]}]}
    records, _ = jd.apply_reply(reply, [], open_, DAY, sources={"a": OFFICIAL, "f": FERRY})
    assert [r["type"] for r in records] == ["retire_proposal"]


def test_9_an_empty_object_is_malformed_not_abstention():
    with pytest.raises(jd.DraftUnavailable) as caught:
        jd.parse_reply("{}")
    assert caught.value.outcome == "malformed_reply"
