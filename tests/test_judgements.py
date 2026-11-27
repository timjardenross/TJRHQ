"""Targeted tests for the judgement producer: boundary, evidence rules, continuity. No network; the drafter is a stub."""
import io
import json
import re
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

from intelligence import brief_evidence as be
from intelligence import judgements as jd

NOW = datetime(2026, 11, 26, 1, 0, tzinfo=timezone.utc)
TITLE = "Telstra mobile outage disrupts Triple Zero calls in Canberra"


def event(i, source="ABC News", title=TITLE, url=None, summary=None, geography="AU"):
    return {"id": f"0000000{i}-0000-0000-0000-000000000000", "title": title, "summary": summary or title, "source": source,
            "geography": geography, "collected_at": NOW.isoformat(), "published_at": NOW.isoformat(),
            "url": url or f"https://example{i}.com.au/story"}


def evidence(*events):
    return be.build_evidence(list(events), now=NOW, window_hours=72)


def two_publishers():
    return evidence(event(1), event(2, source="Guardian Australia"))


def payload(request, **override):
    """A well-formed reply citing every record offered in the request; model labels are src-<n letters>."""
    refs = {f"src-{'abcdefghij'[n]}": e for n, e in enumerate(request["event_ids"])}
    j = {"id": None, "area": "sector", "assessment": "The Telstra outage is a live threat to Triple Zero calls in Canberra.",
         "facts": [{"text": TITLE + ".", "refs": list(refs)}],
         "reasoning": "Disrupted Triple Zero calls in Canberra mean the outage reaches emergency calling.",
         "key_assumption": "The reported disruption is still current.", "connection": {"statement": "", "refs": []},
         "australian_relevance": "", "implications": "Triple Zero calls in Canberra may need another path.",
         "uncertainty": "Restoration time is not reported.", "competing_explanation": "The disruption may already be over.",
         "change": "new", "change_reason": "", "review_by": "2026-12-01", "requirements": ["telecoms-digital"],
         "indicators": [{"indicator": "Further reports of failed calls", "threshold": "any new report", "check_by": "2026-11-28"}]}
    j.update(override)
    return j, refs


def reply_for(request, **override):
    j, refs = payload(request, **override)
    return json.dumps({"judgements": [j]}), refs


def nothing(request):
    return '{"judgements": []}', {}


def run(tmp_path, ev, drafter, now=NOW, **kw):
    return jd.run(ev, coverage={"degraded": False}, register=jd.Register(tmp_path), drafter=drafter, now=now, **kw)


def test_public_source_fails_closed():
    ok = {"source_name": "ABC News", "url": "https://www.abc.net.au/news/x", "title": "Outage"}
    assert jd.public_source(ok)[0]
    assert jd.public_source({**ok, "url": "https://status.supabase.com/incidents/x"})[0]
    assert not jd.public_source({**ok, "url": "https://abc.supabase.co/x"})[0]
    for bad in ({**ok, "source_name": ""}, {**ok, "url": None}, {**ok, "url": "file:///etc/passwd"},
                {**ok, "url": "http://10.0.0.5/x"}, {**ok, "url": "http://intranet/x"},
                {**ok, "url": "https://203-0-113-5.sslip.io/x"}, {**ok, "url": "https://user:pw@abc.net.au/x"},
                {**ok, "source_name": "AWS Status (Uptime Kuma direct probe)"},
                {**ok, "source_name": "APRA (changedetection.io watchlist)"}):
        assert not jd.public_source(bad)[0], bad


def test_mixed_provenance_incident_is_excluded_whole():
    ev = evidence(event(1), event(2, source="Telstra (Uptime Kuma direct probe)"))
    candidates, excluded = jd.build_candidates(ev)
    assert candidates == [] and excluded


def test_request_carries_identifiers_only(tmp_path):
    seen = []
    run(tmp_path, two_publishers(), lambda r: seen.append(r) or nothing(r))
    (request,) = seen
    assert set(request) == {"as_of", "event_ids", "standing_ids"} and request["standing_ids"] == []
    assert all(re.fullmatch(r"[0-9a-f-]{36}", e) for e in request["event_ids"])


def test_boundary_exclusions_and_telstra_gap_are_disclosed(tmp_path):
    result = run(tmp_path, two_publishers(), lambda r: ('{"judgements": []}', {}, {"x": "personal identifier"}))
    assert "Left out at the outbound boundary: 1 item(s) - personal identifier." in result["text"]
    assert "Reduced Telstra coverage" in result["text"]


def test_supported_judgement_is_registered_with_code_confidence(tmp_path):
    result = run(tmp_path, two_publishers(), lambda p: reply_for(p, confidence="high"))
    assert result["status"] == "ok", result["run"]["abstentions"]
    open_, _ = jd.Register(tmp_path).state()
    (j,) = open_.values()
    assert j["confidence"] == "moderate" and j["change"] == "new" and len(j["evidence"]) == 2 and j["requirements"] == ["B2"]
    assert "EVALUATION ONLY" in result["text"] and j["id"] in result["text"]


@pytest.mark.parametrize("override,reason", [
    ({"facts": [{"text": TITLE + ".", "refs": ["src-zzz"]}]}, "source reference"),
    ({"reasoning": ""}, "reasoning"),
    ({"key_assumption": ""}, "key_assumption"),
    ({"assessment": TITLE + "."}, "restates a headline"),
    ({"indicators": []}, "warning indicator"),
    ({"competing_explanation": ""}, "competing_explanation"),
    ({"assessment": "Optus has lost 4000 services in Perth since Tuesday."}, "claim gate"),
    ({"implications": "This is a cascading failure across Triple Zero calls in Canberra."}, "without a reported connection"),
])
def test_defective_judgement_is_withheld(tmp_path, override, reason):
    result = run(tmp_path, two_publishers(), lambda p: reply_for(p, **override))
    assert result["status"] == "abstained"
    assert any(reason in a["reason"] for a in result["run"]["abstentions"]), result["run"]["abstentions"]


def test_single_unofficial_source_is_insufficient(tmp_path):
    result = run(tmp_path, evidence(event(1)), reply_for)
    assert result["status"] == "abstained"
    assert "insufficient evidence" in result["run"]["abstentions"][0]["reason"]


def test_at_most_three_a_day(tmp_path):
    def many(request):
        j, refs = payload(request)
        return json.dumps({"judgements": [j] * 5}), refs
    result = run(tmp_path, two_publishers(), many)
    assert len(result["run"]["issued"]) == 3


def test_unavailable_drafting_abstains_and_never_expires(tmp_path):
    run(tmp_path, two_publishers(), lambda p: reply_for(p, review_by="2026-11-27"))

    def down(_):
        raise jd.DraftUnavailable("router: HTTPError")
    result = run(tmp_path, two_publishers(), down, now=NOW + timedelta(days=5))
    assert result["status"] == "drafting_unavailable" and "drafting unavailable" in result["text"]
    assert len(jd.Register(tmp_path).state()[0]) == 1


def test_several_incidents_are_not_systemic_evidence(tmp_path):
    other = "Optus mobile outage disrupts services in Perth"
    ev = evidence(event(1), event(2, source="Guardian Australia"), event(3, title=other), event(4, source="iTnews", title=other))
    result = run(tmp_path, ev, lambda p: reply_for(p, assessment="Systemic weakness threatens Triple Zero calls in Canberra."))
    assert any("without a reported connection" in a["reason"] for a in result["run"]["abstentions"]), result["run"]["abstentions"]


def test_one_reported_connection_supports_a_systemic_claim(tmp_path):
    title = "Banks depend on shared supplier Cuscal for card payments"
    ev = evidence(event(1, title=title), event(2, source="Guardian Australia", title=title))
    result = run(tmp_path, ev, lambda p: reply_for(
        p, assessment="Card payments carry concentration exposure through one shared supplier.",
        facts=[{"text": title + ".", "refs": ["src-a", "src-b"]}], connection={"statement": title + ".", "refs": ["src-a"]},
        reasoning="Banks depend on the shared supplier for card payments.", implications="Card payments of banks share one point.",
        key_assumption="The dependency on Cuscal is current.", competing_explanation="Banks may hold a second route."))
    assert result["status"] == "ok", result["run"]["abstentions"]


def test_international_indicator_is_eligible_when_relevance_is_stated(tmp_path):
    title = "London cloud region outage halts payments at British banks"
    ev = evidence(*(event(i, source=s, title=title, geography="UK", url=f"https://example{i}.co.uk/a")
                    for i, s in ((1, "BBC News"), (2, "Financial Times"))))
    fields = {"assessment": "A cloud region outage can halt bank payments and is a warning for local banks.",
              "facts": [{"text": title + ".", "refs": ["src-a", "src-b"]}],
              "reasoning": "The outage halts payments at British banks, so a cloud region can stop bank payments.",
              "implications": "Bank payments that sit in one cloud region may halt.", "key_assumption": "The outage is as reported.",
              "competing_explanation": "The cause may be local to British banks."}
    withheld = run(tmp_path / "a", ev, lambda p: reply_for(p, **fields))
    assert any("Australian relevance" in a["reason"] for a in withheld["run"]["abstentions"]), withheld["run"]["abstentions"]
    issued = run(tmp_path / "b", ev, lambda p: reply_for(
        p, australian_relevance="Australian banks that run payments in a cloud region may be exposed the same way.", **fields))
    assert issued["status"] == "ok", issued["run"]["abstentions"]


def test_continuity_carry_unchanged_retire_and_expire(tmp_path):
    reg = jd.Register(tmp_path)
    run(tmp_path, two_publishers(), reply_for)
    (jid,) = reg.state()[0]
    first = reg.path.read_text()
    # re-assessed without new evidence cannot be "strengthened"
    run(tmp_path, two_publishers(), lambda p: reply_for(p, id=jid, change="strengthened"), now=NOW + timedelta(days=1))
    assert reg.state()[0][jid]["change"] == "unchanged"
    assert reg.path.read_text().startswith(first)                      # append only
    result = run(tmp_path, two_publishers(), nothing, now=NOW + timedelta(days=2))
    assert "STANDING" in result["text"]
    result = run(tmp_path, two_publishers(), nothing, now=NOW + timedelta(days=10))
    assert "expired" in result["text"] and reg.state()[0] == {}


def test_rejection_closes_blocks_redraft_and_is_never_sent(tmp_path, monkeypatch):
    monkeypatch.setenv(jd.DIR_ENV, str(tmp_path))
    run(tmp_path, two_publishers(), reply_for)
    (jid,) = jd.Register(tmp_path).state()[0]
    assert jd.main(["adjudicate", jid, "--relevant", "n", "--useful", "n", "--decision", "none", "--reject",
                    "--note", "private reason zebra"]) == 0
    seen = []
    result = run(tmp_path, two_publishers(), lambda r: seen.append(r) or reply_for(r), now=NOW + timedelta(days=1))
    assert "zebra" not in json.dumps(seen) and seen[0]["standing_ids"] == []
    assert any("you rejected" in a["reason"] for a in result["run"]["abstentions"])


def test_adjudication_review_and_miss_records(tmp_path, monkeypatch):
    monkeypatch.setenv(jd.DIR_ENV, str(tmp_path))
    run(tmp_path, two_publishers(), reply_for)
    (jid,) = jd.Register(tmp_path).state()[0]
    assert jd.main(["adjudicate", jid, "--relevant", "y", "--useful", "y", "--decision", "non-action"]) == 0
    assert jd.main(["review", jid, "--facts", "pass", "--reasoning", "fail"]) == 0
    assert jd.main(["miss", "x", "--materiality", "critical", "--consequence", "no warning", "--cause", "no source"]) == 0
    with pytest.raises(SystemExit):
        jd.main(["miss", "x", "--cause", "no source"])                    # explanation alone is not an assessment
    kinds = [r["type"] for r in jd.Register(tmp_path).records()]
    assert kinds.count("adjudication") == kinds.count("review") == kinds.count("miss") == 1


def test_retire_needs_reason_and_evidence(tmp_path):
    reg = jd.Register(tmp_path)
    run(tmp_path, two_publishers(), reply_for)
    (jid,) = reg.state()[0]
    run(tmp_path, two_publishers(),
        lambda p: (json.dumps({"retire": [{"id": jid, "status": "closed", "reason": "done", "refs": []}]}), {}),
        now=NOW + timedelta(days=1))
    assert jid in reg.state()[0]


def test_one_completed_run_per_melbourne_day(tmp_path):
    run(tmp_path, two_publishers(), reply_for)
    assert run(tmp_path, two_publishers(), reply_for)["status"] == "skipped"


def test_router_client_has_one_route_and_no_fallback(monkeypatch):
    seen = []

    def fake(request, timeout):
        seen.append(request.full_url)
        raise OSError("404")
    monkeypatch.setattr(jd.urllib.request, "urlopen", fake)
    monkeypatch.delenv("MODEL_ROUTER_URL", raising=False)
    with pytest.raises(jd.DraftUnavailable):
        jd.draft_via_router({"as_of": "2026-11-26", "event_ids": [], "standing_ids": []})
    assert seen == ["http://127.0.0.1:8891/api/model/intelligence-judgement"]
    for elsewhere in ("https://elsewhere.example.com", "http://127.0.0.1.example.com", "http://localhost@evil.example.com"):
        monkeypatch.setenv("MODEL_ROUTER_URL", elsewhere)
        with pytest.raises(jd.DraftUnavailable):
            jd.draft_via_router({"as_of": "2026-11-26", "event_ids": [], "standing_ids": []})
    assert len(seen) == 1


def test_flag_defaults_off():
    assert not jd.enabled({})


def test_live_run_sends_only_with_send_flag(tmp_path, monkeypatch):
    from core.platform import notification_service as ns
    from intelligence import captains_brief as cb
    sent = []
    monkeypatch.setenv(jd.DIR_ENV, str(tmp_path))
    monkeypatch.setattr(be, "load_events", lambda *a, **k: [])
    monkeypatch.setattr(cb, "_get_latest_ori_brief", lambda: None)
    monkeypatch.setattr(ns, "notify", lambda body, **kw: sent.append(kw))
    monkeypatch.delenv(jd.SEND_FLAG, raising=False)
    assert "EVALUATION ONLY" in jd.run_live()["text"] and sent == []
    (tmp_path / "register.jsonl").unlink()
    monkeypatch.setenv(jd.SEND_FLAG, "1")
    jd.run_live()
    assert len(sent) == 1 and sent[0]["chunk"] and sent[0]["strict"]


@pytest.mark.parametrize("text", ['{"judgements": [], "retire": ["x"]}', '{"judgements": [{"area": "sector", "indicators": ["x"], "facts": ["y"]}]}'])
def test_malformed_reply_is_recorded_not_raised(tmp_path, text):
    result = run(tmp_path, two_publishers(), lambda r: (text, {}))
    assert result["status"] == "drafting_unavailable" and "malformed" in result["text"]


@pytest.mark.parametrize("drafter", [reply_for, nothing, "down"])
def test_every_product_states_the_screening_and_telstra_limitations(tmp_path, drafter):
    if drafter == "down":
        def drafter(_):
            raise jd.DraftUnavailable("router: HTTPError")
    result = run(tmp_path, two_publishers(), drafter)
    assert ("Information screening is pattern-based and may exclude legitimate reporting or fail to detect some sensitive details. "
            "Excluded records may reduce intelligence coverage.") in result["text"]
    assert "Reduced Telstra coverage" in result["text"]


@pytest.mark.parametrize("outcome", ["withheld_security_review", "hold_expired", "not_sent", "provider_failure", "no_reply"])
def test_each_failure_is_reported_as_what_it_was(tmp_path, outcome):
    def fail(_):
        raise jd.DraftUnavailable("detail", outcome)
    result = run(tmp_path, two_publishers(), fail)
    assert result["run"]["outcome"] == outcome and result["status"] == "drafting_unavailable"
    assert jd.OUTCOMES[outcome] in result["text"] and "not an abstention or a finding of low risk" in result["text"]


def test_model_abstention_and_completion_are_distinct(tmp_path):
    empty = run(tmp_path / "a", two_publishers(), lambda p: (json.dumps({"judgements": []}), {}))
    assert empty["run"]["outcome"] == "model_abstention" and "Valid model abstention" in empty["text"]
    done = run(tmp_path / "b", two_publishers(), lambda p: reply_for(p))
    assert done["run"]["outcome"] == "completed" and "Assessment completed." in done["text"]


@pytest.mark.parametrize("code,body,expected", [
    (500, {"error": "payload withheld by security review", "outcome": "withheld_security_review"}, "withheld_security_review"),
    (500, {"error": "held payload was not released in time", "outcome": "hold_expired"}, "hold_expired"),
    (500, {"error": "HTTP Error 503", "outcome": "provider_failure"}, "provider_failure"),
    (400, {"error": "no eligible record"}, "not_sent"),
    (500, {}, "no_reply"),
])
def test_router_error_body_is_read(monkeypatch, code, body, expected):
    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, code, "x", {}, io.BytesIO(json.dumps(body).encode()))
    monkeypatch.setattr(jd.urllib.request, "urlopen", refuse)
    with pytest.raises(jd.DraftUnavailable) as caught:
        jd.draft_via_router({"as_of": "2026-11-28", "event_ids": [], "standing_ids": []})
    assert caught.value.outcome == expected
