"""Hygiene + freshness checks for tests/fixtures/emergency_alerts/.

Freshness: a captured snapshot older than 120 days emits a pytest warning; older
than 180 days FAILS. Refresh by re-capturing the feed (one fetch per URL via
base.http_get) and updating meta.json captured_at. Synthetic entries are exempt
(they are not a capture).
"""

from __future__ import annotations

import json
import re
import warnings
from datetime import datetime, timedelta, timezone

import pytest

from tests.emergency_alert_helpers import FIXTURE_ROOT

WARN_AFTER = timedelta(days=120)
FAIL_AFTER = timedelta(days=180)

SOURCES = sorted(p.name for p in FIXTURE_ROOT.iterdir() if p.is_dir())
EMAIL_RE = re.compile(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def freshness(captured_at: str, now: datetime) -> str:
    age = now - datetime.fromisoformat(captured_at)
    if age > FAIL_AFTER:
        return "fail"
    if age > WARN_AFTER:
        return "warn"
    return "ok"


def _meta(source):
    return json.loads((FIXTURE_ROOT / source / "meta.json").read_text(encoding="utf-8"))


def test_every_source_has_a_fixture():
    assert SOURCES == ["act_esa", "bom_nsw", "nsw_rfs", "qld_fire", "sa_cfs", "tas_fire", "vic_emergency", "wa_dfes"]


@pytest.mark.parametrize("source", SOURCES)
def test_meta_shape(source):
    meta = _meta(source)
    for key in ("source_key", "url", "captured_at", "captured_by", "notes"):
        assert meta.get(key), f"{source}/meta.json missing {key}"
    assert meta["captured_by"] == "claude-code"
    assert datetime.fromisoformat(meta["captured_at"]).tzinfo is not None, "captured_at must be an ISO timestamp with a UTC offset"
    for name, feed in meta["feeds"].items():
        assert (FIXTURE_ROOT / source / name).is_file(), f"{source}/{name} listed in meta.json but missing"
        assert isinstance(feed["synthetic"], bool)
    on_disk = {p.name for p in (FIXTURE_ROOT / source).iterdir()} - {"meta.json"}
    assert on_disk == set(meta["feeds"]), f"{source}: files on disk and meta.json feeds differ"


@pytest.mark.parametrize("source", SOURCES)
def test_fixture_size_is_within_trim_limit(source):
    for p in (FIXTURE_ROOT / source).iterdir():
        assert p.stat().st_size <= 500 * 1024, f"{p} exceeds the 500 KB fixture limit"


@pytest.mark.parametrize("source", SOURCES)
def test_no_email_addresses_in_fixtures(source):
    """Public repo: contact addresses in feeds are replaced with redacted@example.invalid."""
    for p in (FIXTURE_ROOT / source).iterdir():
        found = set(EMAIL_RE.findall(p.read_text(encoding="utf-8"))) - {"redacted@example.invalid"}
        assert not found, f"{p.name} contains email address(es); redact them"


def test_freshness_thresholds():
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert freshness((now - timedelta(days=119)).isoformat(), now) == "ok"
    assert freshness((now - timedelta(days=121)).isoformat(), now) == "warn"
    assert freshness((now - timedelta(days=179)).isoformat(), now) == "warn"
    assert freshness((now - timedelta(days=181)).isoformat(), now) == "fail"


@pytest.mark.parametrize("source", SOURCES)
def test_captured_snapshots_are_fresh(source):
    now = datetime.now(timezone.utc)
    for name, feed in _meta(source)["feeds"].items():
        if feed["synthetic"]:
            continue
        status = freshness(feed["captured_at"], now)
        if status == "warn":
            warnings.warn(f"{source}/{name} snapshot is older than 120 days (captured {feed['captured_at']}); re-capture it soon", UserWarning, stacklevel=1)
        assert status != "fail", f"{source}/{name} snapshot is older than 180 days (captured {feed['captured_at']}): re-capture it"
