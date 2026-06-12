import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "supabase"))

import client  # noqa: E402


class SupabaseClientTest(unittest.TestCase):
    def test_disabled_mode_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(client.is_supabase_enabled())
            result = client.log_commander_event({"message_text": "test"})

        self.assertFalse(result.ok)
        self.assertFalse(result.enabled)
        self.assertEqual(result.error, "supabase_disabled")

    def test_log_payload_uses_configured_table(self):
        with patch.object(client.CommanderSupabaseClient, "insert") as insert:
            insert.return_value = client.SupabaseWriteResult(ok=True, enabled=True, table="commander_events")
            result = client.log_commander_event({"message_text": "test"})

        self.assertTrue(result.ok)
        insert.assert_called_once_with("commander_events", {"message_text": "test"})

    def test_raw_client_property_exposes_supabase_client(self):
        fake_raw_client = object()
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
        }, clear=True), patch("supabase.create_client", return_value=fake_raw_client):
            supabase_client = client.CommanderSupabaseClient()

        self.assertIs(supabase_client.raw_client, fake_raw_client)


if __name__ == "__main__":
    unittest.main()
