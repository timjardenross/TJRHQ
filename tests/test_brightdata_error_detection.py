"""
Unit tests for intelligence/ingestion/brightdata_fetch.py's detection of
Bright Data's OWN refusal responses (x-brd-error* headers on an HTTP 200)
— confirmed live 2026-09-06 against downdetector.com.au, where Bright
Data's "residential, no-KYC" access tier refuses the target site per its
robots.txt and returns a 200 with a short error-message body in place of
the real page. Before this fix, that error text was silently handed back
as if it were real HTML, which then failed to parse downstream and was
misreported as "page shape may have changed" — masking the real cause.

All against a mocked urllib.request.urlopen and a mocked
external_fetch_budget.check_and_increment — no live Bright Data account
or Supabase required.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.ingestion import brightdata_fetch


def _fake_response(headers: dict, body: bytes):
    resp = mock.MagicMock()
    resp.headers = mock.MagicMock()
    resp.headers.get = lambda key, default=None: headers.get(key, default)
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


class FetchHtmlErrorDetectionTests(unittest.TestCase):
    def _patched(self, response):
        return (
            mock.patch.object(brightdata_fetch, "BRIGHTDATA_API_KEY", "test-key"),
            mock.patch.object(brightdata_fetch.external_fetch_budget, "check_and_increment", return_value=1),
            mock.patch("urllib.request.urlopen", return_value=response),
        )

    def test_raises_clear_error_on_kyc_policy_refusal(self):
        """The exact live shape seen from Bright Data for downdetector.com.au."""
        response = _fake_response(
            headers={
                "x-brd-error-code": "policy_20140",
                "x-brd-error": (
                    "Residential Failed (bad_endpoint): Requested site is not "
                    "available for immediate residential (no KYC) access mode "
                    "in accordance with robots.txt. To get full residential "
                    "access for targeting this site, fill in the KYC form: "
                    "https://brightdata.com/cp/kyc"
                ),
            },
            body=b"Residential Failed (bad_endpoint)...",
        )
        p1, p2, p3 = self._patched(response)
        with p1, p2, p3:
            with self.assertRaises(RuntimeError) as ctx:
                brightdata_fetch.fetch_html("https://downdetector.com.au/status/national-australia-bank/")

        self.assertIn("policy_20140", str(ctx.exception))
        self.assertIn("KYC", str(ctx.exception))

    def test_raises_clear_error_on_ip_not_whitelisted(self):
        """A different Bright Data refusal reason, different header names
        (x-brd-err-code / x-brd-err-msg instead of x-brd-error-code /
        x-brd-error) — both must be detected."""
        response = _fake_response(
            headers={
                "x-brd-err-code": "client_10030",
                "x-brd-err-msg": "The IP address from which you are sending this request is not whitelisted",
                "x-brd-error": "Auth Failed (code: ip_forbidden)",
            },
            body=b"",
        )
        p1, p2, p3 = self._patched(response)
        with p1, p2, p3:
            with self.assertRaises(RuntimeError) as ctx:
                brightdata_fetch.fetch_html("https://downdetector.com.au/status/national-australia-bank/")

        self.assertIn("Auth Failed", str(ctx.exception))

    def test_real_page_content_still_returned_normally(self):
        """No Bright Data error headers present -> real content flows through
        exactly as before this fix."""
        response = _fake_response(headers={}, body=b"<html>real page</html>")
        p1, p2, p3 = self._patched(response)
        with p1, p2, p3:
            html = brightdata_fetch.fetch_html("https://downdetector.com.au/status/national-australia-bank/")

        self.assertEqual(html, "<html>real page</html>")


if __name__ == "__main__":
    unittest.main()
