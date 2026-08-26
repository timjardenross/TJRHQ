"""Emergency Alert Hub adapters — one module per Tier 1 AU jurisdiction source.

See repo-root Emergency_Alert_Hub_Workbench_Mission_and_Scope.md and migration
0174_emergency_alert_hub.sql. Each adapter exposes `fetch() -> list[CanonicalAlert]`
and is called by intelligence/emergency_alerts.py, which handles dedupe,
persistence, and per-source heartbeat recording — adapters never touch the
database directly.
"""
