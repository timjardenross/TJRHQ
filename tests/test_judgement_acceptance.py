"""Acceptance: the real outbound boundary, prompt builder, redaction, projection and validator together. Only the model and the record
store are replaced. SYNTHETIC organisations and events throughout."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from core.security import llm_guardrails as guard
from core.security import public_judgement_route as route
from intelligence import brief_evidence as be
from intelligence import judgement_brief as jb
from intelligence import judgements as jd

NOW = datetime(2026, 11, 27, 1, 0, tzinfo=timezone.utc)
DAY = NOW.astimezone(jd.TZ).date()
_IDS = {name: sid for sid, name in route.allowlist().items()}
OFFICIAL = next(n for n in _IDS if n.startswith("APRA"))
PRESS, OTHER_PRESS = "ABC News", next(n for n in _IDS if n.startswith("iTnews"))
RULE = ("Regulator sets one day outage reporting rule for payment providers",
        ("Payment providers must report major outages to the regulator within one day. The rule applies to card and account payments."))
FAULT = ("Processor fault stops card payments at three banks",
         ("A fault at the shared processor ExampleSwitch stopped card payments at three banks. The banks said the fault was caused by "
          "a failed software update at ExampleSwitch."))


def uid(n):
    return f"0000000{n}-0000-0000-0000-000000000000"


def world(*reports):
    """reports: (n, source name, title, summary). Returns (evidence set, record store reader)."""
    events, rows = [], {}
    for n, source, title, summary in reports:
        published = (NOW - timedelta(days=2)).isoformat()
        events.append({"id": uid(n), "title": title, "summary": summary, "source": source, "geography": "AU", "published_at": published,
                       "collected_at": NOW.isoformat(), "url": f"https://example{n}.com.au/story"})
        rows[uid(n)] = {"event_id": uid(n), "source_id": _IDS[source], "raw_title": title, "raw_summary": summary,
                        "published_at": published, "canonical_url": f"https://example{n}.com.au/story", "suppressed": False}

    def reader(table, query):
        if table == "intelligence_events":
            return [r for e, r in rows.items() if e in query]
        return [{"source_id": sid, "source_name": name, "active": True} for name, sid in _IDS.items() if sid in query]

    return be.build_evidence(events, now=NOW, window_hours=72), reader


STANDARD = ((1, OFFICIAL, *RULE), (2, PRESS, *FAULT))


@pytest.fixture(autouse=True)
def isolated_register(tmp_path_factory, monkeypatch):
    """The router reads standing judgements from its own state directory: never the host's during a test."""
    monkeypatch.setenv(jd.DIR_ENV, str(tmp_path_factory.mktemp("router-state")))


class Model:
    """Stands where the router and model do: real prepare, prompt, redaction and projection; then a scripted reply."""

    redact = False                      # the real screening engine takes seconds a call: one test switches it on

    def __init__(self, reader, reply):
        self.reader, self.reply, self.prompt = reader, reply, ""

    def __call__(self, request):
        prepared = route.prepare(request, reader=self.reader, detector=lambda text: [])
        prompt, refs = route.build_prompt(prepared)
        sent = guard.redact_pii(prompt, preserve_entities=route.PRESERVE).redacted_text if self.redact else prompt
        self.prompt = sent
        shown = route.projection(sent)
        by_title = {v["title"][:12]: ref for ref, v in shown["records"].items()}
        ref = {"rule": by_title.get(RULE[0][:12], "src-zzz"), "fault": by_title.get(FAULT[0][:12], "src-zzz")}
        return json.dumps(self.reply(ref, shown)), refs, prepared["dropped"], shown


def draft(ref, **over):
    base = {"id": None, "area": "sector",
            "assessment": "Card payments at several banks may share one point of failure at ExampleSwitch, which each bank could not "
                          "remove alone.",
            "facts": [{"text": "A fault at the shared processor ExampleSwitch stopped card payments at three banks.",
                       "refs": [ref["fault"]]},
                      {"text": "Payment providers must report major outages to the regulator within one day.", "refs": [ref["rule"]]}],
            "reasoning": "If three banks depend on one processor, a single software update at ExampleSwitch could stop card payments "
                         "at each of them, and each could then face the one day reporting rule.",
            "key_assumption": "The three banks still use ExampleSwitch for card payments.",
            "connection": {"statement": "The shared processor ExampleSwitch stopped card payments at three banks.", "refs": [ref["fault"]]},
            "australian_relevance": "", "implications": "Payment providers could need to test a processor fault, not only their own "
                                                        "systems.",
            "uncertainty": "Whether the banks have another route is not reported.",
            "competing_explanation": "The fault may be confined to one update and not to the shared arrangement.",
            "change": "new", "change_reason": "", "review_by": str(DAY + timedelta(days=28)),
            "indicators": [{"indicator": "A further processor fault", "threshold": "any second event",
                            "check_by": str(DAY + timedelta(days=60))}]}
    return {**base, **over}


def reply(*judgements, retire=(), abstentions=()):
    return {"judgements": list(judgements), "retire": list(retire), "abstentions": list(abstentions)}


def cycle(tmp_path, answer, reports=STANDARD, now=NOW):
    import os

    os.environ[jd.DIR_ENV] = str(tmp_path)                     # router and producer share one register, as in production
    evidence, reader = world(*reports)
    model = Model(reader, answer)
    return jd.run(evidence, coverage={"degraded": False}, register=jd.Register(tmp_path), drafter=model, now=now), model


def reasons(result):
    return " | ".join(a["reason"] for a in result["run"]["abstentions"])


def test_the_real_screening_engine_leaves_a_readable_projection_to_check_against(tmp_path, monkeypatch):
    if not guard._venv_ready():
        pytest.skip("llmsec venv not present")
    monkeypatch.setattr(Model, "redact", True)
    result, model = cycle(tmp_path, lambda ref, shown: reply(draft(ref)))
    shown = route.projection(model.prompt)
    assert len(shown["records"]) == 2 and shown["standing"] == []
    assert result["run"]["outcome"] == "completed", reasons(result)


def test_accepts_substantive_supported_conditional_inference(tmp_path):
    result, model = cycle(tmp_path, lambda ref, shown: reply(draft(ref)))
    assert result["run"]["outcome"] == "completed", reasons(result)
    (j,) = jd.Register(tmp_path).state()[0].values()
    assert j["confidence"] == "high" and "2 independent origin(s)" in j["confidence_basis"]
    assert {s["summary"] for s in j["evidence"]} <= {v["summary"] for v in route.projection(model.prompt)["records"].values()}


@pytest.mark.parametrize("over", [
    {"assessment": "The fault at ExampleSwitch did not stop card payments at the three banks."},
    {"implications": "Payment providers do not have to report major outages to the regulator."},
    {"reasoning": "Reporting major outages is optional for payment providers, so each could wait."},
    {"uncertainty": "Card payments continued at all three banks during the fault."},
])
def test_rejects_contradictory_assessments(tmp_path, over):
    result, _ = cycle(tmp_path, lambda ref, shown: reply(draft(ref, **over)))
    assert result["run"]["outcome"] == "drafts_rejected" and "contradicts" in reasons(result), reasons(result)


def test_rejects_unrelated_systemic_connection(tmp_path):
    for n, over in enumerate((
            {"assessment": "Mobile coverage for regional towns may depend on one tower operator."},      # different exposure
            {"connection": {"statement": "Payment providers must report major outages to the regulator.", "refs": ["@rule"]}},
            {"connection": {"statement": "", "refs": []}})):                                             # none supplied
        def answer(ref, shown, over=over):
            link = over.get("connection")
            if link and link["refs"] == ["@rule"]:
                return reply(draft(ref, connection={**link, "refs": [ref["rule"]]}))
            return reply(draft(ref, **over))
        result, _ = cycle(tmp_path / str(n), answer)
        assert result["run"]["outcome"] == "drafts_rejected" and "connection" in reasons(result), reasons(result)


@pytest.mark.parametrize("over", [
    {"key_assumption": "ExampleSwitch has failed twice before this year."},
    {"key_assumption": "ExampleSwitch is the only processor used by Optus."},
    {"uncertainty": "Whether ExampleSwitch, which was fined last year, could fail again is unclear."},
    {"competing_explanation": "The banks had already cut their testing budgets."},
    {"indicators": [{"indicator": "A repeat of the 14 earlier processor faults", "threshold": "any", "check_by": str(DAY)}]},
    {"indicators": [{"indicator": "A further fault at Atlassian", "threshold": "any", "check_by": str(DAY)}]},
])
def test_rejects_fabricated_facts_in_assumptions_alternatives_and_indicators(tmp_path, over):
    result, _ = cycle(tmp_path, lambda ref, shown: reply(draft(ref, **over)))
    assert result["run"]["outcome"] == "drafts_rejected", over


@pytest.mark.parametrize("copy", [
    (OTHER_PRESS, FAULT[0], FAULT[1]),                                                                       # same wording
    (OTHER_PRESS, "Banks hit by processor fault", "AAP reports a processor problem halted cards. " + FAULT[1][:60]),
])
def test_duplicated_reporting_does_not_add_confidence(copy):
    first = {"publisher": "a", "official": False, "title": FAULT[0], "summary": FAULT[1] + (" AAP" if "AAP" in copy[2] else ""),
             "source": PRESS}
    second = {"publisher": "b", "official": False, "title": copy[1], "summary": copy[2], "source": copy[0]}
    assert jd.confidence_for([first, second])[0] is None
    official = {"publisher": "r", "official": True, "title": RULE[0], "summary": RULE[1], "source": "APRA"}
    relay = {"publisher": "c", "official": False, "title": "Banks told to report faster",
             "summary": "Outages must be reported within a day, APRA said in a statement.", "source": PRESS}
    assert jd.confidence_for([official, relay])[0] == "moderate"
    assert jd.confidence_for([official, {**first, "role": "syndicated"}])[0] == "moderate"
    assert jd.confidence_for([official, first])[0] == "high"


def test_publication_date_is_not_an_event_date(tmp_path):
    published = (NOW - timedelta(days=2)).date()
    day = f"{published.day} {published:%B}"
    wrong, _ = cycle(tmp_path / "a", lambda ref, shown: reply(draft(
        ref, reasoning=f"The fault on {day} could recur at each of the banks.")))
    assert wrong["run"]["outcome"] == "drafts_rejected", reasons(wrong)
    right, model = cycle(tmp_path / "b", lambda ref, shown: reply(draft(
        ref, uncertainty=f"The report was published on {day}; whether the fault could recur is unclear.")))
    assert right["run"]["outcome"] == "completed", reasons(right)
    assert "not the date of the event" in " ".join(model.prompt.split())


def test_valid_abstention_is_preserved_and_malformed_replies_are_not_abstentions(tmp_path):
    ok, _ = cycle(tmp_path / "a", lambda ref, shown: reply(abstentions=[{"topic": "processor", "reason": "one report only"}]))
    assert ok["run"]["outcome"] == "model_abstention" and "Valid model abstention" in ok["text"]
    for n, bad in enumerate(({"judgements": []}, reply(), {"judgements": [{"assessment": "x"}], "retire": [], "abstentions": []},
                             reply(abstentions=[{"topic": "processor"}]), [], {"answer": "nothing to report"})):
        result, _ = cycle(tmp_path / str(n), lambda ref, shown, bad=bad: bad)
        assert result["run"]["outcome"] == "malformed_reply" and result["status"] == "drafting_unavailable", bad
        assert "not an abstention or a finding of low risk" in result["text"] and result["run"]["malformed_reply"]


def test_unsupported_retirement_does_not_close_a_judgement(tmp_path):
    cycle(tmp_path, lambda ref, shown: reply(draft(ref)))
    (jid,) = jd.Register(tmp_path).state()[0]
    # not reviewed and cleared, so the model is never shown it: it cannot update or retire it
    seen = {}
    cycle(tmp_path, lambda ref, shown: seen.update(shown) or reply(
        retire=[{"id": jid, "status": "withdrawn", "reason": "no longer true", "refs": [ref["fault"]]}]), now=NOW + timedelta(days=1))
    assert seen["standing"] == [] and jid in jd.Register(tmp_path).state()[0]
    assert not [r for r in jd.Register(tmp_path).records() if r["type"] in ("retire", "retire_proposal")]


def test_record_removed_at_the_boundary_cannot_support_anything(tmp_path):
    reports = STANDARD
    evidence, reader = world(*reports)

    def withholding(request):
        text, refs, dropped, shown = Model(reader, lambda ref, s: reply(draft(ref)))(request)
        gone = next(r for r, v in shown["records"].items() if v["title"] == RULE[0])
        del shown["records"][gone]                                      # as if screening or redaction had removed it
        return text, refs, dropped, shown

    result = jd.run(evidence, coverage={"degraded": False}, register=jd.Register(tmp_path), drafter=withholding, now=NOW)
    assert result["run"]["outcome"] == "drafts_rejected" and "no valid source reference" in reasons(result)


def test_unreviewed_judgement_stays_out_of_the_brief(tmp_path):
    cycle(tmp_path, lambda ref, shown: reply(draft(ref, implications="The banks could face large penalties from the regulator.")))
    register = jd.Register(tmp_path)
    assert "large penalties" not in "\n".join(jb.section_lines(DAY, register))       # code accepts it; a person has to judge it


def test_client_refuses_a_router_reply_without_the_shown_evidence(monkeypatch):
    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"response": "{}", "refs": {}}).encode()

    monkeypatch.setattr(jd.urllib.request, "urlopen", lambda *a, **k: Reply())
    monkeypatch.delenv("MODEL_ROUTER_URL", raising=False)
    with pytest.raises(jd.DraftUnavailable, match="shown"):
        jd.draft_via_router({"as_of": str(DAY), "event_ids": [], "standing_ids": []})
