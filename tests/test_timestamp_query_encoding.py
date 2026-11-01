"""Timestamps sent to PostgREST must be valid and correctly encoded.

Two bugs, both found in the Supabase logs on 2026-09-28 (each request was a
400 that its caller silently degraded):

* A timezone-aware ``datetime.isoformat()`` already ends in ``+00:00``. In a
  query string a raw ``+`` decodes to a space ("2026-09-28T20:55:39 00:00"),
  so ``alert_silences``, the midday-signals query and the source-fidelity
  audit were all rejected — a planned-burn silence never applied.
* Appending ``"Z"`` to that value (``…+00:00Z``) is invalid for timestamptz,
  so every ``command_memory_records`` decision write from
  ``log_decision_to_command_memory`` failed.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
for sub in ("", "core/platform", "platform-runtime"):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))

import alert_silences
import command_memory_integration as cmi

import intelligence.captains_brief as cb
from intelligence.audit import source_fidelity

AWARE = datetime(2026, 9, 28, 20, 55, 39, 991184, tzinfo=timezone.utc)
AWARE_ISO = "2026-09-28T20:55:39.991184+00:00"


def _query_value(path: str, key: str) -> str:
    return parse_qs(urlparse(path).query, keep_blank_values=True)[key][0]


def test_list_active_silences_percent_encodes_the_timestamp():
    with patch.object(alert_silences, "supabase_get", return_value=[]) as get:
        alert_silences.list_active_silences(at=AWARE)
    path = get.call_args.args[0]
    assert "+00:00" not in path and "%2B00%3A00" in path
    # What PostgREST decodes is the original timestamp, not "…39 00:00".
    assert _query_value(path, "starts_at") == f"lte.{AWARE_ISO}"
    assert _query_value(path, "ends_at") == f"gte.{AWARE_ISO}"


def test_midday_signals_query_percent_encodes_since():
    with patch.object(cb, "_sb_request", return_value=[]) as req:
        cb._get_new_signals_since(AWARE_ISO)
    table, query = req.call_args.args
    assert table == "intelligence_events"
    assert "+00:00" not in query
    assert parse_qs(query)["collected_at"] == [f"gte.{AWARE_ISO}"]


def test_source_fidelity_queries_percent_encode_since():
    with patch.object(source_fidelity.intelligence_store, "_get", return_value=[]) as get:
        source_fidelity.source_fidelity_report(days=30)
    queries = [call.args[0] for call in get.call_args_list]
    assert queries, "expected the report to issue its queries"
    for query in queries:
        assert "+" not in query.split("?", 1)[1], query
        assert "%2B00%3A00" in query


def test_decision_record_timestamps_are_valid_timestamptz():
    fake = MagicMock()
    fake.insert.return_value = True
    with patch.object(cmi, "get_client", return_value=fake), \
         patch.object(cmi.id_registry, "next_id", return_value="DEC-0001"):
        cmi.log_decision_to_command_memory("We will ship", "Ready", "U001")
    _table, record = fake.insert.call_args.args
    for key in ("created_at", "updated_at"):
        assert not re.search(r"[+-]\d\d:\d\dZ$", record[key]), record[key]
        assert datetime.fromisoformat(record[key]).tzinfo is not None


def test_no_aware_isoformat_gets_a_z_suffix():
    """Regression guard: `<aware datetime>.isoformat() + "Z"` -> "…+00:00Z"."""
    pattern = re.compile(r"""\.isoformat\(\)\s*\+\s*["']Z["']""")
    skip_dirs = {".git", "node_modules", ".venv", "venv", "tests", "__pycache__"}
    offenders = []
    for path in ROOT.rglob("*.py"):
        if skip_dirs & set(path.relative_to(ROOT).parts) or path.name.startswith("test_") or path == Path(__file__):
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"aware isoformat() + 'Z' is invalid for timestamptz: {offenders}"
