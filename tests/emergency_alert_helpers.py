"""Shared helpers for the emergency-alert adapter snapshot tests.

Fixtures live in tests/fixtures/emergency_alerts/<source_key>/ (see each
meta.json for where/when it was captured, what was redacted, and which files
are synthetic). Tests using these helpers are offline: `block_network` makes
any attempt to reach the network fail the test.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "core" / "platform"))

import alert_schema

FIXTURE_ROOT = REPO / "tests" / "fixtures" / "emergency_alerts"


def fixture_bytes(source: str, name: str) -> bytes:
    return (FIXTURE_ROOT / source / name).read_bytes()


def fixture_text(source: str, name: str) -> str:
    return (FIXTURE_ROOT / source / name).read_text(encoding="utf-8")


def fixture_json(source: str, name: str):
    return json.loads(fixture_bytes(source, name))


def fixture_meta(source: str) -> dict:
    return json.loads((FIXTURE_ROOT / source / "meta.json").read_text(encoding="utf-8"))


def by(alerts, attr: str) -> dict:
    return dict(Counter(getattr(a, attr) for a in alerts))


def assert_in_schema(alerts) -> None:
    """No output value falls outside the alerts table's CHECK sets."""
    bad_sev = {a.severity for a in alerts} - alert_schema.ALLOWED_SEVERITY
    bad_type = {a.alert_type for a in alerts} - alert_schema.ALLOWED_ALERT_TYPE
    assert not bad_sev, f"severity outside schema: {bad_sev}"
    assert not bad_type, f"alert_type outside schema: {bad_type}"


@pytest.fixture
def block_network(monkeypatch):
    """Fail loudly if anything under test tries to reach the network."""
    def _blocked(*args, **kwargs):
        raise AssertionError("network access attempted in an offline emergency-alert test")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    from intelligence.ingestion.emergency_alert_adapters import base
    monkeypatch.setattr(base, "http_get", _blocked)
    monkeypatch.setattr(base, "http_get_json", _blocked)
    return _blocked
