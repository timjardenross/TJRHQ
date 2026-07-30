"""Tests for core/health/supabase_client.py — WP-3.

Tests the public API shape and error handling without making real network calls.
Uses unittest.mock to intercept urllib requests.

Run: python3 -m pytest core/health/test_supabase_client.py -v
  or: python3 core/health/test_supabase_client.py
"""

from __future__ import annotations
import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _mock_response(data: dict | list, status: int = 200):
    """Return a mock urllib response object."""
    body = json.dumps(data).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(code: int, body: str = "error"):
    exc = urllib.error.HTTPError(
        url="http://test", code=code, msg="Error",
        hdrs=None, fp=io.BytesIO(body.encode()),
    )
    return exc


class TestSupabaseClientPublicAPI(unittest.TestCase):
    """is_configured, supabase_get, supabase_upsert, supabase_insert must all be importable."""

    def test_public_api_importable(self):
        import supabase_client as sc
        self.assertTrue(callable(sc.supabase_get))
        self.assertTrue(callable(sc.supabase_upsert))
        self.assertTrue(callable(sc.supabase_insert))
        self.assertTrue(callable(sc.is_configured))

    def test_is_configured_false_when_env_not_set(self):
        """When credentials are absent, is_configured returns False."""
        import supabase_client as sc
        with patch.object(sc, "_URL", ""), patch.object(sc, "_KEY", ""):
            self.assertFalse(sc.is_configured())

    def test_is_configured_true_when_env_set(self):
        import supabase_client as sc
        with patch.object(sc, "_URL", "https://test.supabase.co"), patch.object(sc, "_KEY", "secret"):
            self.assertTrue(sc.is_configured())


class TestSupabaseGet(unittest.TestCase):

    def setUp(self):
        import supabase_client as sc
        self.sc = sc
        self._url_patch = patch.object(sc, "_URL", "https://test.supabase.co")
        self._key_patch = patch.object(sc, "_KEY", "test_key")
        self._url_patch.start()
        self._key_patch.start()

    def tearDown(self):
        self._url_patch.stop()
        self._key_patch.stop()

    def test_get_returns_list(self):
        rows = [{"id": "abc", "log_date": "2026-06-13"}]
        with patch("urllib.request.urlopen", return_value=_mock_response(rows)):
            result = self.sc.supabase_get("health_daily_logs")
        self.assertEqual(result, rows)

    def test_get_wraps_dict_in_list(self):
        """PostgREST sometimes returns a single dict — wrap it."""
        with patch("urllib.request.urlopen", return_value=_mock_response({"id": "x"})):
            result = self.sc.supabase_get("health_daily_logs")
        self.assertIsInstance(result, list)

    def test_get_raises_runtime_on_http_error(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(403)):
            with self.assertRaises(RuntimeError) as ctx:
                self.sc.supabase_get("health_daily_logs")
        self.assertIn("403", str(ctx.exception))

    def test_get_raises_when_unconfigured(self):
        with patch.object(self.sc, "_URL", ""):
            with self.assertRaises(RuntimeError):
                self.sc.supabase_get("health_daily_logs")


class TestSupabaseUpsert(unittest.TestCase):

    def setUp(self):
        import supabase_client as sc
        self.sc = sc
        self._url_patch = patch.object(sc, "_URL", "https://test.supabase.co")
        self._key_patch = patch.object(sc, "_KEY", "test_key")
        self._url_patch.start()
        self._key_patch.start()

    def tearDown(self):
        self._url_patch.stop()
        self._key_patch.stop()

    def test_upsert_returns_row(self):
        saved = {"id": "row-1", "log_date": "2026-06-13"}
        with patch("urllib.request.urlopen", return_value=_mock_response([saved])):
            result = self.sc.supabase_upsert("health_daily_logs", {"log_date": "2026-06-13"}, on_conflict="log_date")
        self.assertEqual(result, saved)

    def test_upsert_raises_on_http_error(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(409, "conflict")):
            with self.assertRaises(RuntimeError):
                self.sc.supabase_upsert("health_daily_logs", {}, on_conflict="log_date")

    def test_upsert_includes_on_conflict_in_url(self):
        """Verify on_conflict is sent as a URL query parameter (PostgREST v10+)."""
        saved = {"id": "row-1"}
        captured = {}

        def fake_urlopen(req, timeout=10):
            captured["url"] = req.full_url
            captured["prefer"] = req.get_header("Prefer")
            return _mock_response([saved])

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self.sc.supabase_upsert("health_daily_logs", {"log_date": "2026-06-13"}, on_conflict="log_date")

        self.assertIn("on_conflict=log_date", captured["url"])
        self.assertIn("merge-duplicates", captured["prefer"])
        self.assertNotIn("on_conflict", captured["prefer"])  # not in Prefer header


class TestSupabaseInsert(unittest.TestCase):
    """WP-3: supabase_insert is a plain INSERT (no conflict handling)."""

    def setUp(self):
        import supabase_client as sc
        self.sc = sc
        self._url_patch = patch.object(sc, "_URL", "https://test.supabase.co")
        self._key_patch = patch.object(sc, "_KEY", "test_key")
        self._url_patch.start()
        self._key_patch.start()

    def tearDown(self):
        self._url_patch.stop()
        self._key_patch.stop()

    def test_insert_returns_row(self):
        saved = {"id": "evt-1", "event_type": "appointment"}
        with patch("urllib.request.urlopen", return_value=_mock_response([saved])):
            result = self.sc.supabase_insert("health_events", {"event_type": "appointment"})
        self.assertEqual(result, saved)

    def test_insert_prefer_return_representation(self):
        """insert should NOT include merge-duplicates — it's a plain insert."""
        captured = {}

        def fake_urlopen(req, timeout=10):
            captured["prefer"] = req.get_header("Prefer")
            return _mock_response([{"id": "x"}])

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self.sc.supabase_insert("health_events", {"event_type": "appointment"})

        self.assertIn("return=representation", captured["prefer"])
        self.assertNotIn("merge-duplicates", captured["prefer"])

    def test_insert_raises_on_http_error(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(400, "bad request")):
            with self.assertRaises(RuntimeError):
                self.sc.supabase_insert("health_events", {})

    def test_insert_raises_when_unconfigured(self):
        with patch.object(self.sc, "_URL", ""):
            with self.assertRaises(RuntimeError):
                self.sc.supabase_insert("health_events", {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
