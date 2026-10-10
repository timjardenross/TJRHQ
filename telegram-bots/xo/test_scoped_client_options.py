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
