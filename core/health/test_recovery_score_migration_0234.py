"""Runs core/infrastructure/supabase/tests/0234_recovery_score_pain_state.test.sql
against a THROWAWAY Postgres database (name must contain "test"; the SQL
refuses to run otherwise). Skipped unless TEST_DATABASE_URL is set, because the
repo's CI has no Postgres service. Example:

    createdb recovery_test
    TEST_DATABASE_URL=postgresql:///recovery_test pytest core/health/test_recovery_score_migration_0234.py
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL = "core/infrastructure/supabase/tests/0234_recovery_score_pain_state.test.sql"
DSN = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DSN or not shutil.which("psql"),
    reason="needs TEST_DATABASE_URL (throwaway db with 'test' in its name) and psql",
)


def test_recovery_score_pain_state_migration_and_rollback():
    result = subprocess.run(
        ["psql", DSN, "-v", "ON_ERROR_STOP=1", "-q", "-f", SQL],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "OK: 0234 recovery score tests passed" in result.stdout
