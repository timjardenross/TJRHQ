"""Drift guard: core/platform/alert_schema.py must equal the alerts table's CHECK lists.

If this fails, a migration changed (or a frozenset was edited) without the other.
Update core/platform/alert_schema.py in the same PR as the migration.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "core" / "platform"))

import alert_schema

MIGRATIONS = REPO / "core" / "infrastructure" / "supabase" / "migrations"

_ITEM_RE = re.compile(r"'([^']+)'")


def _migration_number(path: Path) -> int:
    return int(path.name.split("_", 1)[0])


def _check_list(sql: str, column: str, constraint: str | None) -> set[str] | None:
    """The quoted values of `<column> ... check (<column> in ( ... ))`, either as an
    inline column check (0174) or `add constraint <constraint> check (...)`."""
    patterns = []
    if constraint:
        patterns.append(rf"add\s+constraint\s+{constraint}\s+check\s*\(\s*{column}\s+in\s*\((.*?)\)\s*\)")
    patterns.append(rf"\b{column}\s+text\s+not\s+null\s+default\s+'[^']*'\s+check\s*\(\s*{column}\s+in\s*\((.*?)\)\s*\)")
    for pattern in patterns:
        m = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
        if m:
            return set(_ITEM_RE.findall(m.group(1)))
    return None


def _latest_definition(file_filter: str, column: str, constraint: str) -> tuple[Path, set[str]]:
    """Highest-numbered migration (among those mentioning `file_filter`) that defines the list."""
    found: list[tuple[int, Path, set[str]]] = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        if file_filter not in sql:
            continue
        values = _check_list(sql, column, constraint)
        if values:
            found.append((_migration_number(path), path, values))
    assert found, f"no migration defines {constraint}"
    _, path, values = max(found, key=lambda t: t[0])
    return path, values


def test_severity_set_matches_migration():
    path, values = _latest_definition("create table if not exists alerts", "severity", "alerts_severity_check")
    assert alert_schema.ALLOWED_SEVERITY == values, (
        f"alert_schema.ALLOWED_SEVERITY drifted from {path.name}: "
        f"only in python {sorted(alert_schema.ALLOWED_SEVERITY - values)}, only in sql {sorted(values - alert_schema.ALLOWED_SEVERITY)}"
    )


def test_alert_type_set_matches_latest_migration():
    path, values = _latest_definition("alerts_alert_type_check", "alert_type", "alerts_alert_type_check")
    assert alert_schema.ALLOWED_ALERT_TYPE == values, (
        f"alert_schema.ALLOWED_ALERT_TYPE drifted from {path.name}: "
        f"only in python {sorted(alert_schema.ALLOWED_ALERT_TYPE - values)}, only in sql {sorted(values - alert_schema.ALLOWED_ALERT_TYPE)}"
    )


def test_alert_type_source_migration_is_the_latest_that_touches_the_constraint():
    """Guards the guard: if a newer migration drops/re-adds the constraint in a shape the
    parser cannot read, the test above would silently keep reading an older one."""
    touching = [p for p in MIGRATIONS.glob("*.sql") if "alerts_alert_type_check" in p.read_text(encoding="utf-8")]
    latest_touching = max(touching, key=_migration_number)
    path, _ = _latest_definition("alerts_alert_type_check", "alert_type", "alerts_alert_type_check")
    assert path == latest_touching, f"{latest_touching.name} touches alerts_alert_type_check but the parser read {path.name}"


def test_severity_constraint_is_never_redefined_after_0174():
    """If a migration ever widens severity, this fails so the parser/test get updated deliberately."""
    redefining = [p.name for p in MIGRATIONS.glob("*.sql") if "alerts_severity_check" in p.read_text(encoding="utf-8")]
    assert redefining == [], f"severity CHECK redefined in {redefining}: extend _latest_definition for it"


def test_defaults_are_inside_their_sets():
    assert alert_schema.DEFAULT_ALERT_TYPE in alert_schema.ALLOWED_ALERT_TYPE
    assert alert_schema.DEFAULT_SEVERITY in alert_schema.ALLOWED_SEVERITY
