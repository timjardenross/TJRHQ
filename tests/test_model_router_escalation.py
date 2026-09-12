"""
Regression tests for FND-001: core/model-router/app.py's escalate /
fallback-complex routing.

Root cause (see app.py's MODEL_CLOUD / _resolve_cloud_escalation() comments
for the full history): MODEL_CLOUD (glm-5.3:cloud) was configured as the
cloud escalation target in the 2026-09-08 GLM 5.3 migration, but the tag was
never actually pulled/registered on this VM's Ollama install.
_available_model_names() correctly detected this on every call and correctly
triggered the router's fallback — but that fallback was unconditionally
MODEL_LARGE (mistral-small3.2:24b), a 24B model this CPU-only, no-GPU,
8-core host cannot serve within any real timeout. call_log.jsonl showed
repeated genuine 300s timeouts on this path.

The fix replaces the single-step fallback with a real degrade chain
(_resolve_cloud_escalation()): preferred cloud -> approved alternate cloud
-> host-safe local model (gemma3:4b) — MODEL_LARGE is never an automatic
degrade target again.

These tests exercise _resolve_cloud_escalation() directly, mocking
_available_model_names() — never touches real Ollama, Ollama Cloud, or
network. Dotted-path import convention matches
tests/test_batch_coding_pr_error.py.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_ROUTER_DIR = REPO_ROOT / "core" / "model-router"
sys.path.insert(0, str(MODEL_ROUTER_DIR))

import app


class CloudPrimaryAvailableTest(unittest.TestCase):
    """Invariant 1: a configured and reachable cloud model routes successfully."""

    def test_escalate_uses_preferred_cloud_when_available(self):
        policy = dict(app.TASK_POLICY["escalate"])
        with patch.object(app, "_available_model_names", return_value={app.MODEL_CLOUD}):
            resolved, tier, reason = app._resolve_cloud_escalation("escalate", policy)
        self.assertEqual(resolved["model"], app.MODEL_CLOUD)
        self.assertEqual(tier, "cloud_primary")
        self.assertEqual(reason, "")

    def test_fallback_complex_uses_preferred_cloud_when_available(self):
        policy = dict(app.TASK_POLICY["fallback-complex"])
        with patch.object(app, "_available_model_names", return_value={app.MODEL_CLOUD}):
            resolved, tier, _reason = app._resolve_cloud_escalation("fallback-complex", policy)
        self.assertEqual(resolved["model"], app.MODEL_CLOUD)
        self.assertEqual(tier, "cloud_primary")


class CloudPrimaryUnavailableTest(unittest.TestCase):
    """Invariants 2 & 6: an unavailable preferred cloud model must fall
    through to the approved alternate cloud, NEVER straight to a
    host-unsafe heavy local model, and must never silently select a
    300s-class CPU fallback."""

    def test_falls_back_to_alternate_cloud_not_local(self):
        policy = dict(app.TASK_POLICY["escalate"])
        with patch.object(app, "_available_model_names", return_value={app.MODEL_CLOUD_ALT}):
            resolved, tier, _reason = app._resolve_cloud_escalation("escalate", policy)
        self.assertEqual(resolved["model"], app.MODEL_CLOUD_ALT)
        self.assertEqual(tier, "cloud_alt")
        self.assertNotEqual(resolved["model"], app.MODEL_LARGE)

    def test_fallback_complex_also_prefers_alternate_cloud(self):
        policy = dict(app.TASK_POLICY["fallback-complex"])
        with patch.object(app, "_available_model_names", return_value={app.MODEL_CLOUD_ALT}):
            resolved, tier, _reason = app._resolve_cloud_escalation("fallback-complex", policy)
        self.assertEqual(resolved["model"], app.MODEL_CLOUD_ALT)
        self.assertEqual(tier, "cloud_alt")


class BothCloudsUnavailableTest(unittest.TestCase):
    """Invariant 2 (the actual FND-001 reproduction) & 6: when NEITHER cloud
    route is available, the router must degrade to the host-safe local
    model, never to MODEL_LARGE, and never silently — a route_reason must
    be present so the degrade is observable."""

    def test_escalate_degrades_to_safe_local_never_model_large(self):
        policy = dict(app.TASK_POLICY["escalate"])
        with patch.object(app, "_available_model_names", return_value=set()):
            resolved, tier, reason = app._resolve_cloud_escalation("escalate", policy)
        self.assertEqual(resolved["model"], app.MODEL_ESCALATION_SAFE_LOCAL)
        self.assertNotEqual(resolved["model"], app.MODEL_LARGE)
        self.assertEqual(tier, "local_safe_degraded")
        self.assertTrue(reason)  # fallback reason must be observable, not blank

    def test_fallback_complex_degrades_to_safe_local_never_model_large(self):
        policy = dict(app.TASK_POLICY["fallback-complex"])
        with patch.object(app, "_available_model_names", return_value=set()):
            resolved, tier, _reason = app._resolve_cloud_escalation("fallback-complex", policy)
        self.assertEqual(resolved["model"], app.MODEL_ESCALATION_SAFE_LOCAL)
        self.assertNotEqual(resolved["model"], app.MODEL_LARGE)
        self.assertEqual(tier, "local_safe_degraded")

    def test_only_unrelated_local_models_present_still_degrades_safely(self):
        """The exact FND-001 reproduction: neither cloud tag registered,
        only unrelated local models present (mirrors this host's real
        `ollama list` before glm-5.3:cloud was pulled)."""
        policy = dict(app.TASK_POLICY["escalate"])
        with patch.object(
            app,
            "_available_model_names",
            return_value={"qwen3.5:9b", "gemma3:4b", "mistral-small3.2:24b"},
        ):
            resolved, tier, _reason = app._resolve_cloud_escalation("escalate", policy)
        self.assertEqual(resolved["model"], app.MODEL_ESCALATION_SAFE_LOCAL)
        self.assertEqual(tier, "local_safe_degraded")


class FndOo1SafetyInvariantTest(unittest.TestCase):
    """Invariant 6, asserted structurally: MODEL_LARGE must not appear
    anywhere in _resolve_cloud_escalation()'s possible outputs, for any
    availability state. This is the actual regression guard for FND-001 —
    it fails if a future edit reintroduces MODEL_LARGE as a degrade target."""

    def test_model_large_unreachable_from_escalation_chain_in_any_state(self):
        possible_available_sets = [
            set(),
            {app.MODEL_CLOUD},
            {app.MODEL_CLOUD_ALT},
            {app.MODEL_CLOUD, app.MODEL_CLOUD_ALT},
            {app.MODEL_LARGE},  # even when MODEL_LARGE itself IS installed, it must not be selected
            {app.MODEL_LARGE, "gemma3:4b"},
        ]
        for task_type in ("escalate", "fallback-complex"):
            policy = dict(app.TASK_POLICY[task_type])
            for available in possible_available_sets:
                with patch.object(app, "_available_model_names", return_value=available):
                    resolved, _tier, _reason = app._resolve_cloud_escalation(task_type, policy)
                self.assertNotEqual(
                    resolved["model"], app.MODEL_LARGE,
                    f"escalation chain selected MODEL_LARGE for task_type={task_type}, "
                    f"available={available} — FND-001 regression",
                )


class RouteObservabilityTest(unittest.TestCase):
    """Invariant 5: escalate and fallback-complex both surface which tier
    served the request via route_tier/route_reason, not just a bare model
    name — needed to distinguish a genuine cloud response from a degrade."""

    def test_route_tier_present_for_every_state(self):
        policy = dict(app.TASK_POLICY["escalate"])
        for available, expected_tier in (
            ({app.MODEL_CLOUD}, "cloud_primary"),
            ({app.MODEL_CLOUD_ALT}, "cloud_alt"),
            (set(), "local_safe_degraded"),
        ):
            with patch.object(app, "_available_model_names", return_value=available):
                _resolved, tier, _reason = app._resolve_cloud_escalation("escalate", policy)
            self.assertEqual(tier, expected_tier)


class RunTaskExceptionPathTest(unittest.TestCase):
    """Invariant 4: an exception/error from the resolved model's own call
    (bad key, provider down, model not found) must surface as an explicit
    failure — it must NOT retry against MODEL_LARGE or any other unresolved
    tier. _resolve_cloud_escalation() runs once, before the try/except in
    _run_task(); there is no secondary fallback path inside the except
    blocks, which this test locks in structurally."""

    def test_ollama_failure_after_resolution_returns_explicit_failure_not_model_large(self):
        with patch.object(app, "_available_model_names", return_value=set()):
            with patch.object(
                app, "_ollama_generate", side_effect=TimeoutError("simulated: timed out")
            ) as mocked_generate:
                result = app._run_task("escalate", "does the captain need this now?", {})

        self.assertFalse(result["success"])
        self.assertEqual(result["model"], app.MODEL_ESCALATION_SAFE_LOCAL)
        self.assertNotEqual(result["model"], app.MODEL_LARGE)
        self.assertEqual(result["route_tier"], "local_safe_degraded")
        # Exactly one attempt — no silent retry against a different model/tier.
        mocked_generate.assert_called_once()
        called_model = mocked_generate.call_args[0][0]
        self.assertEqual(called_model, app.MODEL_ESCALATION_SAFE_LOCAL)
        self.assertNotEqual(called_model, app.MODEL_LARGE)


if __name__ == "__main__":
    unittest.main()
