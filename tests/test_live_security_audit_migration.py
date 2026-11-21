"""Contract checks for migration 0259's least-privilege hardening."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "core"
    / "infrastructure"
    / "supabase"
    / "migrations"
    / "0259_live_security_audit_hardening.sql"
)


def _sql() -> str:
    return MIGRATION.read_text().lower()


def test_mutable_search_paths_are_pinned() -> None:
    sql = _sql()
    for signature in (
        "match_research_memories_mistral(public.vector, double precision, integer)",
        "count_uncorroborated_events(timestamptz)",
        "bulk_update_signal_scores(jsonb)",
        "current_officer_clearance()",
    ):
        statement = f"alter function public.{signature}"
        start = sql.index(statement)
        assert "set search_path = pg_catalog, public" in sql[start : start + 240]


def test_privileged_functions_do_not_grant_anon_execute() -> None:
    sql = _sql()
    assert "grant execute" in sql
    assert "grant execute on function" in sql
    assert "to anon" not in sql


def test_policies_use_explicit_roles_not_auth_role() -> None:
    sql = _sql()
    executable_sql = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    assert "auth.role()" not in executable_sql
    assert "to service_role using (true) with check (true)" in executable_sql
    assert "to authenticated using (true)" in executable_sql


def test_no_policy_tables_are_removed_from_anon() -> None:
    sql = _sql()
    assert "revoke all on table" in sql
    assert "public.google_calendar_tokens" in sql
    assert "public.working_memory" in sql
    assert sql.rstrip().endswith("from anon;")
