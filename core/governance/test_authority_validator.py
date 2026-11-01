"""Tests for core/governance/authority_validator.py — EXEC-001 WP1.

2026-09-15 adversarial review: authority_validator.py and
authority_enforcement.py had zero test coverage despite being the whole
platform's officer-authority gate (Waves 3/4 changed its default from
fail-open to fail-closed). Writing tests surfaced that
governance/authority/ — the manifest directory the whole module is built
around — never existed in the repo, so every check always hit the
manifest-gap branch; the gap was then silently swallowed by both real call
sites' exception handling, so the gate was 100% fail-open in practice
everywhere. Both bugs are fixed (manifests added, call sites now treat a
gap as a denial) as of this same review — these tests lock in the fixed
behaviour and would have caught the regression.

Run: python3 -m pytest core/governance/test_authority_validator.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from core.governance import authority_validator as av

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_manifest_cache():
    """load_manifest() caches by design (manifests are static governance
    documents) — clear it around every test so one test's manifest read
    can't leak into another's, and so monkeypatched manifests don't stick."""
    av._manifest_cache.clear()
    yield
    av._manifest_cache.clear()


@pytest.fixture
def restrictive_manifest(monkeypatch):
    """A manifest with real allow/deny/approval content, for exercising
    every branch of can_officer()/requires_approval() — distinct from the
    real baseline manifests in governance/authority/, which are
    deliberately unrestricted."""
    manifest = {
        "officer": "test_restrictive",
        "allowed_actions": ["read_report", "propose_mission"],
        "disallowed_actions": ["delete_mission"],
        "requires_captain": ["propose_mission"],
        "requires_xo": ["read_report"],
        "requires_number_one": [],
    }
    monkeypatch.setitem(av._manifest_cache, "test_restrictive", manifest)
    return manifest


# ---------------------------------------------------------------------------
# load_manifest / load_all_manifests
# ---------------------------------------------------------------------------

class TestLoadManifest:
    def test_loads_real_baseline_manifest(self):
        """governance/authority/number_one.yaml exists post-fix — this is
        the regression test for the manifest directory not existing at
        all (2026-09-15 finding)."""
        manifest = av.load_manifest("number_one")
        assert manifest, "number_one.yaml must exist and load non-empty"
        assert manifest["officer"] == "number_one"

    def test_missing_officer_returns_empty_dict(self):
        assert av.load_manifest("definitely_not_a_real_officer_slug") == {}

    def test_officer_slug_normalisation(self):
        """'Number One' / 'number-one' / 'number_one' must all resolve to
        the same manifest file (key = lower, spaces/hyphens -> underscore)."""
        assert av.load_manifest("Number One") == av.load_manifest("number_one")
        assert av.load_manifest("number-one") == av.load_manifest("number_one")

    def test_caches_after_first_load(self):
        first = av.load_manifest("number_one")
        av._manifest_cache["number_one"]["officer"] = "mutated-to-prove-cache-hit"
        second = av.load_manifest("number_one")
        assert second["officer"] == "mutated-to-prove-cache-hit"
        assert first is second

    def test_load_all_manifests_includes_known_baseline_officers(self):
        all_manifests = av.load_all_manifests()
        for officer in ("number_one", "xo", "human_systems", "engineering"):
            assert officer in all_manifests


# ---------------------------------------------------------------------------
# can_officer — manifest gap semantics (the actual bug this review found)
# ---------------------------------------------------------------------------

class TestManifestGapSemantics:
    def test_raise_mode_raises_manifest_gap_error(self, monkeypatch):
        monkeypatch.setattr(av, "_MANIFEST_GAP_MODE", "raise")
        with pytest.raises(av.ManifestGapError) as exc_info:
            av.can_officer("no_such_officer", "some_action")
        assert exc_info.value.officer == "no_such_officer"
        assert exc_info.value.action == "some_action"

    def test_log_mode_fails_open_with_explanatory_reason(self, monkeypatch):
        monkeypatch.setattr(av, "_MANIFEST_GAP_MODE", "log")
        approved, reason = av.can_officer("no_such_officer", "some_action")
        assert approved is True
        assert "gap" in reason.lower()

    def test_manifest_gap_error_is_not_an_authority_error(self):
        """ManifestGapError and AuthorityError are siblings, not
        parent/child — a caller catching only `except AuthorityError` will
        NOT catch a manifest gap. This is exactly the bug both real call
        sites had (core/coordination/execution_engine.py,
        platform-runtime/command_memory_integration.py) before this
        review's fix — asserting the class relationship so a future
        refactor that accidentally unifies them doesn't silently
        reintroduce a false sense of safety in code that only catches one."""
        assert not issubclass(av.ManifestGapError, av.AuthorityError)
        assert not issubclass(av.AuthorityError, av.ManifestGapError)


# ---------------------------------------------------------------------------
# can_officer — allow/deny logic against a populated manifest
# ---------------------------------------------------------------------------

class TestCanOfficer:
    def test_explicit_disallow_wins(self, restrictive_manifest):
        approved, reason = av.can_officer("test_restrictive", "delete_mission")
        assert approved is False
        assert "disallowed" in reason.lower()

    def test_allowlist_permits_listed_action(self, restrictive_manifest):
        approved, _ = av.can_officer("test_restrictive", "read_report")
        assert approved is True

    def test_allowlist_denies_unlisted_action(self, restrictive_manifest):
        approved, reason = av.can_officer("test_restrictive", "launch_nukes")
        assert approved is False
        assert "not in the allowed_actions" in reason.lower()

    def test_disallow_checked_before_allowlist(self, monkeypatch):
        """An action in BOTH allowed_actions and disallowed_actions must be
        denied — explicit disallow takes priority (documented behaviour)."""
        manifest = {
            "officer": "test_conflict",
            "allowed_actions": ["ambiguous_action"],
            "disallowed_actions": ["ambiguous_action"],
        }
        monkeypatch.setitem(av._manifest_cache, "test_conflict", manifest)
        approved, _reason = av.can_officer("test_conflict", "ambiguous_action")
        assert approved is False

    def test_empty_allowed_actions_means_no_allowlist_restriction(self):
        """The 13 real baseline manifests (2026-09-15) all ship with
        allowed_actions: [] — this must mean "no allowlist restriction",
        not "nothing is allowed", or every real officer would be
        permanently locked out."""
        approved, reason = av.can_officer("number_one", "any_action_whatsoever")
        assert approved is True
        assert reason == "permitted"


# ---------------------------------------------------------------------------
# requires_approval
# ---------------------------------------------------------------------------

class TestRequiresApproval:
    def test_returns_none_for_self_authorised_action(self, restrictive_manifest):
        assert av.requires_approval("test_restrictive", "delete_mission") is None

    def test_returns_captain_tier(self, restrictive_manifest):
        assert av.requires_approval("test_restrictive", "propose_mission") == "captain"

    def test_returns_xo_tier(self, restrictive_manifest):
        assert av.requires_approval("test_restrictive", "read_report") == "xo"

    def test_missing_manifest_returns_none_not_a_raise(self):
        """requires_approval() deliberately does NOT raise ManifestGapError
        on a missing manifest (unlike can_officer) — documented behaviour,
        asserted so it doesn't silently change."""
        assert av.requires_approval("no_such_officer_at_all", "anything") is None


# ---------------------------------------------------------------------------
# validate_or_raise
# ---------------------------------------------------------------------------

class TestValidateOrRaise:
    def test_raises_authority_error_on_denial(self, restrictive_manifest):
        with pytest.raises(av.AuthorityError):
            av.validate_or_raise("test_restrictive", "delete_mission")

    def test_does_not_raise_on_permitted_action(self, restrictive_manifest):
        av.validate_or_raise("test_restrictive", "read_report")  # must not raise


# ---------------------------------------------------------------------------
# audit_authority_action — must never raise even when Supabase is unavailable
# ---------------------------------------------------------------------------

class TestAuditAuthorityAction:
    def test_non_blocking_when_supabase_disabled(self, monkeypatch):
        class _DisabledClient:
            def is_enabled(self):
                return False

        monkeypatch.setattr(
            "tools.supabase.client.CommanderSupabaseClient", lambda: _DisabledClient()
        )
        av.audit_authority_action(
            officer="number_one", action="assign_mission_owner",
            approved=True, reason="test",
        )  # must not raise

    def test_non_blocking_when_client_import_fails(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def _raising_import(name, *args, **kwargs):
            if name == "tools.supabase.client":
                raise ImportError("simulated: module unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _raising_import)
        av.audit_authority_action(
            officer="number_one", action="assign_mission_owner",
            approved=True, reason="test",
        )  # must not raise
