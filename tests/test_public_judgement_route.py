"""The public-source judgement boundary: caller identity, identifiers only, validated standing text, personal information,
hold before dispatch, unchanged redaction for everything else. Real loopback sockets; the model call and record store are replaced."""
import importlib.util
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from core.security import llm_guardrails as guard
from core.security import public_judgement_route as route

ROOT = Path(__file__).resolve().parent.parent
ABC = "85d57c5c-a0f1-449f-8d18-b33d8d197daa"
NEWS_SEARCH = "51288836-78b5-485a-97bb-e6ae5974af56"          # search-aggregator feed: not eligible
EV = "00000001-0000-0000-0000-000000000000"
FABRICATED = [
    "Jane Citizen, date of birth 4 March 1961, of 12 Smith Street Ballarat, tax file number 123 456 782",
    "Internal note: server db-primary admin console is open on the management network",
    "My mother was diagnosed with dementia and is a practising Catholic",
]


def row(event_id=EV, source_id=ABC, title="APRA fines Bendigo and Adelaide Bank", summary="Penalty over a cyber incident", **kw):
    return {"event_id": event_id, "source_id": source_id, "raw_title": title, "raw_summary": summary, "published_at": "2026-11-24T00:00:00Z",
            "canonical_url": "https://www.abc.net.au/news/x", "suppressed": False, **kw}


def store(*events, active=True):
    def read(table, query):
        if table == "intelligence_events":
            return [e for e in events if e["event_id"] in query]
        return [{"source_id": s, "source_name": "ABC News", "active": active} for s in (ABC, NEWS_SEARCH) if s in query]
    return read


def nobody(text):
    return []


def ask(**kw):
    return {"as_of": "2026-11-26", "event_ids": [EV], "standing_ids": [], **kw}


def prepare(body, reader=None, detector=nobody):
    return route.prepare(body, reader=reader or store(row()), detector=detector)


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("PDB_JUDGEMENTS_DIR", str(tmp_path))
    for name in (route.FLAG, route.UNATTENDED_FLAG, route.HOLD_SECONDS_ENV, "LLM_GUARDRAILS_FAIL_OPEN"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def router():
    spec = importlib.util.spec_from_file_location("router_under_test", ROOT / "core" / "model-router" / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_flag_default_off_and_never_with_fail_open():
    assert not route.enabled({})
    assert route.enabled({route.FLAG: "1"})
    assert not route.enabled({route.FLAG: "1", "LLM_GUARDRAILS_FAIL_OPEN": "1"})


def test_allowlist_is_the_62_verified_ids_and_states_the_telstra_gap():
    allowed = route.allowlist()
    assert len(allowed) == 62 and ABC in allowed and NEWS_SEARCH not in allowed
    assert not any(n.startswith(("Google News", "Telstra", "DocuSign", "Google Workspace")) for n in allowed.values())
    assert any("Telstra" in line for line in route.limitations())


# ── C2: caller text cannot be submitted ──────────────────────────────────────

@pytest.mark.parametrize("text", FABRICATED)
def test_fabricated_records_labelled_as_public_are_refused(text):
    fake = {"event_id": "00000000-0000-0000-0000-000000000000", "title": text, "summary": text, "publisher": "ABC News", "published": ""}
    for body in ({"as_of": "2026-11-26", "records": [fake], "standing": []},          # the reviewed shape
                 ask(records=[fake]), ask(event_ids=[text]), ask(standing_ids=[text])):
        with pytest.raises(route.Rejected):
            prepare(body)
    with pytest.raises(route.Rejected, match="no stored record"):
        prepare(ask(event_ids=[fake["event_id"]]))


def test_prompt_is_built_from_the_stored_record():
    prepared = prepare(ask())
    prompt, refs = route.build_prompt(prepared)
    assert "APRA fines Bendigo" in prompt and list(refs.values()) == [EV]


@pytest.mark.parametrize("events,active", [
    ([row(source_id=NEWS_SEARCH)], True),
    ([row()], False),
    ([row(canonical_url="http://10.0.0.5/x")], True),
    ([row(suppressed=True)], True),
])
def test_ineligible_stored_records_are_refused(events, active):
    with pytest.raises(route.Rejected, match="no eligible record"):
        prepare(ask(), reader=store(*events, active=active))


def test_a_failed_read_refuses():
    def broken(table, query):
        raise OSError("down")
    with pytest.raises(route.Rejected, match="could not be read"):
        prepare(ask(), reader=broken)


# ── C4: personal information ─────────────────────────────────────────────────

@pytest.mark.parametrize("text", [FABRICATED[0], FABRICATED[2], "A Ballarat nurse who is Muslim has lost the job",
                                  "The driver was diagnosed with cancer last year", "Passport number PA 1234567 was exposed"])
def test_personal_information_is_screened_out_even_from_a_public_source(text):
    assert route.sensitive({"k": text}, nobody)


def test_a_detected_person_with_a_sensitive_attribute_is_screened_out():
    text = "Sam Example, who is gay, resigned"
    assert route.sensitive({"k": text}, lambda joined: [(0, 11)])
    assert not route.sensitive({"k": text}, nobody)


@pytest.mark.parametrize("text", [
    "APRA fines Bendigo and Adelaide Bank over cyber incident", "Australian banks warned over Chinese suppliers",
    "Health department outage disrupts mental health services in Victoria", "Medibank breach exposed customer health records",
    "Indigenous communities in the Northern Territory lose mobile coverage", "Optus outage hits Triple Zero calls in Canberra",
])
def test_national_geographic_and_organisational_intelligence_is_kept(text):
    assert not route.sensitive({"k": text}, nobody), route.sensitive({"k": text}, nobody)


def test_unavailable_person_detector_refuses():
    def down(text):
        raise guard.GuardrailsUnavailableError("no venv")
    with pytest.raises(route.Rejected, match="could not be screened"):
        route.sensitive({"k": "x"}, down)


# ── C3: standing judgements ──────────────────────────────────────────────────

JUDGEMENT = {"type": "judgement", "id": "jdg-abcdef", "area": "sector", "assessment": "Payments are exposed.",
             "indicators": [{"indicator": "More failures", "threshold": "any", "check_by": "2026-11-28"}], "evidence": [{"event_id": EV}]}


def register(state, *records):
    (state / "register.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))


def standing():
    return ask(standing_ids=["jdg-abcdef"])


def test_validated_and_returned_judgement_is_carried(state):
    route.record_outputs(json.dumps({"judgements": [JUDGEMENT]}))
    register(state, JUDGEMENT, {"type": "adjudication", "id": "jdg-abcdef", "rejected": False, "note": "private zebra"})
    prepared = prepare(standing())
    assert [s["id"] for s in prepared["standing"]] == ["jdg-abcdef"] and "zebra" not in route.build_prompt(prepared)[0]


def test_unvalidated_model_output_cannot_stand(state):
    route.record_outputs(json.dumps({"judgements": [JUDGEMENT]}))            # returned by the route, never passed validation
    with pytest.raises(route.Rejected, match="not an open judgement"):
        prepare(standing())


def test_register_text_the_route_never_returned_cannot_stand(state):
    register(state, JUDGEMENT)
    prepared = prepare(standing())
    assert prepared["standing"] == [] and prepared["dropped"]["jdg-abcdef"] == "text was not returned by this route"


@pytest.mark.parametrize("closing", [{"type": "retire", "id": "jdg-abcdef"},
                                     {"type": "adjudication", "id": "jdg-abcdef", "rejected": True}])
def test_closed_judgement_cannot_stand(state, closing):
    route.record_outputs(json.dumps({"judgements": [JUDGEMENT]}))
    register(state, JUDGEMENT, closing)
    with pytest.raises(route.Rejected, match="not an open judgement"):
        prepare(standing())


def test_standing_judgement_loses_its_place_when_evidence_is_no_longer_eligible(state):
    other = "00000002-0000-0000-0000-000000000000"
    judgement = {**JUDGEMENT, "evidence": [{"event_id": other}]}
    route.record_outputs(json.dumps({"judgements": [judgement]}))
    register(state, judgement)
    prepared = prepare(standing(), reader=store(row(), row(event_id=other, source_id=NEWS_SEARCH)))
    assert prepared["standing"] == [] and prepared["dropped"]["jdg-abcdef"] == "evidence no longer eligible"


# ── C5: hold and release ─────────────────────────────────────────────────────

def held_payload(text="payload"):
    return route.audit([EV], text, []), text


def run_hold(payload_id, text, act, seconds=30):
    """Run the hold with a fake clock; ``act`` is called on each poll."""
    tick = {"t": 0.0}

    def sleep(_):
        tick["t"] += 2
        act(tick["t"])
    os.environ[route.HOLD_SECONDS_ENV] = str(seconds)
    try:
        route.await_release(payload_id, text, sleep=sleep, clock=lambda: tick["t"])
    finally:
        os.environ.pop(route.HOLD_SECONDS_ENV, None)


def test_hold_is_the_default_and_expires(state):
    pid, text = held_payload()
    with pytest.raises(route.NotReleased, match="in time"):
        run_hold(pid, text, lambda t: None)
    with pytest.raises(route.Rejected, match="no such held payload"):        # late release refused
        route.release_payload(pid, route._sha(text))


def test_release_binds_to_the_inspected_payload_and_is_single_use(state):
    pid, text = held_payload()
    with pytest.raises(route.Rejected, match="no such held payload"):        # cannot be approved before it is held
        route.release_payload(pid, route._sha(text))
    seen = []

    def approve(t):
        if not seen:
            with pytest.raises(route.Rejected, match="does not match"):
                route.release_payload(pid, route._sha("another payload"))
            route.release_payload(pid, route._sha(text))
            seen.append(t)
    run_hold(pid, text, approve)
    assert not list((state / "outbound").glob("*.release")) and not list((state / "outbound").glob("*.held"))
    with pytest.raises(route.NotReleased):                                   # the same approval does not work twice
        run_hold(pid, text, lambda t: None, seconds=4)


def test_edited_payload_file_cannot_be_released(state):
    pid, text = held_payload()

    def tamper(t):
        (state / "outbound" / f"{pid}.txt").write_text("changed")
        with pytest.raises(route.Rejected, match="does not match"):
            route.release_payload(pid, route._sha("changed"))
    with pytest.raises(route.NotReleased):
        run_hold(pid, text, tamper, seconds=4)


# ── C1 and the whole path over a real loopback socket ────────────────────────

@pytest.fixture
def server(monkeypatch, state):
    app = router()
    sent = []
    monkeypatch.setenv(route.FLAG, "1")
    monkeypatch.setenv(route.HOLD_SECONDS_ENV, "30")
    monkeypatch.setattr(app, "_AUTH_TOKEN", "")
    monkeypatch.setattr(app, "check_input_rail", lambda p: None)
    monkeypatch.setattr(app, "check_output_rail", lambda r: None)
    monkeypatch.setattr(app, "redact_pii", lambda p, **kw: guard.RedactionResult(redacted_text="REDACTED " + p, findings=[]))
    monkeypatch.setattr(app, "_gemini_generate", lambda model, prompt, *a, **k: sent.append(prompt) or
                        {"candidates": [{"content": {"parts": [{"text": '{"judgements": []}'}]}}]})
    monkeypatch.setattr(app, "_log_call", lambda entry: None)
    monkeypatch.setattr(app._judgement_route, "read_rows", store(row()))
    monkeypatch.setattr(app._judgement_route, "person_spans", nobody)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.RouterHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/api/model/intelligence-judgement", sent, app
    httpd.shutdown()


def post(url, body, timeout=40):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


@pytest.mark.skipif(os.geteuid() != 0, reason="needs root to start a caller as another user")
def test_non_root_caller_is_refused_and_nothing_is_read_or_sent(server):
    url, sent, _ = server
    client = ("import urllib.request,urllib.error,json,sys\n"
              "r=urllib.request.Request(sys.argv[1],data=sys.argv[2].encode(),method='POST')\n"
              "try:\n  print(urllib.request.urlopen(r,timeout=20).status)\nexcept urllib.error.HTTPError as e:\n  print(e.code, e.read().decode())")
    out = subprocess.run(["/usr/bin/python3", "-I", "-c", client, url, json.dumps(ask())], user=65534, group=65534, extra_groups=[],
                         cwd="/", capture_output=True, text=True, timeout=60, check=False)
    assert out.stdout.startswith("403") and "not permitted" in out.stdout, out.stdout + out.stderr
    assert sent == []


@pytest.mark.skipif(os.geteuid() != 0, reason="needs root to start a caller as another user")
def test_non_root_caller_that_half_closes_is_still_refused(server):
    url, sent, _ = server
    port = int(url.split(":")[2].split("/")[0])
    body = json.dumps(ask())
    client = (f"import socket\ns=socket.create_connection(('127.0.0.1',{port}))\n"
              f"b={body!r}.encode()\n"
              "s.sendall(b'POST /api/model/intelligence-judgement HTTP/1.1\\r\\nHost: x\\r\\nContent-Length: %d\\r\\n\\r\\n' % len(b) + b)\n"
              "s.shutdown(socket.SHUT_WR)\ns.settimeout(20)\nprint(s.recv(200))")
    out = subprocess.run(["/usr/bin/python3", "-I", "-c", client], user=65534, group=65534, extra_groups=[], cwd="/",
                         capture_output=True, text=True, timeout=60, check=False)
    assert "403" in out.stdout, out.stdout + out.stderr
    assert sent == []


def test_unknown_identity_is_refused(tmp_path):
    assert route.caller_uid(("10.0.0.5", 1), ("127.0.0.1", 2)) is None
    assert route.caller_uid(("127.0.0.1", 1), ("127.0.0.1", 2), tables=(str(tmp_path / "none"),)) is None
    line = "  0: 0100007F:0001 0100007F:0002 {state} 00000000:00000000 00:00000000 00000000     0        0 {inode} 1 x\n"
    for state_, inode, rows, expect in (("01", "55", 1, 0), ("06", "0", 1, None), ("01", "0", 1, None), ("04", "55", 1, None),
                                        ("01", "55", 2, None)):
        table = tmp_path / "tcp"
        table.write_text("header\n" + line.format(state=state_, inode=inode) * rows)
        assert route.caller_uid(("127.0.0.1", 1), ("127.0.0.1", 2), tables=(str(table),)) == expect


def test_root_caller_cannot_submit_text(server):
    url, sent, _ = server
    for body in ({"prompt": FABRICATED[1]}, ask(records=[{"title": FABRICATED[0]}])):
        status, reply = post(url, body)
        assert status == 400, reply
    assert sent == []


def test_nothing_is_sent_while_held_and_exactly_the_inspected_payload_after_release(server, state):
    url, sent, _ = server
    result = {}
    t = threading.Thread(target=lambda: result.update(zip(("status", "reply"), post(url, ask()))))
    t.start()
    deadline = time.time() + 20
    while not list((state / "outbound").glob("*.held")) and time.time() < deadline:
        time.sleep(0.1)
    (held,) = (state / "outbound").glob("*.held")
    time.sleep(2.5)
    assert sent == [] and "status" not in result                             # held: nothing has left
    inspected = (state / "outbound" / f"{held.stem}.txt").read_text()
    assert route.main(["release", held.stem, route._sha(inspected)]) == 0
    t.join(30)
    assert result["status"] == 200 and sent == [inspected] and result["reply"]["dropped"] == {}


def test_unreleased_request_sends_nothing(server, monkeypatch):
    url, sent, _ = server
    monkeypatch.setenv(route.HOLD_SECONDS_ENV, "3")
    status, reply = post(url, ask())
    assert status == 500 and "not released" in reply["error"] and sent == []


def test_no_audit_no_send_and_other_routes_unchanged(state, monkeypatch):
    app = router()
    sent, calls = [], []
    monkeypatch.setattr(app, "check_input_rail", lambda p: None)
    monkeypatch.setattr(app, "check_output_rail", lambda r: None)
    monkeypatch.setattr(app, "redact_pii", lambda p, **kw: guard.RedactionResult(redacted_text="REDACTED", findings=[]))
    monkeypatch.setattr(app, "secure_outbound_prompt", lambda p: calls.append("default") or ("DEFAULT", None))
    monkeypatch.setattr(app, "_gemini_generate", lambda model, prompt, *a, **k: sent.append(prompt) or
                        {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
    monkeypatch.setattr(app, "_log_call", lambda entry: None)

    def no_audit(*a):
        raise OSError("disk full")
    monkeypatch.setattr(app._judgement_route, "audit", no_audit)
    assert not app._run_task(route.TASK, "built prompt", {"event_ids": []})["success"]
    assert sent == []
    assert app._run_task("intelligence-brief", "p", {})["success"]           # no hold, no new redaction option
    assert sent == ["DEFAULT"] and calls == ["default"] and route.TASK not in app.TASK_ROUTES.values()


# ── redaction ────────────────────────────────────────────────────────────────

def test_only_the_four_reviewed_types_may_be_preserved(monkeypatch):
    seen = []
    monkeypatch.setattr(guard, "_invoke_worker", lambda cmd, payload: seen.append(payload) or {"redacted_text": "x", "findings": []})
    guard.redact_pii("text")
    assert seen[-1] == {"text": "text"}                                      # existing calls: byte-identical payload
    guard.redact_pii("text", preserve_entities=route.PRESERVE)
    assert seen[-1]["preserve"] == ["DATE_TIME", "LOCATION", "NRP", "ORGANIZATION"]
    with pytest.raises(ValueError):
        guard.redact_pii("text", preserve_entities=frozenset({"PERSON"}))


def test_preserving_route_fails_closed_even_with_fail_open(monkeypatch):
    def down(cmd, payload):
        raise guard.GuardrailsUnavailableError("no venv")
    monkeypatch.setattr(guard, "_invoke_worker", down)
    monkeypatch.setattr(guard, "_FAIL_OPEN", True)
    with pytest.raises(guard.GuardrailsUnavailableError):
        guard.redact_pii("text", preserve_entities=route.PRESERVE)


def test_real_redaction_keeps_the_four_types_and_still_removes_the_rest():
    if not guard._venv_ready():
        pytest.skip("llmsec venv not present")
    text = "Jane Citizen (jane@example.org, 192.168.1.20) says Telstra failed in Canberra on 24 November 2026 for Australian banks."
    out = guard.redact_pii(text, preserve_entities=route.PRESERVE).redacted_text
    for kept in ("Telstra", "Canberra", "24 November 2026", "Australian"):
        assert kept in out, out
    for gone in ("Jane Citizen", "jane@example.org", "192.168.1.20"):
        assert gone not in out, out
    assert "Telstra" not in guard.redact_pii(text).redacted_text


def test_real_person_detector_screens_a_named_individual_but_not_organisations():
    if not guard._venv_ready():
        pytest.skip("llmsec venv not present")
    texts = {"person": "John Smith is Jewish and was refused service", "org": "APRA fines Bendigo and Adelaide Bank over cyber incident"}
    assert list(route.sensitive(texts)) == ["person"]


def test_the_routes_own_wording_survives_redaction():
    if not guard._venv_ready():
        pytest.skip("llmsec venv not present")
    prompt, refs = route.build_prompt(prepare(ask()))
    out = guard.redact_pii(prompt, preserve_entities=route.PRESERVE).redacted_text
    template = out.split("Sources (each line starts")[0]
    for word in ("essential-services", "banking-payments", "telecoms-digital", "emerging_cascading", "src-"):
        assert word in out, word
    assert "<US_DRIVER_LICENSE>" not in template and all(ref in out for ref in refs)
