"""
Contract test: every task_type scripts/self_improvement/router_client.py
calls must actually be wired up in core/model-router/app.py.

Real incident this catches: router_client.py's assess_external_candidate()
called self._call_router("hq-evolution-external-fit", ...) against a
task_type that had no TASK_POLICY entry and no TASK_ROUTES entry in app.py
— every call 404'd ("unknown route"), silently swallowed by
external_enrichment.enrich()'s fail-open per-candidate handling, so every
external HQ Evolution candidate kept its metadata-only discovery-time
fit/evidence_strength forever. tests/test_external_enrichment.py's suite
never caught this because it mocks ModelRouterClient._call_router directly
and never exercises the real server-side route — this test is the missing
client/server contract check.

Dotted-path import convention matches tests/test_model_router_guardrails.py
for app.py, tests/test_self_improvement_system.py for router_client.py.
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_ROUTER_DIR = REPO_ROOT / "core" / "model-router"
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(MODEL_ROUTER_DIR))
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

import app  # noqa: E402 - path setup above must run first

_CALL_ROUTER_TASK_TYPE = re.compile(r'self\._call_router\(\s*"([a-z0-9-]+)"')


def _task_types_used_by_router_client() -> set[str]:
    """Every task_type literal router_client.py actually passes to
    self._call_router(...) — read from source rather than hardcoded here,
    so a future client method is covered automatically without editing
    this test."""
    source = (SELF_IMPROVEMENT_DIR / "router_client.py").read_text()
    return set(_CALL_ROUTER_TASK_TYPE.findall(source))


class TestRouterClientTaskTypesAreWired(unittest.TestCase):
    def test_every_client_task_type_has_a_task_policy_entry(self):
        used = _task_types_used_by_router_client()
        self.assertTrue(used, "regex found no self._call_router(...) call sites — did router_client.py change shape?")
        missing = used - set(app.TASK_POLICY)
        self.assertEqual(missing, set(), f"task_type(s) called by router_client.py have no app.TASK_POLICY entry: {missing}")

    def test_every_client_task_type_has_a_route(self):
        used = _task_types_used_by_router_client()
        routed = set(app.TASK_ROUTES.values())
        missing = used - routed
        self.assertEqual(missing, set(), f"task_type(s) called by router_client.py have no app.TASK_ROUTES entry: {missing}")

    def test_task_routes_path_matches_its_task_type(self):
        """Every TASK_ROUTES path must be exactly /api/model/<task_type> —
        catches a copy-paste path/key mismatch, not just a missing entry."""
        for path, task_type in app.TASK_ROUTES.items():
            self.assertEqual(path, f"/api/model/{task_type}", f"path {path!r} does not match its task_type {task_type!r}")

    def test_every_task_route_has_a_task_policy_entry(self):
        """The reverse direction: a route pointing at a task_type
        TASK_POLICY doesn't know how to run would KeyError inside
        _run_task the first time it's actually hit."""
        missing = set(app.TASK_ROUTES.values()) - set(app.TASK_POLICY)
        self.assertEqual(missing, set(), f"TASK_ROUTES task_type(s) missing from TASK_POLICY: {missing}")


if __name__ == "__main__":
    unittest.main()
