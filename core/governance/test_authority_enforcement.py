"""Tests for core/governance/authority_enforcement.py — EXEC-001 WP1 / MSN-0326 Wave 4.

2026-09-15 adversarial review: zero test coverage before this file (see
test_authority_validator.py's module docstring for the manifest-gap bug
this review also found and fixed). Covers enforce_authority() and
AuthorityContext: permit/deny, captain_override, and Wave 4's
approval-blocking default.

Run: python3 -m pytest core/governance/test_authority_enforcement.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from core.governance import authority_enforcement as ae
from core.governance import authority_validator as av


@pytest.fixture(autouse=True)
def _clear_manifest_cache():
    av._manifest_cache.clear()
    yield
    av._manifest_cache.clear()


@pytest.fixture(autouse=True)
def _no_real_audit_writes(monkeypatch):
    """Every enforcement path audits — stub it out so tests never depend
    on (or accidentally hit) live Supabase."""
    monkeypatch.setattr(av, "audit_authority_action", lambda **kwargs: None)


@pytest.fixture
def permissive_manifest(monkeypatch):
    manifest = {"officer": "test_officer", "allowed_actions": [], "disallowed_actions": []}
    monkeypatch.setitem(av._manifest_cache, "test_officer", manifest)
    return manifest


@pytest.fixture
def denying_manifest(monkeypatch):
    manifest = {"officer": "test_officer", "disallowed_actions": ["forbidden_action"]}
    monkeypatch.setitem(av._manifest_cache, "test_officer", manifest)
    return manifest


@pytest.fixture
def approval_gated_manifest(monkeypatch):
    manifest = {
        "officer": "test_officer",
        "allowed_actions": [],
        "requires_captain": ["gated_action"],
    }
    monkeypatch.setitem(av._manifest_cache, "test_officer", manifest)
    return manifest


# ---------------------------------------------------------------------------
# enforce_authority decorator
# ---------------------------------------------------------------------------

class TestEnforceAuthorityDecorator:
    def test_permits_and_calls_wrapped_function(self, permissive_manifest):
        @ae.enforce_authority(officer="test_officer", action="do_thing")
        def fn(x):
            return x * 2

        assert fn(21) == 42

    def test_denies_and_raises_without_calling_wrapped_function(self, denying_manifest):
        calls = []

        @ae.enforce_authority(officer="test_officer", action="forbidden_action")
        def fn():
            calls.append(1)

        with pytest.raises(av.AuthorityError):
            fn()
        assert calls == [], "wrapped function must not run when authority is denied"

    def test_captain_override_bypasses_denial(self, denying_manifest):
        @ae.enforce_authority(
            officer="test_officer", action="forbidden_action", captain_override=True
        )
        def fn():
            return "ran"

        assert fn() == "ran"

    def test_approval_blocking_raises_when_required_and_no_override(
        self, approval_gated_manifest
    ):
        @ae.enforce_authority(
            officer="test_officer", action="gated_action", require_approval_blocking=True
        )
        def fn():
            return "ran"

        with pytest.raises(av.AuthorityError):
            fn()

    def test_approval_blocking_disabled_lets_action_proceed(self, approval_gated_manifest):
        """MSN-0326 Wave 4 rollback path: require_approval_blocking=False
        (or AUTHORITY_APPROVAL_BLOCKING=false) reverts to pre-Wave-4
        "approval assumed at call site" behaviour — must still work."""
        @ae.enforce_authority(
            officer="test_officer", action="gated_action", require_approval_blocking=False
        )
        def fn():
            return "ran"

        assert fn() == "ran"

    def test_captain_override_bypasses_approval_block(self, approval_gated_manifest):
        @ae.enforce_authority(
            officer="test_officer",
            action="gated_action",
            captain_override=True,
            require_approval_blocking=True,
        )
        def fn():
            return "ran"

        assert fn() == "ran"


# ---------------------------------------------------------------------------
# AuthorityContext context manager
# ---------------------------------------------------------------------------

class TestAuthorityContext:
    def test_permits_entry_and_runs_body(self, permissive_manifest):
        ran = []
        with ae.AuthorityContext(officer="test_officer", action="do_thing"):
            ran.append(1)
        assert ran == [1]

    def test_denies_and_raises_before_body_runs(self, denying_manifest):
        ran = []
        with pytest.raises(av.AuthorityError), ae.AuthorityContext(
            officer="test_officer", action="forbidden_action"
        ):
            ran.append(1)  # pragma: no cover - must never execute
        assert ran == []

    def test_captain_override_bypasses_denial(self, denying_manifest):
        ran = []
        with ae.AuthorityContext(
            officer="test_officer", action="forbidden_action", captain_override=True
        ):
            ran.append(1)
        assert ran == [1]

    def test_approval_blocking_raises_before_body_runs(self, approval_gated_manifest):
        ran = []
        with pytest.raises(av.AuthorityError), ae.AuthorityContext(
            officer="test_officer", action="gated_action", require_approval_blocking=True
        ):
            ran.append(1)  # pragma: no cover - must never execute
        assert ran == []


# ---------------------------------------------------------------------------
# Manifest-gap behaviour through the enforcement layer
# ---------------------------------------------------------------------------

class TestManifestGapThroughEnforcement:
    def test_enforce_authority_propagates_manifest_gap_in_raise_mode(self, monkeypatch):
        """2026-09-15 finding: this exact path (a decorated call for an
        officer with no manifest) is what silently proceeded in both real
        call sites before this review's fix, because ManifestGapError
        wasn't caught alongside AuthorityError. At the enforcement-layer
        level (no caller-side try/except to interfere), the gap must
        surface as an exception, not a quiet pass-through."""
        monkeypatch.setattr(av, "_MANIFEST_GAP_MODE", "raise")

        @ae.enforce_authority(officer="brand_new_unmanifested_officer", action="anything")
        def fn():
            return "should not run"

        with pytest.raises(av.ManifestGapError):
            fn()
