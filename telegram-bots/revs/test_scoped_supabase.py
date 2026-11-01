#!/usr/bin/env python3
"""Tests for scoped_supabase.py — REVS bot's scoped-role Supabase client
construction, including the 2026-09-14 supabase-py 2.3.4 -> 2.31.0
mechanism change (private `_auth_token` attribute -> public
`ClientOptions(headers=...)`).

Run from repo root:
    python -m pytest telegram-bots/revs/test_scoped_supabase.py -v

No live Supabase project required — create_client itself is mocked, and
jwt.encode runs against a fake secret only to prove a real, well-formed
token is minted and threaded through correctly.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

import scoped_supabase


class TestResolveScopedAuth:
    def test_mints_token_from_jwt_secret(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", "a-test-secret-that-is-long-enough")
        monkeypatch.delenv("REVS_BOT_SCOPED_TOKEN", raising=False)
        token = scoped_supabase.resolve_scoped_auth()
        assert token is not None
        # A real, well-formed JWT — three dot-separated base64url segments.
        assert token.count(".") == 2

    def test_falls_back_to_preminted_token_when_no_secret(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
        monkeypatch.setenv("REVS_BOT_SCOPED_TOKEN", "pre-minted-token-value")
        assert scoped_supabase.resolve_scoped_auth() == "pre-minted-token-value"

    def test_returns_none_when_neither_configured(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
        monkeypatch.delenv("REVS_BOT_SCOPED_TOKEN", raising=False)
        assert scoped_supabase.resolve_scoped_auth() is None

    def test_secret_takes_priority_over_preminted(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", "a-test-secret-that-is-long-enough")
        monkeypatch.setenv("REVS_BOT_SCOPED_TOKEN", "should-not-be-used")
        token = scoped_supabase.resolve_scoped_auth()
        assert token != "should-not-be-used"


class TestBuildScopedClient:
    def test_returns_none_without_anon_key(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
        monkeypatch.setenv("SUPABASE_JWT_SECRET", "a-test-secret-that-is-long-enough")
        assert scoped_supabase.build_scoped_client("https://example.supabase.co") is None

    def test_returns_none_without_scoped_token(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
        monkeypatch.delenv("REVS_BOT_SCOPED_TOKEN", raising=False)
        assert scoped_supabase.build_scoped_client("https://example.supabase.co") is None

    def test_constructs_client_via_client_options_headers_not_private_attribute(self, monkeypatch):
        """The core regression this test guards: build_scoped_client() must
        use the public ClientOptions(headers={...}) mechanism (the only one
        that still works on supabase-py >=2.5.0), never the dead private
        `_auth_token` attribute patch — which silently no-ops on current
        supabase-py and would run this public-facing bot unscoped without
        raising anything."""
        monkeypatch.setenv("SUPABASE_ANON_KEY", "the-anon-key")
        monkeypatch.setenv("REVS_BOT_SCOPED_TOKEN", "the-scoped-token")

        fake_client = MagicMock()
        fake_client.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock()

        with patch("supabase.create_client", return_value=fake_client) as mock_create, \
             patch("supabase.ClientOptions") as mock_options_cls:
            mock_options_cls.return_value = "OPTIONS_SENTINEL"
            result = scoped_supabase.build_scoped_client("https://example.supabase.co")

        assert result is fake_client
        # ClientOptions was built with exactly the scoped bearer token —
        # never derived from the anon key.
        mock_options_cls.assert_called_once_with(headers={"Authorization": "Bearer the-scoped-token"})
        # create_client received the anon key as the apikey argument and
        # the ClientOptions instance as `options` — never a plain
        # create_client(url, anon_key) followed by attribute mutation.
        mock_create.assert_called_once_with(
            "https://example.supabase.co", "the-anon-key", options="OPTIONS_SENTINEL",
        )

    def test_returns_none_when_live_verification_query_fails(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_ANON_KEY", "the-anon-key")
        monkeypatch.setenv("REVS_BOT_SCOPED_TOKEN", "the-scoped-token")

        fake_client = MagicMock()
        fake_client.table.return_value.select.return_value.limit.return_value.execute.side_effect = RuntimeError("PGRST301")

        with patch("supabase.create_client", return_value=fake_client), \
             patch("supabase.ClientOptions"):
            result = scoped_supabase.build_scoped_client("https://example.supabase.co")

        assert result is None

    def test_verification_query_targets_revs_users(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_ANON_KEY", "the-anon-key")
        monkeypatch.setenv("REVS_BOT_SCOPED_TOKEN", "the-scoped-token")

        fake_client = MagicMock()
        with patch("supabase.create_client", return_value=fake_client), \
             patch("supabase.ClientOptions"):
            scoped_supabase.build_scoped_client("https://example.supabase.co")

        fake_client.table.assert_called_once_with("revs_users")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
