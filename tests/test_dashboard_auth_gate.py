"""SEC-01 G3: shared-secret gate on every self-improvement dashboard route.

Covers every registered route and method, static and unknown paths, missing,
wrong, empty and misplaced secrets, the fail-closed 503 when the server secret is
unset, constant-time comparison, and that the secret never reaches the logs.
No test here mutates state: refused requests never reach a handler, and the one
authenticated POST targets an opportunity id that does not exist (404).
"""

import inspect
import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))
sys.path.insert(0, str(REPO_ROOT))

import dashboard

from tests.si_dashboard_helpers import TEST_SI_SECRET, si_test_client

HDR = "X-Self-Improvement-Secret"


@pytest.fixture(autouse=True)
def _secret_configured():
    saved = dashboard._SI_SECRET
    dashboard._SI_SECRET = TEST_SI_SECRET
    yield
    dashboard._SI_SECRET = saved


def _concrete(rule):
    return rule.replace("<finding_id>", "x").replace("<opportunity_id>", "x").replace("<path:filename>", "none.js")


def _all_route_methods():
    pairs = []
    for rule in dashboard.app.url_map.iter_rules():
        for method in sorted((rule.methods or set()) - {"HEAD"}):
            pairs.append((method, _concrete(rule.rule)))
    return pairs


ROUTE_METHODS = _all_route_methods()


def test_route_inventory_is_what_we_expect():
    # 13 registered routes; OPTIONS is auto-added by Flask. HEAD is covered separately.
    # If a route is added, this count changes and forces a deliberate review of the gate.
    assert len(ROUTE_METHODS) == 26


@pytest.mark.parametrize("method,path", ROUTE_METHODS)
def test_every_route_and_method_requires_secret(method, path):
    client = dashboard.app.test_client()
    kwargs = {"json": {}} if method in ("POST", "PUT", "PATCH") else {}
    assert client.open(path, method=method, **kwargs).status_code == 401
    assert client.open(path, method=method, headers={HDR: "wrong"}, **kwargs).status_code == 401


@pytest.mark.parametrize("path", ["/", "/static/none.js", "/no-such-route", "/api/does-not-exist"])
def test_static_unknown_and_html_paths_are_gated(path):
    assert dashboard.app.test_client().get(path).status_code == 401


def test_head_is_gated():
    assert dashboard.app.test_client().head("/api/status").status_code == 401


@pytest.mark.parametrize("headers", [
    {},
    {HDR: ""},
    {HDR: TEST_SI_SECRET + " "},
    {HDR: TEST_SI_SECRET.upper()},
    {"Authorization": f"Bearer {TEST_SI_SECRET}"},
])
def test_missing_empty_padded_or_misplaced_secret_is_refused(headers):
    assert dashboard.app.test_client().get("/api/status", headers=headers).status_code == 401


def test_secret_in_query_string_is_not_accepted():
    client = dashboard.app.test_client()
    assert client.get(f"/api/status?{HDR}={TEST_SI_SECRET}").status_code == 401


def test_correct_secret_is_accepted():
    client = si_test_client(dashboard)
    assert client.get("/api/status").status_code == 200


def test_authenticated_post_to_unknown_opportunity_is_404_not_a_mutation():
    client = si_test_client(dashboard)
    resp = client.post("/api/opportunity/decide", json={"opportunity_id": "EVO-NONEXISTENT-SEC01", "decision_type": "reject"})
    assert resp.status_code == 404


def test_unset_server_secret_fails_closed_with_503():
    dashboard._SI_SECRET = ""
    client = si_test_client(dashboard)
    dashboard._SI_SECRET = ""
    assert client.get("/api/status").status_code == 503
    assert dashboard.app.test_client().get("/").status_code == 503


def test_comparison_is_constant_time():
    src = inspect.getsource(dashboard._require_si_secret)
    assert "compare_digest" in src
    assert "_SI_SECRET ==" not in src and "== _SI_SECRET" not in src


def test_secret_value_never_reaches_logs(caplog):
    caplog.set_level(logging.DEBUG)
    dashboard.app.test_client().get("/api/status", headers={HDR: "not-the-secret-value-xyz"})
    dashboard.app.test_client().get("/api/status", headers={HDR: TEST_SI_SECRET})
    dashboard.app.test_client().get("/api/status", headers={HDR: TEST_SI_SECRET + "x"})
    assert TEST_SI_SECRET not in caplog.text
    assert "not-the-secret-value-xyz" not in caplog.text
