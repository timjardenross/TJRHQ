"""Allowed values for the `alerts` table's CHECK-constrained columns.

The alerts table (migration 0174, widened by 0244) has CHECK constraints on
`severity` and `alert_type`, and the orchestrator upserts one source's rows in
a single request - so ONE out-of-set value fails the whole source and every
real alert in that batch goes unrecorded (and, via absence-based expiry,
could later read as a false "lifted"). intelligence/emergency_alerts.py
therefore coerces an out-of-set value to the safe default ('other' /
'unknown') before upsert instead of dropping the row.

These sets MUST match the migrations. tests/test_alert_schema_drift.py parses
the CHECK lists out of the migration SQL and fails if they diverge: when a
migration widens either constraint, update the frozenset here in the same PR.
"""

from __future__ import annotations

# alerts.severity - migration 0174.
ALLOWED_SEVERITY: frozenset[str] = frozenset({
    "emergency_warning",
    "watch_and_act",
    "advice",
    "unknown",
})

# alerts.alert_type - last set by migration 0244 (adds thunderstorm_asthma).
ALLOWED_ALERT_TYPE: frozenset[str] = frozenset({
    "bushfire",
    "flood",
    "storm",
    "cyclone",
    "heatwave",
    "hazard_reduction",
    "structure_fire",
    "severe_weather",
    "tsunami",
    "thunderstorm_asthma",
    "other",
})

DEFAULT_ALERT_TYPE = "other"
DEFAULT_SEVERITY = "unknown"
