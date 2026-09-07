"""
Unit tests for intelligence/ingestion/firecrawl_client.py's automatic
failover from the primary Firecrawl account to a second account
(FIRECRAWL_API_KEY_2) once the primary's safe ceiling is reached.

All against a mocked external_fetch_budget.check_and_increment — no live
Supabase or real Firecrawl call required.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.ingestion import firecrawl_client
from intelligence.ingestion import external_fetch_budget


class AcquireAccountTests(unittest.TestCase):
    def test_uses_primary_account_when_under_ceiling(self):
        with mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY", "key1"), \
             mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY_2", "key2"), \
             mock.patch.object(external_fetch_budget, "check_and_increment", return_value=1) as inc:
            api_key, provider = firecrawl_client._acquire_account()

        self.assertEqual((api_key, provider), ("key1", "firecrawl"))
        inc.assert_called_once_with("firecrawl")

    def test_fails_over_to_second_account_when_primary_exceeded(self):
        def fake_increment(provider, **kwargs):
            if provider == "firecrawl":
                raise external_fetch_budget.FetchBudgetExceeded("firecrawl at ceiling")
            return 1

        with mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY", "key1"), \
             mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY_2", "key2"), \
             mock.patch.object(external_fetch_budget, "check_and_increment", side_effect=fake_increment) as inc:
            api_key, provider = firecrawl_client._acquire_account()

        self.assertEqual((api_key, provider), ("key2", "firecrawl_2"))
        self.assertEqual(
            inc.call_args_list,
            [mock.call("firecrawl"), mock.call("firecrawl_2")],
        )

    def test_primary_exceeded_and_no_second_key_raises(self):
        with mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY", "key1"), \
             mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY_2", ""), \
             mock.patch.object(
                 external_fetch_budget, "check_and_increment",
                 side_effect=external_fetch_budget.FetchBudgetExceeded("firecrawl at ceiling"),
             ):
            with self.assertRaises(external_fetch_budget.FetchBudgetExceeded):
                firecrawl_client._acquire_account()

    def test_check_failed_does_not_fail_over(self):
        """An ambiguous check failure (Supabase unreachable, etc.) must
        propagate rather than trigger a fallback to the second account —
        fail-safe, not fail-open."""
        with mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY", "key1"), \
             mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY_2", "key2"), \
             mock.patch.object(
                 external_fetch_budget, "check_and_increment",
                 side_effect=external_fetch_budget.FetchBudgetCheckFailed("supabase unreachable"),
             ) as inc:
            with self.assertRaises(external_fetch_budget.FetchBudgetCheckFailed):
                firecrawl_client._acquire_account()

        inc.assert_called_once_with("firecrawl")

    def test_only_second_key_configured_goes_straight_to_it(self):
        with mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY", ""), \
             mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY_2", "key2"), \
             mock.patch.object(external_fetch_budget, "check_and_increment", return_value=1) as inc:
            api_key, provider = firecrawl_client._acquire_account()

        self.assertEqual((api_key, provider), ("key2", "firecrawl_2"))
        inc.assert_called_once_with("firecrawl_2")

    def test_neither_key_configured_raises_not_configured(self):
        with mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY", ""), \
             mock.patch.object(firecrawl_client, "FIRECRAWL_API_KEY_2", ""):
            with self.assertRaises(firecrawl_client.FirecrawlNotConfigured):
                firecrawl_client._acquire_account()


if __name__ == "__main__":
    unittest.main()
