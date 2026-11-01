"""Test configuration for intelligence/: see the autouse fixture below."""

import pytest


@pytest.fixture(autouse=True)
def _capacity_enforcement_on_for_legacy_tests(monkeypatch):
    """Capacity gating is advisory by default in production (owner decision 2026-10-18; see
    core/health/capacity_enforcement.py). The pre-existing gate tests assert the original D-055
    behaviour, so they run with enforcement on. Tests of the advisory default clear the variable."""
    monkeypatch.setenv("CAPACITY_ENFORCEMENT", "enforce")
