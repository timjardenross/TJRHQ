#!/usr/bin/env python3
"""
Source Audit Tool — Test all intelligence sources for health.

Run this to identify which sources are broken, which are working, and which need repair.

Usage:
    python tools/intelligence/audit_sources.py                # Full audit
    python tools/intelligence/audit_sources.py --quick         # Fast 10-source sample
    python tools/intelligence/audit_sources.py --category rss  # Test only RSS sources
    python tools/intelligence/audit_sources.py --output report.json

Output:
    - Console: summary + failures
    - JSON: detailed results (if --output specified)
    - Return code: 0 (all pass) | 1 (some fail) | 2 (critical fail)
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

# Bootstrap .env
REPO_ROOT = Path(__file__).parent.parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

import os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# Import source registry
sys.path.insert(0, str(REPO_ROOT / "tools" / "intelligence"))
from seed_source_registry import SOURCES


@dataclass
class SourceTest:
    """Result of testing a single source."""
    source_name: str
    source_type: str
    category: str
    active: bool
    url: str
    rss_url: Optional[str]
    api_endpoint: Optional[str]
    status: str  # "PASS" | "WARN" | "FAIL" | "SKIP"
    http_code: Optional[int]
    error: Optional[str]
    latency_ms: float
    content_preview: Optional[str]  # First 200 chars of response
    recommendation: Optional[str]  # "activate" | "repair" | "remove" | "monitor"


def test_source(source: dict, timeout: int = 15) -> SourceTest:
    """Test a single source. Return result."""
    name = source["source_name"]
    source_type = source["source_type"]
    active = source["active"]
    url = source.get("url", "")
    rss_url = source.get("rss_url")
    api_endpoint = source.get("api_endpoint")
    category = source.get("category", "")

    # Determine what to test
    test_url = None
    test_type = None
    if source_type == "rss" and rss_url:
        test_url = rss_url
        test_type = "RSS"
    elif source_type == "api" and api_endpoint:
        test_url = api_endpoint
        test_type = "API"
    elif source_type == "scrape" and url:
        test_url = url
        test_type = "SCRAPE"
    else:
        return SourceTest(
            source_name=name,
            source_type=source_type,
            category=category,
            active=active,
            url=url,
            rss_url=rss_url,
            api_endpoint=api_endpoint,
            status="SKIP",
            http_code=None,
            error="No valid endpoint (manual source?)",
            latency_ms=0,
            content_preview=None,
            recommendation="manual_only"
        )

    # Test the endpoint
    start = time.time()
    try:
        req = urllib.request.Request(test_url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency_ms = (time.time() - start) * 1000
            body = resp.read(1024).decode("utf-8", errors="ignore")  # First 1KB

            # Basic validation
            status = "PASS"
            recommendation = None
            error = None

            if resp.status != 200:
                status = "WARN"
                error = f"HTTP {resp.status}"
                recommendation = "investigate"

            # Check for common failure patterns
            if "bot" in body.lower() and "detect" in body.lower():
                status = "FAIL"
                error = "Bot detection triggered"
                recommendation = "blocked_remove"
            elif "404" in body or "not found" in body.lower():
                status = "FAIL"
                error = "404 Not Found"
                recommendation = "url_update_needed"
            elif "sign in" in body.lower() or "login" in body.lower():
                status = "FAIL"
                error = "Authentication required"
                recommendation = "auth_gated"
            elif len(body.strip()) < 50:
                status = "WARN"
                error = "Response too short (may be empty feed)"
                recommendation = "monitor"

            if latency_ms > 10000:
                status = "WARN" if status == "PASS" else status
                error = f"Very slow ({latency_ms:.0f}ms)" if not error else error
                recommendation = "slow_may_timeout"

            return SourceTest(
                source_name=name,
                source_type=source_type,
                category=category,
                active=active,
                url=url,
                rss_url=rss_url,
                api_endpoint=api_endpoint,
                status=status,
                http_code=resp.status,
                error=error,
                latency_ms=latency_ms,
                content_preview=body[:200],
                recommendation=recommendation
            )

    except urllib.error.HTTPError as e:
        latency_ms = (time.time() - start) * 1000
        error_msg = f"HTTP {e.code}"
        recommendation = "investigate"

        if e.code == 403:
            error_msg = "403 Forbidden (bot detection or auth required)"
            recommendation = "blocked_remove"
        elif e.code == 404:
            error_msg = "404 Not Found (URL may have changed)"
            recommendation = "url_update_needed"
        elif e.code == 401:
            error_msg = "401 Unauthorized"
            recommendation = "auth_gated"
        elif e.code >= 500:
            error_msg = f"Server error {e.code}"
            recommendation = "monitor"

        return SourceTest(
            source_name=name,
            source_type=source_type,
            category=category,
            active=active,
            url=url,
            rss_url=rss_url,
            api_endpoint=api_endpoint,
            status="FAIL",
            http_code=e.code,
            error=error_msg,
            latency_ms=latency_ms,
            content_preview=None,
            recommendation=recommendation
        )

    except urllib.error.URLError as e:
        latency_ms = (time.time() - start) * 1000
        error_msg = str(e.reason)
        recommendation = "investigate"

        if "timeout" in error_msg.lower():
            recommendation = "timeout_check"
        elif "dns" in error_msg.lower() or "name or service" in error_msg.lower():
            error_msg = "DNS resolution failed"
            recommendation = "dns_failure"
        elif "connection refused" in error_msg.lower():
            error_msg = "Connection refused"
            recommendation = "service_down"

        return SourceTest(
            source_name=name,
            source_type=source_type,
            category=category,
            active=active,
            url=url,
            rss_url=rss_url,
            api_endpoint=api_endpoint,
            status="FAIL",
            http_code=None,
            error=error_msg,
            latency_ms=latency_ms,
            content_preview=None,
            recommendation=recommendation
        )

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        return SourceTest(
            source_name=name,
            source_type=source_type,
            category=category,
            active=active,
            url=url,
            rss_url=rss_url,
            api_endpoint=api_endpoint,
            status="FAIL",
            http_code=None,
            error=f"Exception: {str(e)[:100]}",
            latency_ms=latency_ms,
            content_preview=None,
            recommendation="investigate"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Audit intelligence sources for health",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/intelligence/audit_sources.py                    # Full audit
  python tools/intelligence/audit_sources.py --quick              # 10-source sample
  python tools/intelligence/audit_sources.py --active-only         # Active sources only
  python tools/intelligence/audit_sources.py --output report.json  # Save results
  python tools/intelligence/audit_sources.py --category regulatory # Filter by category
        """
    )
    parser.add_argument("--quick", action="store_true", help="Test first 10 sources only")
    parser.add_argument("--active-only", action="store_true", help="Test only active sources")
    parser.add_argument("--category", help="Test only sources in this category (e.g., 'rss', 'regulatory')")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds (default: 15)")
    parser.add_argument("--output", help="Save detailed results to JSON file")
    args = parser.parse_args()

    # Filter sources
    sources_to_test = SOURCES
    if args.active_only:
        sources_to_test = [s for s in sources_to_test if s["active"]]
    if args.category:
        sources_to_test = [s for s in sources_to_test if s.get("source_type") == args.category or s.get("category") == args.category]
    if args.quick:
        sources_to_test = sources_to_test[:10]

    # Run tests
    print(f"\n{'='*80}")
    print(f"Intelligence Source Audit")
    print(f"{'='*80}")
    print(f"\nTesting {len(sources_to_test)} sources (timeout: {args.timeout}s)...\n")

    results = []
    start_time = time.time()

    for i, source in enumerate(sources_to_test, 1):
        name = source["source_name"]
        active = "✓" if source["active"] else "○"
        sys.stdout.write(f"\r  [{i:2d}/{len(sources_to_test)}] {active} {name:<50}")
        sys.stdout.flush()

        result = test_source(source, timeout=args.timeout)
        results.append(result)

    elapsed = time.time() - start_time
    print(f"\n\nAudit complete in {elapsed:.1f}s\n")

    # Summarize
    passed = [r for r in results if r.status == "PASS"]
    warned = [r for r in results if r.status == "WARN"]
    failed = [r for r in results if r.status == "FAIL"]
    skipped = [r for r in results if r.status == "SKIP"]

    print(f"{'─'*80}")
    print(f"RESULTS: {len(passed)} PASS | {len(warned)} WARN | {len(failed)} FAIL | {len(skipped)} SKIP")
    print(f"{'─'*80}\n")

    if passed:
        print(f"✓ HEALTHY SOURCES ({len(passed)}):")
        for r in passed:
            print(f"  ✓ {r.source_name:<50} ({r.latency_ms:6.0f}ms)")

    if warned:
        print(f"\n⚠️  WARNINGS ({len(warned)}):")
        for r in warned:
            print(f"  ⚠️  {r.source_name:<50} {r.error}")

    if failed:
        print(f"\n✗ FAILURES ({len(failed)}):")
        for r in failed:
            status_icon = {
                "blocked_remove": "🚫",
                "timeout_check": "⏱️ ",
                "dns_failure": "🌐",
                "auth_gated": "🔒",
                "url_update_needed": "🔗",
            }.get(r.recommendation, "✗ ")
            print(f"  {status_icon} {r.source_name:<45} {r.error:<35} [{r.recommendation}]")

    if skipped:
        print(f"\n⊘ SKIPPED ({len(skipped)}):")
        for r in skipped:
            print(f"  ⊘ {r.source_name:<50} (manual)")

    # Detailed report
    print(f"\n{'='*80}")
    print(f"RECOMMENDATIONS")
    print(f"{'='*80}\n")

    by_recommendation = {}
    for r in results:
        rec = r.recommendation or "ok"
        if rec not in by_recommendation:
            by_recommendation[rec] = []
        by_recommendation[rec].append(r)

    recommendations = {
        "activate": "🟢 ACTIVATE (staged source, ready to enable)",
        "monitor": "🟡 MONITOR (working but slow or sparse feed)",
        "investigate": "🟠 INVESTIGATE (may be fixable with URL/auth update)",
        "repair": "🟠 REPAIR (broken but replacement exists)",
        "blocked_remove": "🔴 REMOVE (bot-blocked or auth-gated permanently)",
        "timeout_check": "🟠 TIMEOUT (very slow, may need retry logic)",
        "dns_failure": "🔴 REMOVE (DNS not resolving, domain may be gone)",
        "auth_gated": "🔴 REMOVE (requires credentials we don't have)",
        "url_update_needed": "🟠 FIX_URL (URL may have changed, find new one)",
        "service_down": "🟡 MONITOR (service appears down, may be temporary)",
        "manual_only": "⊘ SKIP (manual source, no URL to test)",
        "ok": "✓ OK (no issues)",
    }

    for rec_key in ["activate", "repair", "investigate", "timeout_check", "url_update_needed", "blocked_remove", "dns_failure", "auth_gated", "monitor", "service_down", "manual_only", "ok"]:
        if rec_key in by_recommendation:
            sources = by_recommendation[rec_key]
            label = recommendations.get(rec_key, rec_key)
            print(f"{label} ({len(sources)}):")
            for r in sources:
                print(f"  • {r.source_name}")
            print()

    # Save JSON
    if args.output:
        output_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_tested": len(results),
            "summary": {
                "pass": len(passed),
                "warn": len(warned),
                "fail": len(failed),
                "skip": len(skipped),
            },
            "results": [asdict(r) for r in results],
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"Detailed results saved to: {args.output}\n")

    # Exit code
    if failed:
        return 1
    if warned:
        return 1  # Still flag warnings as needs attention
    return 0


if __name__ == "__main__":
    sys.exit(main())
