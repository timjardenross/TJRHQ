"""
Source-tier classifier — Phase A Stage 3 (auto-tier by source authority).

Classifies a signal's source URL into Tier 1–4 by domain, where lower tier =
higher authority. 100% rule-based, no LLM, no network — deterministic and fast
(<1ms/source), matching the zero-heavy-deps philosophy of classifier.py.

  Tier 1  Primary/authoritative: wire services, regulators, official statements
  Tier 2  Established media & industry analysts
  Tier 3  Specialist publications, professional networks, industry forums
  Tier 4  Social / aggregators / unverified (DEFAULT — conservative)

Design note: this is DISTINCT from intelligence_source_registry.priority_rank,
which is a curated per-source priority set by the source catalogue. source_tier
is auto-derived per signal from whatever URL the signal actually carries, so a
Tier-1 regulator quoted via a Tier-4 aggregator link is scored on the link it
arrived on. Matching is by domain SUFFIX so subdomains (news.abc.net.au) resolve
to their parent. Unknown domains are Tier 4 by design (never a false Tier 1).
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

log = logging.getLogger(__name__)

# ─── Domain → tier tables (Australian OR-intelligence focused) ────────────────
# Ordered most-authoritative first. A domain listed in a lower tier wins even if
# it also appears lower down (first match by ascending tier).

TIER_1_DOMAINS: tuple[str, ...] = (
    # Wire services
    "reuters.com", "apnews.com", "bloomberg.com", "afp.com",
    # Australian regulators / official bodies
    "asic.gov.au", "apra.gov.au", "rba.gov.au", "acma.gov.au",
    "accc.gov.au", "oaic.gov.au", "austrac.gov.au", "asd.gov.au",
    "cyber.gov.au", "acsc.gov.au", "aemo.com.au", "bom.gov.au",
    "homeaffairs.gov.au", "infrastructure.gov.au", "treasury.gov.au",
    "auspaynet.com.au", "nbnco.com.au",
    # Official carrier / operator status & newsroom domains (first-party)
    "telstra.com", "telstra.com.au", "optus.com.au", "tpgtelecom.com.au",
    "vodafone.com.au", "exchange.telstra.com.au",
)

TIER_2_DOMAINS: tuple[str, ...] = (
    # Established Australian media
    "abc.net.au", "afr.com", "smh.com.au", "theage.com.au",
    "news.com.au", "theaustralian.com.au", "9news.com.au",
    "7news.com.au", "sbs.com.au", "theguardian.com", "itnews.com.au",
    # Established international / financial press
    "ft.com", "wsj.com", "nytimes.com", "bbc.com", "bbc.co.uk",
    "cnbc.com", "theregister.com", "arstechnica.com",
)

TIER_3_DOMAINS: tuple[str, ...] = (
    # Specialist / trade / professional networks
    "linkedin.com", "techcrunch.com", "zdnet.com", "computerworld.com",
    "cso.com.au", "cyberdaily.au", "innovationaus.com",
    "fintechweekly.com", "finextra.com", "bankingday.com",
    "downdetector.com", "downdetector.com.au", "aussieoutages.com",
    "statuspage.io", "stat.us",
)

TIER_4_DOMAINS: tuple[str, ...] = (
    # Social / aggregators / self-published — explicit for clarity; also the default
    "reddit.com", "twitter.com", "x.com", "facebook.com",
    "medium.com", "substack.com", "youtube.com", "tiktok.com",
    "wordpress.com", "blogspot.com", "t.me",
)

_TIER_TABLE: tuple[tuple[int, tuple[str, ...]], ...] = (
    (1, TIER_1_DOMAINS),
    (2, TIER_2_DOMAINS),
    (3, TIER_3_DOMAINS),
    (4, TIER_4_DOMAINS),
)

DEFAULT_TIER = 4  # conservative: unknown = discovery-only


def extract_domain(url: str) -> str:
    """Return the lowercased hostname of a URL, without a leading 'www.'.

    Tolerates bare domains ('abc.net.au/news') and malformed input; returns ''
    on failure so the caller falls through to the default tier.
    """
    if not url:
        return ""
    try:
        candidate = url.strip()
        if "://" not in candidate:
            candidate = "//" + candidate  # let urlparse treat it as netloc
        host = urlparse(candidate).netloc or ""
        host = host.split("@")[-1].split(":")[0].lower()  # strip creds + port
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("source_tier: failed to parse url %r: %s", url, exc)
        return ""


def classify_source_tier(url: str) -> int:
    """Classify a source URL into Tier 1–4 (1 = most authoritative).

    Matching is by domain suffix, so 'news.abc.net.au' matches 'abc.net.au'.
    Unknown or unparseable domains return Tier 4.
    """
    domain = extract_domain(url)
    if not domain:
        return DEFAULT_TIER

    for tier, domains in _TIER_TABLE:
        for known in domains:
            if domain == known or domain.endswith("." + known):
                return tier

    log.debug("source_tier: unknown domain %r -> Tier %d", domain, DEFAULT_TIER)
    return DEFAULT_TIER


def tier_label(tier: int) -> str:
    """Human-readable label for a tier (for UI / brief provenance)."""
    return {
        1: "Tier 1 — Primary/Authoritative",
        2: "Tier 2 — Established Media",
        3: "Tier 3 — Specialist/Professional",
        4: "Tier 4 — Social/Unverified",
    }.get(tier, f"Tier {tier}")


class SourceTierClassifier:
    """Object wrapper (parity with the design spec's pipeline integration)."""

    def classify(self, url: str) -> int:
        return classify_source_tier(url)

    def classify_with_label(self, url: str) -> tuple[int, str]:
        tier = classify_source_tier(url)
        return tier, tier_label(tier)
