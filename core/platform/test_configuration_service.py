"""Tests for core/platform/configuration_service.py — had zero coverage
before 2026-08-29's config-loader consolidation (see
tools/check_config_loaders.py and the notification-sender consolidation
this mirrors)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from core.platform.configuration_service import (
    get_shared_config,
    load_dotenv_files,
    validate_shared_config,
)


def test_missing_file_is_skipped_not_raised(tmp_path):
    load_dotenv_files([tmp_path / "does-not-exist.env"])  # must not raise


def test_first_file_wins_by_default(tmp_path):
    f1 = tmp_path / "a.env"
    f1.write_text("KEY=first\n")
    f2 = tmp_path / "b.env"
    f2.write_text("KEY=second\n")
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KEY", None)
        load_dotenv_files([f1, f2])
        assert os.environ["KEY"] == "first"
        del os.environ["KEY"]


def test_existing_env_var_not_overridden_by_default(tmp_path):
    f = tmp_path / "a.env"
    f.write_text("KEY=fromfile\n")
    with patch.dict(os.environ, {"KEY": "preexisting"}):
        load_dotenv_files([f])
        assert os.environ["KEY"] == "preexisting"


def test_override_true_replaces_existing(tmp_path):
    f = tmp_path / "a.env"
    f.write_text("KEY=fromfile\n")
    with patch.dict(os.environ, {"KEY": "preexisting"}):
        load_dotenv_files([f], override=True)
        assert os.environ["KEY"] == "fromfile"


def test_comments_and_blank_lines_skipped(tmp_path):
    f = tmp_path / "a.env"
    f.write_text("# comment\n\nKEY=value\n")
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KEY", None)
        load_dotenv_files([f])
        assert os.environ["KEY"] == "value"
        del os.environ["KEY"]


def test_quoted_values_stripped(tmp_path):
    f = tmp_path / "a.env"
    f.write_text('KEY="quoted value"\n')
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KEY", None)
        load_dotenv_files([f])
        assert os.environ["KEY"] == "quoted value"
        del os.environ["KEY"]


def test_get_shared_config_reads_env():
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://x.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "secret",
        "GEMINI_API_KEY": "gkey",
    }):
        cfg = get_shared_config()
        assert cfg.supabase_url == "https://x.supabase.co"
        assert cfg.supabase_service_role_key == "secret"
        assert cfg.supabase_enabled is True


def test_get_shared_config_falls_back_to_supabase_key_alias():
    with patch.dict(os.environ, {"SUPABASE_URL": "u", "SUPABASE_KEY": "alias-key"}, clear=False):
        os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
        cfg = get_shared_config()
        assert cfg.supabase_service_role_key == "alias-key"


def test_validate_shared_config_reports_missing():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
        os.environ.pop("SUPABASE_KEY", None)
        missing = validate_shared_config()
        assert "SUPABASE_URL" in missing
        assert "SUPABASE_SERVICE_ROLE_KEY" in missing
