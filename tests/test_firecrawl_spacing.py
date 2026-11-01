"""Unit tests for Firecrawl call spacing and the one-shot 429 retry."""

import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.ingestion import external_fetch_budget, firecrawl_client


def _http_429(retry_after=3):
    body = json.dumps({"success": False, "retry_after_seconds": retry_after}).encode()
    return urllib.error.HTTPError("u", 429, "Too Many Requests", {}, io.BytesIO(body))


class _Resp:
    def __init__(self, payload):
        self._p = json.dumps(payload).encode()

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


OK = {"success": True, "data": {"rawHtml": "<html/>", "metadata": {"statusCode": 200}}}


class SpacingTests(unittest.TestCase):
    def setUp(self):
        firecrawl_client._last_call_at["firecrawl"] = 0.0

    def test_second_call_waits_for_gap(self):
        with mock.patch.object(firecrawl_client.time, "sleep") as sleep, \
             mock.patch.object(firecrawl_client.time, "monotonic", side_effect=[100.0, 100.0, 101.0, 101.0]):
            firecrawl_client._wait_for_spacing("firecrawl")
            firecrawl_client._wait_for_spacing("firecrawl")
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args[0][0], firecrawl_client._MIN_CALL_GAP_SECONDS - 1.0)

    def test_429_retries_once_and_succeeds(self):
        calls = [_http_429(3), _Resp(OK)]

        def fake_open(*a, **k):
            r = calls.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY", "k"), \
             mock.patch.object(external_fetch_budget, "check_and_increment", return_value=1) as inc, \
             mock.patch.object(firecrawl_client, "_wait_for_spacing"), \
             mock.patch.object(firecrawl_client.time, "sleep") as sleep, \
             mock.patch.object(firecrawl_client.urllib.request, "urlopen", side_effect=fake_open):
            data = firecrawl_client.scrape("https://example.com")
        self.assertEqual(data["rawHtml"], "<html/>")
        sleep.assert_called_once_with(4.0)
        inc.assert_called_once_with("firecrawl")  # retry must not spend a second budget unit

    def test_second_429_raises(self):
        with mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY", "k"), \
             mock.patch.object(external_fetch_budget, "check_and_increment", return_value=1), \
             mock.patch.object(firecrawl_client, "_wait_for_spacing"), \
             mock.patch.object(firecrawl_client.time, "sleep"), \
             mock.patch.object(firecrawl_client.urllib.request, "urlopen", side_effect=[_http_429(1), _http_429(1)]):
            with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
                firecrawl_client.scrape("https://example.com")


if __name__ == "__main__":
    unittest.main()
