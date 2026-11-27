"""What the framework can and cannot tell apart. SYNTHETIC organisations and events; no model is involved.

Code checks wording against the cited sources. It separates reported facts from invented ones and reported causes from asserted ones.
It cannot tell a well-founded inference from baseless speculation worded the same way: that is the human reasoning review, and the
last tests show an accepted-but-baseless judgement staying out of the brief."""
from datetime import date, timedelta

import pytest

from core.security import public_judgement_route as route
from intelligence import claim_gate as cg
from intelligence import judgement_brief as jb
from intelligence import judgements as jd

DAY = date(2026, 11, 27)
REGULATOR = {"ref": "a", "event_id": "a", "publisher": "example-regulator", "official": True, "source": "Example Regulator",
             "geography": "AU", "published_at": "2026-11-24", "url": "https://example.com.au/rule",
             "title": "Regulator sets one day outage reporting rule for payment providers",
             "summary": "Payment providers must report major outages to the regulator within one day. The rule applies to card and "
                        "account payments."}
NEWS = {"ref": "b", "event_id": "b", "publisher": "example-news", "official": False, "source": "Example News", "geography": "AU",
        "published_at": "2026-11-24", "url": "https://news.example.com/fault",
        "title": "Processor fault stops card payments at three banks",
        "summary": "A fault at the shared processor ExampleSwitch stopped card payments at three banks on Monday. The banks said the "
                   "fault was caused by a failed software update at ExampleSwitch."}
SOURCES = {"a": REGULATOR, "b": NEWS}


def gate(text, field="so_what"):
    evidence = [{"id": s["ref"], "title": s["title"], "summary": s["summary"], "source": s["source"], "canonical_url": s["url"],
                 "published_at": s["published_at"]} for s in SOURCES.values()]
    return cg.validate_text(text, evidence, field=field, mode="enforce").passed


@pytest.mark.parametrize("text", [
    "A fault at the shared processor ExampleSwitch stopped card payments at three banks.",
    "The banks said the fault was caused by a failed software update at ExampleSwitch."])
def test_1_supported_fact_is_accepted_as_a_fact(text):
    assert gate(text, "digest")


@pytest.mark.parametrize("text", ["The fault stopped card payments at seven banks.",
                                  "ExampleSwitch restored card payments at all three banks on Tuesday.",
                                  "ExampleSwitch admitted the software defect."])
def test_2_unsupported_fact_is_rejected_where_facts_are_stated(text):
    assert not gate(text, "digest")


@pytest.mark.parametrize("text", [
    "The three banks share a processor, so one fault at ExampleSwitch may stop card payments at several banks at once.",
    "A shared processor could mean a bank's own resilience testing may not cover the fault that matters most."])
def test_3_evidence_backed_inference_is_accepted_as_analysis(text):
    assert gate(text)


@pytest.mark.parametrize("text", [
    "If another software update at ExampleSwitch fails, card payments at the same banks could stop again.",
    "If the fault is a major outage, the affected payment providers could have to report it within one day."])
def test_4_conditional_forecast_is_accepted(text):
    assert gate(text)


SPECULATION = ["ExampleSwitch may be preparing to leave the payments market.",
               "The banks could face large penalties from the regulator.",
               "If testing was skipped, customer data might have been exposed."]


@pytest.mark.parametrize("text", SPECULATION)
def test_5_speculation_is_rejected_as_fact(text):
    assert not gate(text, "digest")


@pytest.mark.parametrize("text", SPECULATION)
@pytest.mark.xfail(strict=True, reason="code cannot tell hedged speculation from inference; the human reasoning review must")
def test_5_speculation_is_rejected_as_analysis(text):
    assert not gate(text)


@pytest.mark.parametrize("text", ["The reporting rule caused the card payment fault.",
                                  "The fault happened because the banks cut testing budgets.",
                                  "The outage led to losses for retailers."])
def test_6_unsupported_causal_assertion_is_rejected(text):
    assert not gate(text)


# ── a substantive judgement end to end ────────────────────────────────────────

def judgement(**over):
    base = {"area": "sector",
            "assessment": "Card payments at several banks may share one point of failure at ExampleSwitch, which each bank could not "
                          "remove alone.",
            "facts": [{"text": "A fault at the shared processor ExampleSwitch stopped card payments at three banks.", "refs": ["b"]},
                      {"text": "Payment providers must report major outages to the regulator within one day.", "refs": ["a"]}],
            "connection": {"statement": "The shared processor ExampleSwitch stopped card payments at three banks.", "refs": ["b"]},
            "reasoning": "If three banks depend on one processor, a single software update at ExampleSwitch could stop card payments "
                         "at each of them, and each could then face the one day reporting rule.",
            "key_assumption": "The three banks still use ExampleSwitch for card payments.",
            "implications": "Payment providers could need to test a processor fault, not only their own systems.",
            "uncertainty": "Whether the banks have another route is not reported.",
            "competing_explanation": "The fault may be confined to one update and not to the shared arrangement.",
            "indicators": [{"indicator": "A further processor fault", "threshold": "any second event",
                            "check_by": str(DAY + timedelta(days=60))}],
            "review_by": str(DAY + timedelta(days=28))}
    return {**base, **over}


def validate(draft):
    return jd.validate_one(draft, SOURCES, None, DAY)


def test_substantive_inference_is_accepted_and_is_not_a_restated_headline():
    accepted, why = validate(judgement())
    assert accepted, why
    assert accepted["confidence"] == "high" and "point of failure" not in NEWS["title"] + REGULATOR["title"]


@pytest.mark.parametrize("override,reason", [
    ({"assessment": NEWS["title"] + "."}, "restates a headline"),
    ({"reasoning": "The banks lost payments because they cut testing budgets at ExampleSwitch."}, "claim gate"),
    ({"assessment": "Card payments at several banks will stop again at ExampleSwitch."}, "claim gate"),
    ({"review_by": str(DAY + timedelta(days=route.REVIEW_DAYS + 1))}, "review date"),
])
def test_defective_versions_are_rejected(override, reason):
    accepted, why = validate(judgement(**override))
    assert accepted is None and reason in why


def test_baseless_judgement_the_code_accepts_never_reaches_the_brief_without_a_passing_review(tmp_path):
    accepted, why = validate(judgement(implications="The banks could face large penalties from the regulator."))
    assert accepted, why                                                    # the limit of code checking
    register = jd.Register(tmp_path)
    record = {"type": "judgement", "id": "jdg-synspc", "run_date": str(DAY), "first_issued": str(DAY), **accepted}
    register.append([record, {"type": "run", "run_date": str(DAY), "issued": ["jdg-synspc"], "status": "ok", "outcome": "completed"}])
    assert "large penalties" not in "\n".join(jb.section_lines(DAY, register))                 # unreviewed
    register.append([{"type": "review", "id": "jdg-synspc", "facts": "pass", "reasoning": "fail"}])
    assert "large penalties" not in "\n".join(jb.section_lines(DAY, register))                 # failed reasoning review


# ── instructions say what the validator enforces ──────────────────────────────

def test_instructions_state_the_limits_and_wording_rules_and_do_not_offer_hedging_as_proof():
    prompt = route.build_prompt({"as_of": str(DAY), "standing": [], "records": [
        {"event_id": "x", "publisher": "p", "published": str(DAY), "title": "t", "summary": "s"}]})[0]
    text = " ".join(prompt.split("Sources (each line")[0].split())
    for expected in (str(DAY + timedelta(days=route.INDICATOR_DAYS)), str(DAY + timedelta(days=route.REVIEW_DAYS)),
                     'Use "will" only where a cited source says', "say that one thing caused another only when a cited source says so",
                     "only when a cited source reports that change", "do not make a claim supported", "Abstaining is better"):
        assert expected in text, expected


# ── corrected false positives, with guards ───────────────────────────────────

OPENERS = ["Costs", "Delays", "Firms", "Pressure", "Institutions", "Entities", "Boards", "Compliance", "Timeframes", "Obligations",
           "Reliance", "Smaller", "Faster", "Shorter", "Earlier", "Manual", "Without"]


@pytest.mark.parametrize("word", OPENERS)
def test_ordinary_sentence_opener_is_not_an_invented_name(word):
    assert gate(f"{word} may matter for payment providers.")


@pytest.mark.parametrize("text", ["The escalation process could matter for payment providers.",
                                  "Payment providers could need clearer escalation paths."])
def test_escalation_procedure_is_not_a_trend_claim(text):
    assert gate(text)


@pytest.mark.parametrize("text", ["Optus may matter for payment providers.", "Atlassian could be affected.",
                                  "Outages are escalating across payment providers.", "Escalating faults could matter."])
def test_guard_invented_names_and_real_trend_claims_stay_rejected(text):
    assert not gate(text)


REASONABLE = [("assessment", "Banks that use ExampleSwitch may face a shared interruption to card payments."),
              ("reasoning", "If a software update can stop card payments at three banks, a similar change could affect other users."),
              ("implications", "Boards could ask whether one day is enough time to confirm a supplier fault and report it."),
              ("key_assumption", "The reported cause is correct and the processor is still shared."),
              ("uncertainty", "The sources do not say whether the three banks have a second processor."),
              ("competing_explanation", "The interruption might reflect each bank's own configuration rather than the processor."),
              ("indicator", "Regulator guidance on supplier outages"), ("threshold", "guidance that names third party processors")]


@pytest.mark.parametrize("field,text", REASONABLE)
def test_reasonable_analysis_is_not_blocked(field, text):
    from intelligence import judgement_checks

    assert judgement_checks.analytic_problem(field, text, list(SOURCES.values())) == ""
