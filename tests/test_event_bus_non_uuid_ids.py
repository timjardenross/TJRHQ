"""event_bus must not send UPDATEs for ids that can never be a core_events uuid.

core/platform/attention_drill.py builds an in-memory event with a synthetic
`drill-<hex>` id and never writes it to core_events, but the dispatcher still
called mark_event_status() / record_dispatch_message_id() on it — a PATCH that
always failed the uuid cast (400) and recorded a failed event-bus heartbeat.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from core.platform import event_bus

DRILL_ID = "drill-f6fc82f9e815"


def _patched_client():
    client_cls = MagicMock()
    return client_cls, patch("tools.supabase.client.CommanderSupabaseClient", client_cls)


def test_mark_event_status_skips_a_drill_id_without_any_request():
    client_cls, patcher = _patched_client()
    with patcher, patch.object(event_bus, "_record_bus_heartbeat") as heartbeat:
        assert event_bus.mark_event_status(DRILL_ID, "acknowledged") is False
    client_cls.assert_not_called()
    heartbeat.assert_not_called()  # a drill must not register as an event-bus failure


def test_record_dispatch_message_id_skips_a_drill_id_without_any_request():
    client_cls, patcher = _patched_client()
    with patcher:
        assert event_bus.record_dispatch_message_id(DRILL_ID, 123) is False
    client_cls.assert_not_called()


def test_a_real_event_id_still_updates_core_events():
    event_id = str(uuid.uuid4())
    client_cls, patcher = _patched_client()
    with patcher, patch.object(event_bus, "_record_bus_heartbeat"):
        assert event_bus.mark_event_status(event_id, "acknowledged") is True
        assert event_bus.record_dispatch_message_id(event_id, 7) is True
    table = client_cls.return_value.raw_client.table
    assert [c.args for c in table.call_args_list] == [("core_events",), ("core_events",)]
    updates = table.return_value.update
    assert [c.args[0] for c in updates.call_args_list] == [{"status": "acknowledged"}, {"dispatch_message_id": 7}]
    assert all(c.args == ("event_id", event_id) for c in updates.return_value.eq.call_args_list)


def test_invalid_status_is_still_rejected_first():
    client_cls, patcher = _patched_client()
    with patcher:
        assert event_bus.mark_event_status(str(uuid.uuid4()), "bogus") is False
    client_cls.assert_not_called()
