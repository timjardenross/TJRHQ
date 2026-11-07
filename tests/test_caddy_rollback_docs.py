"""SEC-01: documentation and guard tests for the Caddy rollback procedure.

All script runs use temporary fixtures and a stub `caddy` binary. The live
/etc/caddy file is never read or written, and no real reload happens.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DEPLOY = REPO / "deploy" / "caddy"
README = DEPLOY / "README-v3.md"
ROLLBACK = DEPLOY / "rollback_v2.sh"
BACKUP = DEPLOY / "backup_known_good.sh"
CHECKLIST = DEPLOY / "G5-CHECKLIST.md"
V2_SHA = "1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stub_caddy(tmp: Path) -> Path:
    """A fake `caddy` that records its argv and exits 0. Never a real Caddy."""
    log = tmp / "caddy-calls.log"
    stub = tmp / "caddy"
    stub.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit 0\n')
    stub.chmod(0o755)
    return stub


def _env(tmp: Path, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CADDY_") and k != "V3_SHA"}
    env.update({"CADDY_BIN": str(_stub_caddy(tmp)), "CADDY_LIVE": str(tmp / "live"),
                "CADDY_V2_SHA": _sha(tmp / "backup"), "CADDY_BACKUP": str(tmp / "backup"),
                "V3_SHA": _sha(tmp / "live"), "DEST_DIR": str(tmp / "dest")})
    env.update(extra)
    return env


@pytest.fixture()
def fixture_files(tmp_path):
    (tmp_path / "live").write_text("live v3 content\n")
    (tmp_path / "backup").write_text("redacted v2 content\n")
    return tmp_path


# --- README content -----------------------------------------------------------

def test_readme_names_the_expected_v2_hash():
    assert V2_SHA in README.read_text()


def test_readme_forbids_the_pre_redaction_backup_source():
    text = README.read_text()
    assert "Caddyfile.bak.pre-sec01" in text
    assert "pre-redaction" in text.lower()


def test_readme_requires_backup_hash_verification_and_validate_before_reload():
    text = README.read_text()
    assert "backup_known_good.sh" in text
    assert "sha256sum /root/.sec01-caddy-rollback" in text
    assert "caddy validate" in text
    assert "caddy reload" in text
    rollback = text[text.index("## Rollback (production)"):text.index("## Deployment gate")]
    assert rollback.index("caddy validate --config /etc/caddy/Caddyfile") < rollback.index(
        "caddy reload --config /etc/caddy/Caddyfile --force")


def test_readme_documents_drift_without_overwrite():
    text = README.read_text()
    assert "### Drift" in text
    assert "nothing has been overwritten" in text.lower()


def test_checklist_carries_the_rollback_prerequisites():
    text = CHECKLIST.read_text()
    assert V2_SHA in text
    assert "rollback_v2.sh" in text
    assert "Caddyfile.bak.pre-sec01" in text


# --- scripts ---------------------------------------------------------------------

@pytest.mark.parametrize("script", [ROLLBACK, BACKUP])
def test_scripts_are_executable_and_parse(script):
    assert script.stat().st_mode & stat.S_IXUSR
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True, check=False).returncode == 0


def test_rollback_refuses_pre_redaction_backup(fixture_files):
    bad = fixture_files / "Caddyfile.bak.pre-sec01-x"
    bad.write_text("pre-redaction\n")
    env = _env(fixture_files, CADDY_BACKUP=str(bad))
    r = subprocess.run(["bash", str(ROLLBACK)], env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 2 and "predates log redaction" in r.stdout


def test_rollback_refuses_wrong_backup_hash(fixture_files):
    env = _env(fixture_files, CADDY_V2_SHA="0" * 64)
    r = subprocess.run(["bash", str(ROLLBACK)], env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 3 and "REFUSED" in r.stdout


def test_rollback_stops_on_drift_without_overwriting(fixture_files):
    before = (fixture_files / "live").read_bytes()
    env = _env(fixture_files, V3_SHA="0" * 64)
    r = subprocess.run(["bash", str(ROLLBACK), "--apply"], env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 4 and "drifted" in r.stdout
    assert (fixture_files / "live").read_bytes() == before


def test_rollback_dry_run_changes_nothing(fixture_files):
    before = (fixture_files / "live").read_bytes()
    r = subprocess.run(
        ["bash", str(ROLLBACK)], env=_env(fixture_files), capture_output=True, text=True, check=False
    )
    assert r.returncode == 0 and "dry-run" in r.stdout
    assert (fixture_files / "live").read_bytes() == before


def test_rollback_apply_restores_validates_and_never_reloads(fixture_files):
    env = _env(fixture_files)
    r = subprocess.run(["bash", str(ROLLBACK), "--apply"], env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (fixture_files / "live").read_text() == "redacted v2 content\n"
    calls = (fixture_files / "caddy-calls.log").read_text()
    assert "validate" in calls and "reload" not in calls


def test_backup_helper_refuses_unless_live_is_redacted_v2(fixture_files):
    env = _env(fixture_files)  # live != V2_SHA constant (fixture is not the real file)
    env.pop("CADDY_V2_SHA")
    env["CADDY_LIVE"] = str(fixture_files / "live")
    r = subprocess.run(["bash", str(BACKUP), "--apply"], env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 3 and "REFUSED" in r.stdout
    assert not (fixture_files / "dest").exists()


def test_backup_helper_writes_0600_copy_in_0700_dir(fixture_files):
    live = fixture_files / "live"
    env = _env(fixture_files, CADDY_LIVE=str(live), CADDY_V2_SHA=_sha(live))
    r = subprocess.run(["bash", str(BACKUP), "--apply"], env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    dest = fixture_files / "dest" / f"Caddyfile.v2-redacted-{_sha(live)[:8]}"
    assert dest.read_bytes() == live.read_bytes()
    assert stat.S_IMODE(dest.stat().st_mode) == 0o600
    assert stat.S_IMODE((fixture_files / "dest").stat().st_mode) == 0o700
