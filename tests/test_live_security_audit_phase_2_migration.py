"""Contract checks for migration 0260's no-semantic-change hardening."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "core"
    / "infrastructure"
    / "supabase"
    / "migrations"
    / "0260_live_security_audit_phase_2.sql"
)


def _sql() -> str:
    return MIGRATION.read_text().lower()


def test_all_audited_foreign_keys_receive_covering_indexes() -> None:
    sql = _sql()
    assert sql.count("create index if not exists") == 18
    for column in (
        "mission_id",
        "event_id",
        "signal_id",
        "memory_document_id",
        "specialist_id",
    ):
        assert f"({column})" in sql


def test_duplicate_index_is_removed_without_dropping_constraint_index() -> None:
    sql = _sql()
    assert "drop index if exists public.downdetector_learned_thresholds_source_idx" in sql
    assert "drop index if exists public.downdetector_learned_thresholds_source_name_key" not in sql


def test_auth_uid_calls_use_initplans() -> None:
    executable_sql = "\n".join(
        line for line in _sql().splitlines() if not line.lstrip().startswith("--")
    )
    assert "auth.uid()" in executable_sql
    assert "(select auth.uid())" in executable_sql
    assert "= auth.uid()" not in executable_sql
    assert "auth.uid() =" not in executable_sql


def test_only_redundant_policies_are_removed() -> None:
    sql = _sql()
    assert sql.count("drop policy if exists pain_recovery_owner_all") == 5
    for policy in (
        "auth_read on public.captains_log_entries",
        "decide_ledger_auth_read on public.decide_ledger",
        "auth_read on public.health_daily_logs",
        "home_sessions_auth_read on public.home_sessions",
    ):
        assert f"drop policy if exists {policy}" in sql
