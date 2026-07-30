"""
Unit tests for intelligence/classification/source_tier.py (Phase A Stage 3).

Covers:
- Tier 1–4 classification of representative AU OR-intelligence domains
- Subdomain suffix matching (news.abc.net.au -> abc.net.au)
- www. stripping, port/creds stripping, bare-domain input
- Conservative default: unknown / empty / malformed -> Tier 4 (never false Tier 1)
- Speed budget (<10ms/source)
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.classification.source_tier import (
    DEFAULT_TIER,
    SourceTierClassifier,
    classify_source_tier,
    extract_domain,
    tier_label,
)


class TestSourceTierClassifier(unittest.TestCase):
    def test_tier_1_sources(self):
        for url in (
            "https://www.reuters.com/world/asia-pacific/telstra-outage",
            "https://asic.gov.au/about-asic/news-centre/",
            "https://www.acma.gov.au/articles/2026-07/investigation",
            "https://exchange.telstra.com.au/service-status/",
        ):
            self.assertEqual(classify_source_tier(url), 1, url)

    def test_tier_2_sources(self):
        for url in (
            "https://www.abc.net.au/news/2026-07-11/telstra-outage/",
            "https://www.afr.com/companies/telecommunications/",
            "https://www.theguardian.com/australia-news/",
        ):
            self.assertEqual(classify_source_tier(url), 2, url)

    def test_tier_3_sources(self):
        for url in (
            "https://www.linkedin.com/posts/some-analyst",
            "https://downdetector.com.au/status/telstra/",
            "https://www.itnews.com.au/news/story",  # note: itnews is tier 2
        ):
            tier = classify_source_tier(url)
            self.assertIn(tier, (2, 3), url)  # specialist band

    def test_tier_4_social_and_unknown(self):
        for url in (
            "https://twitter.com/user/status/123",
            "https://www.reddit.com/r/australia/comments/",
            "https://random-blog-42.example/post",
            "https://some-unknown-domain.io/article",
        ):
            self.assertEqual(classify_source_tier(url), 4, url)

    def test_subdomain_suffix_match(self):
        self.assertEqual(classify_source_tier("https://news.abc.net.au/story"), 2)
        self.assertEqual(classify_source_tier("https://sub.deep.reuters.com/x"), 1)

    def test_conservative_defaults(self):
        # Empty / None / malformed must never yield a false Tier 1.
        for bad in ("", "not a url", "http://", "://broken", "javascript:alert(1)"):
            self.assertEqual(classify_source_tier(bad), DEFAULT_TIER, repr(bad))

    def test_extract_domain(self):
        self.assertEqual(extract_domain("https://www.abc.net.au/x"), "abc.net.au")
        self.assertEqual(extract_domain("abc.net.au/x"), "abc.net.au")
        self.assertEqual(extract_domain("https://user:pw@host.com:8080/x"), "host.com")
        self.assertEqual(extract_domain(""), "")

    def test_no_false_tier_1(self):
        # An aggregator link must resolve to Tier 4 even if it mentions a regulator.
        self.assertEqual(
            classify_source_tier("https://reddit.com/r/asic-quotes-regulator"), 4
        )

    def test_labels(self):
        self.assertIn("Tier 1", tier_label(1))
        self.assertIn("Tier 4", tier_label(4))

    def test_class_wrapper(self):
        clf = SourceTierClassifier()
        tier, label = clf.classify_with_label("https://reuters.com/x")
        self.assertEqual(tier, 1)
        self.assertIn("Tier 1", label)

    def test_performance(self):
        urls = [f"https://example{i}.com/article/{i}" for i in range(1000)]
        start = time.perf_counter()
        for u in urls:
            classify_source_tier(u)
        avg_ms = (time.perf_counter() - start) / len(urls) * 1000
        self.assertLess(avg_ms, 10.0, f"too slow: {avg_ms:.4f} ms/source")


if __name__ == "__main__":
    unittest.main()
