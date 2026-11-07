"""SEC-01 G4/G5 prep: write-path matrix for the self-improvement dashboard.

Crosses the two POST write routes with the secret states (missing, empty, wrong,
correct), malformed bodies, unsupported methods, unknown paths, read routes, OPTIONS,
and log hygiene. Every state-changing call (save_decision, the opportunity store,
the outcome-contract builder) is mocked, so nothing touches disk or the network.
Only synthetic credentials are used: the TEST_SI_SECRET constant, a wrong value
and the empty string.
"""

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))
sys.path.insert(0, str(REPO_ROOT))

import dashboard

from tests.si_dashboard_helpers import TEST_SI_SECRET, si_test_client

HDR = "X-Self-Improvement-Secret"
WRONG_SECRET = "SYNTH-WRONG"
DECIDE = "/api/decide"
OPP_DECIDE = "/api/opportunity/decide"
VALID_DECIDE_BODY = {"finding_id": "F-SYNTH", "decision": "rejected"}
VALID_OPP_BODY = {"opportunity_id": "EVO-SYNTH-SEC01", "decision_type": "not_useful"}
WRITE_CASES = [(DECIDE, VALID_DECIDE_BODY), (OPP_DECIDE, VALID_OPP_BODY)]


@pytest.fixture(autouse=True)
def _secret_configured():
    saved = dashboard._SI_SECRET
    dashboard._SI_SECRET = TEST_SI_SECRET
    yield
    dashboard._SI_SECRET = saved


@pytest.fixture
def mocks():
    """Mock every state-changing collaborator; the store reports 'not found' by default."""
    with (
        patch.object(dashboard, "save_decision", return_value=True) as save,
        patch.object(dashboard, "opportunity_store") as store,
        patch.object(dashboard.outcome_contract_module, "build_outcome_contract") as contract,
    ):
        store.get.return_value = None
        yield SimpleNamespace(save=save, store=store, contract=contract)


@pytest.fixture
def loaders():
    """Read-path loaders return empty data so GET handlers never touch real state."""
    with (
        patch.object(dashboard, "load_findings", return_value=([], None)),
        patch.object(dashboard, "load_decisions", return_value={}),
        patch.object(dashboard, "load_finding_staleness", return_value={}),
    ):
        yield


def _assert_no_mutation(m):
    m.save.assert_not_called()
    m.store.get.assert_not_called()
    m.store.update.assert_not_called()
    m.contract.assert_not_called()


# ── Refused writes: the handler must never run ───────────────────────────────

@pytest.mark.parametrize("path,body", WRITE_CASES)
def test_write_without_secret_is_401_and_handler_not_called(mocks, path, body):
    resp = dashboard.app.test_client().post(path, json=body)
    assert resp.status_code == 401
    _assert_no_mutation(mocks)


@pytest.mark.parametrize("path,body", WRITE_CASES)
def test_write_with_empty_secret_is_401_and_handler_not_called(mocks, path, body):
    resp = dashboard.app.test_client().post(path, json=body, headers={HDR: ""})
    assert resp.status_code == 401
    _assert_no_mutation(mocks)


@pytest.mark.parametrize("path,body", WRITE_CASES)
def test_write_with_wrong_secret_is_401_and_handler_not_called(mocks, path, body):
    resp = dashboard.app.test_client().post(path, json=body, headers={HDR: WRONG_SECRET})
    assert resp.status_code == 401
    _assert_no_mutation(mocks)


# ── Authorised writes: the handler runs ──────────────────────────────────────

def test_decide_with_correct_secret_reaches_handler(mocks):
    resp = si_test_client(dashboard).post(DECIDE, json=VALID_DECIDE_BODY)
    assert resp.status_code == 200
    assert resp.get_json() == {"success": True, "finding_id": "F-SYNTH", "decision": "rejected"}
    mocks.save.assert_called_once_with("F-SYNTH", "rejected", "")
    mocks.store.update.assert_not_called()
    mocks.contract.assert_not_called()


def test_opportunity_decide_with_correct_secret_for_absent_id_is_404_without_update(mocks):
    resp = si_test_client(dashboard).post(OPP_DECIDE, json=VALID_OPP_BODY)
    assert resp.status_code == 404
    mocks.store.get.assert_called_once_with("EVO-SYNTH-SEC01")
    mocks.store.update.assert_not_called()
    mocks.save.assert_not_called()
    mocks.contract.assert_not_called()


# ── Malformed bodies with a correct secret ───────────────────────────────────

@pytest.mark.parametrize("path,body", [
    (DECIDE, {}),
    (DECIDE, {"finding_id": "F-SYNTH"}),
    (DECIDE, {"decision": "rejected"}),
    (DECIDE, {"finding_id": "F-SYNTH", "decision": "bogus"}),
    (OPP_DECIDE, {}),
    (OPP_DECIDE, {"opportunity_id": "EVO-SYNTH-SEC01"}),
    (OPP_DECIDE, {"decision_type": "not_useful"}),
    (OPP_DECIDE, {"opportunity_id": "EVO-SYNTH-SEC01", "decision_type": "bogus"}),
])
def test_malformed_write_body_with_correct_secret_is_400_and_no_mutation(mocks, path, body):
    resp = si_test_client(dashboard).post(path, json=body)
    assert resp.status_code == 400
    assert "error" in resp.get_json()
    _assert_no_mutation(mocks)


def test_decide_missing_fields_returns_expected_message(mocks):
    resp = si_test_client(dashboard).post(DECIDE, json={})
    assert resp.get_json() == {"error": "Missing finding_id or decision"}


# ── Method and route matrix with a valid secret ──────────────────────────────

@pytest.mark.parametrize("method,path", [
    ("GET", DECIDE),
    ("PUT", DECIDE),
    ("PATCH", DECIDE),
    ("DELETE", DECIDE),
    pytest.param("GET", OPP_DECIDE, marks=pytest.mark.xfail(
        strict=True,
        reason="GET /api/opportunity/decide matches the GET /api/opportunity/<opportunity_id> "
               "lookup route with id 'decide', so it returns 404 (not 405). Read-only; no mutation.",
    )),
    ("PUT", OPP_DECIDE),
    ("PATCH", OPP_DECIDE),
    ("DELETE", OPP_DECIDE),
])
def test_unsupported_method_on_write_route_is_405(mocks, method, path):
    resp = si_test_client(dashboard).open(path, method=method)
    assert resp.status_code == 405
    _assert_no_mutation(mocks)


@pytest.mark.parametrize("path", [f"{DECIDE}/extra", "/api/does-not-exist", "/api/decidex"])
def test_unknown_route_with_valid_secret_is_404_and_no_handler_call(mocks, path):
    resp = si_test_client(dashboard).post(path, json=VALID_DECIDE_BODY)
    assert resp.status_code == 404
    _assert_no_mutation(mocks)


# ── Read routes still require the secret ─────────────────────────────────────

def test_read_route_without_secret_is_401(loaders):
    assert dashboard.app.test_client().get("/api/findings").status_code == 401


def test_read_route_with_wrong_secret_is_401(loaders):
    resp = dashboard.app.test_client().get("/api/findings", headers={HDR: WRONG_SECRET})
    assert resp.status_code == 401


def test_read_route_with_correct_secret_is_served(loaders):
    resp = si_test_client(dashboard).get("/api/findings")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 0


# ── OPTIONS: Flask auto-responds once authenticated ──────────────────────────

@pytest.mark.parametrize("path", [DECIDE, OPP_DECIDE])
def test_options_on_write_route_with_correct_secret_is_flask_auto_response(mocks, path):
    # Public denial of OPTIONS is Caddy's job (write-method containment), not Flask's;
    # here we only record what the app returns behind a valid secret.
    status = si_test_client(dashboard).open(path, method="OPTIONS").status_code
    assert status in (200, 204)
    _assert_no_mutation(mocks)


# ── Log hygiene ──────────────────────────────────────────────────────────────

def test_secret_and_tracebacks_never_reach_logs(caplog, mocks, loaders):
    caplog.set_level(logging.DEBUG)
    client = dashboard.app.test_client()
    client.post(DECIDE, json=VALID_DECIDE_BODY, headers={HDR: WRONG_SECRET})
    client.post(OPP_DECIDE, json=VALID_OPP_BODY, headers={HDR: TEST_SI_SECRET + "x"})
    si_test_client(dashboard).post(DECIDE, json=VALID_DECIDE_BODY)
    si_test_client(dashboard).get("/api/findings")
    assert TEST_SI_SECRET not in caplog.text
    assert WRONG_SECRET not in caplog.text
    assert "Traceback" not in caplog.text
