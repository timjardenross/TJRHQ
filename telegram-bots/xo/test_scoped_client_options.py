"""USS-TJR-MSN-0412: scoped_supabase must pick the ClientOptions class the installed supabase-py expects.

supabase-py 2.32.0's sync client reads `client_options.storage`, which only SyncClientOptions has; older
releases (2.7.4 and below) only have ClientOptions. Faked modules, no network, no supabase-py needed.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

scoped = pytest.importorskip("telegram_bots.xo.scoped_supabase")


def _fake_client_options(monkeypatch, *, with_sync: bool):
    class ClientOptions:  # base class: no `storage` field
        pass

    mod = types.ModuleType("supabase.lib.client_options")
    mod.ClientOptions = ClientOptions
    if with_sync:
        class SyncClientOptions(ClientOptions):
            storage = object()

        mod.SyncClientOptions = SyncClientOptions
    lib = types.ModuleType("supabase.lib")
    lib.client_options = mod
    monkeypatch.setitem(sys.modules, "supabase", types.ModuleType("supabase"))
    monkeypatch.setitem(sys.modules, "supabase.lib", lib)
    monkeypatch.setitem(sys.modules, "supabase.lib.client_options", mod)
    return mod


def test_prefers_sync_client_options_when_present(monkeypatch):
    mod = _fake_client_options(monkeypatch, with_sync=True)
    assert scoped._client_options_class() is mod.SyncClientOptions


def test_falls_back_to_client_options_on_old_supabase_py(monkeypatch):
    mod = _fake_client_options(monkeypatch, with_sync=False)
    assert scoped._client_options_class() is mod.ClientOptions


def test_gateway_key_falls_back_to_legacy_anon_key(monkeypatch):
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "legacy")
    assert scoped._gateway_api_key() == "legacy"


def test_scoped_client_prefers_publishable_gateway_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "replacement")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "legacy")
    monkeypatch.setattr(scoped, "resolve_scoped_auth", lambda: "scoped-token")

    class Options:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Query:
        def select(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def execute(self):
            return None

    seen = {}
    fake_supabase = types.ModuleType("supabase")

    def create_client(url, key, options):
        seen.update(url=url, key=key, options=options)
        return types.SimpleNamespace(table=lambda _name: Query())

    fake_supabase.create_client = create_client
    monkeypatch.setitem(sys.modules, "supabase", fake_supabase)
    monkeypatch.setattr(scoped, "_client_options_class", lambda: Options)

    assert scoped.build_scoped_client("https://example.supabase.co") is not None
    assert seen["key"] == "replacement"
