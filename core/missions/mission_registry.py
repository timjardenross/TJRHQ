"""SQLite-backed mission registry.

Retired as the runtime mission store under MSN-EDO-005 (superseded by the
canonical file/Supabase path in `MissionRegistryMemoryAdapter._load_from_files`),
but explicitly retained as a test fixture usable via the adapter's `registry=`
dependency-injection API — see core/coordination/mission_registry_memory_adapter.py.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_JSON_COLUMNS = {
    "assigned_specialists",
    "dependencies",
    "blockers",
    "evidence_links",
    "decision_log",
    "tags",
    "blocking_defects",
    "closure_audit_trail",
}

_COLUMNS = [
    "mission_id", "title", "description", "domain", "division", "assigned_role",
    "assigned_specialists", "priority", "status", "source", "created_at", "updated_at",
    "due_date", "next_action", "dependencies", "blockers", "evidence_links",
    "completion_notes", "deferral_reason", "cancellation_reason", "adoption_rating",
    "decision_log", "tags", "expected_behaviour", "actual_behaviour", "validation_method",
    "validation_result", "validation_evidence_link", "blocking_defects",
    "closure_submitted_by", "closure_submitted_at", "number_one_reviewed_by",
    "number_one_reviewed_at", "number_one_approval", "number_one_notes",
    "xo_approved_by", "xo_approved_at", "xo_notes", "closure_audit_trail",
]


class MissionRegistry:
    """Minimal SQLite mission store: schema creation + read-only listing."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        try:
            other_columns = ", ".join(f"{c} TEXT" for c in _COLUMNS if c != "mission_id")
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS missions (mission_id TEXT PRIMARY KEY, {other_columns})"
            )
            conn.commit()
        finally:
            conn.close()

    def list_missions(self) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM missions").fetchall()  # nosec B608 - _COLUMNS is a fixed internal constant, not user input
        finally:
            conn.close()

        missions = []
        for row in rows:
            mission = dict(row)
            for column in _JSON_COLUMNS:
                raw = mission.get(column)
                if raw:
                    try:
                        mission[column] = json.loads(raw)
                    except (TypeError, json.JSONDecodeError):
                        pass
            missions.append(mission)
        return missions
