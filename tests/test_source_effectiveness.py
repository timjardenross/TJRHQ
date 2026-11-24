from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from intelligence import source_effectiveness as se

NOW = datetime(2026, 11, 24, 6, tzinfo=timezone.utc)
EV = {"quiet_verifications": [{"source_name": "Quiet Feed", "verified_on": "2026-11-24", "newest_item_on_source": "2026-10-01", "method": "x"}],
      "coverage_gaps": [{"sector": "telecommunications", "provider": "Telstra", "reason": "form-gated"}]}


def row(**kw):
    base = {"source_name": "S", "active": True, "n7": 0, "n30": 0, "checks7": 14, "bad7": 0, "last_check": "2026-11-23T19:03:00+00:00"}
    base.update(kw)
    return base


def test_states():
    assert se.classify_source(row(n30=12, n7=3), EV, NOW)[0] == se.HEALTHY
    assert se.classify_source(row(bad7=14, source_name="ASIC News Centre"), EV, NOW)[0] == se.BROKEN
    assert se.classify_source(row(bad7=5), EV, NOW)[0] == se.DEGRADED
    assert se.classify_source(row(checks7=0, last_check=None), EV, NOW)[0] == se.BROKEN
    assert se.classify_source(row(last_check="2026-11-20T19:00:00+00:00", n30=4), EV, NOW)[0] == se.DEGRADED
    assert se.classify_source(row(source_name="Quiet Feed"), EV, NOW)[0] == se.QUIET
    assert se.classify_source(row(source_name="Unknown Quiet"), EV, NOW)[0] == se.UNVERIFIED
    assert se.classify_source(row(active=False), EV, NOW)[0] == se.UNCOVERED


def test_zero_items_without_a_probe_is_never_called_quiet():
    assert se.classify_source(row(n30=0), EV, NOW)[0] == se.UNVERIFIED


def test_declared_gaps_are_listed_as_uncovered_and_summarised():
    res = se.classify_all([row(n30=3)], EV, NOW)
    assert se.summarise(res)[se.UNCOVERED] == 1 and any("Telstra" in c["source_name"] for c in res)


def test_shipped_evidence_file_is_valid():
    ev = se.load_evidence()
    assert {g["provider"] for g in ev["coverage_gaps"]} >= {"Telstra", "ASX", "ACMA"}
    assert all("verified_on" in v for v in ev["quiet_verifications"])


def test_parity_fixture_matches_recorded_expectations():
    """Same fixture is classified by lcars-portal/src/lib/sourceEffectiveness.ts (vitest); both must equal `expected`."""
    import json

    fx = json.loads((_REPO / "tests" / "fixtures" / "source_effectiveness_parity.json").read_text(encoding="utf-8"))
    now, ev, rows = datetime.fromisoformat(fx["now"]), fx["evidence"], fx["rows"]
    exp = fx["expected"]
    classified = se.classify_all(rows, ev, now)
    assert classified == exp["classified"] and se.summarise(classified) == exp["summary"]
    assert sorted(x["key"] for x in se.material_exceptions(rows, ev, now)) == exp["material"]
    lim = se.coverage_limitations(rows, ev, now)
    assert lim == exp["limitations"] and se.limitations_line(lim) == exp["limitations_line"]


def test_portal_evidence_copy_is_identical():
    import json

    portal = _REPO / "lcars-portal" / "src" / "config" / "source_effectiveness.json"
    assert json.loads(portal.read_text(encoding="utf-8")) == se.load_evidence()
