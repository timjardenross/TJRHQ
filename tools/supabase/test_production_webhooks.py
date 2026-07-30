#!/usr/bin/env python3
"""
USS TJR Learning Loop — Production Webhook Integration Tests
Week 3 Real Event Stream Validation
Purpose: Test all three webhooks against production endpoints
"""

import json
import hmac
import hashlib
import time
import requests
from typing import Tuple, Dict


class ProductionWebhookTester:
    """Test production webhook endpoints."""

    def __init__(self, base_url: str = "http://localhost:5000"):
        """Initialize tester.

        Args:
            base_url: Production server base URL
        """
        self.base_url = base_url
        self.results = []

    def test_health_check(self) -> Tuple[bool, float]:
        """Test health check endpoint."""
        start = time.time()
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            latency = (time.time() - start) * 1000
            is_healthy = response.status_code == 200
            return is_healthy, latency
        except Exception as e:
            return False, -1.0

    def test_slack_webhook(
        self,
        signing_secret: str,
        payload: Dict = None
    ) -> Tuple[bool, float, int]:
        """Test Slack webhook endpoint.

        Args:
            signing_secret: Slack signing secret
            payload: Optional custom payload

        Returns:
            Tuple of (success, latency_ms, status_code)
        """
        if payload is None:
            payload = {
                "type": "event_callback",
                "event": {
                    "type": "message",
                    "channel": "C123456",
                    "user": "U789012",
                    "text": "Test: Kubernetes migration strategy",
                    "ts": "1623456789.000100"
                },
                "event_id": "Ev123456",
                "event_time": int(time.time())
            }

        request_body = json.dumps(payload)
        timestamp = str(int(time.time()))

        # Create signature
        sig_basestring = f"v0:{timestamp}:{request_body}"
        signature = "v0=" + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "X-Slack-Signature": signature,
            "X-Slack-Request-Timestamp": timestamp,
            "Content-Type": "application/json"
        }

        start = time.time()
        try:
            response = requests.post(
                f"{self.base_url}/webhook/slack",
                data=request_body,
                headers=headers,
                timeout=10
            )
            latency = (time.time() - start) * 1000
            success = response.status_code == 200
            return success, latency, response.status_code
        except Exception as e:
            return False, -1.0, 0

    def test_github_webhook(
        self,
        secret: str,
        payload: Dict = None
    ) -> Tuple[bool, float, int]:
        """Test GitHub webhook endpoint.

        Args:
            secret: GitHub webhook secret
            payload: Optional custom payload

        Returns:
            Tuple of (success, latency_ms, status_code)
        """
        if payload is None:
            payload = {
                "action": "opened",
                "pull_request": {
                    "number": 42,
                    "title": "Test: Kubernetes migration",
                    "body": "Implementation details...",
                    "user": {"login": "test-user"},
                    "html_url": "https://github.com/test/test/pull/42"
                },
                "repository": {
                    "name": "USSTJROS",
                    "url": "https://github.com/test/test"
                }
            }

        request_body = json.dumps(payload)

        # Create signature (GitHub uses SHA256)
        signature = "sha256=" + hmac.new(
            secret.encode(),
            request_body.encode(),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json"
        }

        start = time.time()
        try:
            response = requests.post(
                f"{self.base_url}/webhook/github",
                data=request_body,
                headers=headers,
                timeout=10
            )
            latency = (time.time() - start) * 1000
            success = response.status_code == 200
            return success, latency, response.status_code
        except Exception as e:
            return False, -1.0, 0

    def test_notion_webhook(
        self,
        secret: str,
        payload: Dict = None
    ) -> Tuple[bool, float, int]:
        """Test Notion webhook endpoint.

        Args:
            secret: Notion webhook secret
            payload: Optional custom payload

        Returns:
            Tuple of (success, latency_ms, status_code)
        """
        if payload is None:
            payload = {
                "type": "page",
                "page": {
                    "id": "page123",
                    "url": "https://notion.so/page123",
                    "properties": {
                        "Title": {
                            "type": "title",
                            "title": [
                                {"type": "text", "text": {"content": "Test Page"}}
                            ]
                        }
                    },
                    "last_edited_by": {"id": "user456"},
                    "last_edited_time": "2026-06-22T10:00:00.000Z"
                }
            }

        request_body = json.dumps(payload)

        # Create signature (Notion uses HMAC-SHA256)
        signature = hmac.new(
            secret.encode(),
            request_body.encode(),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "X-Notion-Signature": signature,
            "Content-Type": "application/json"
        }

        start = time.time()
        try:
            response = requests.post(
                f"{self.base_url}/webhook/notion",
                data=request_body,
                headers=headers,
                timeout=10
            )
            latency = (time.time() - start) * 1000
            success = response.status_code == 200
            return success, latency, response.status_code
        except Exception as e:
            return False, -1.0, 0

    def run_all_tests(
        self,
        slack_secret: str = "test-slack-secret",
        github_secret: str = "test-github-secret",
        notion_secret: str = "test-notion-secret"
    ):
        """Run all production webhook tests."""
        print("\n" + "="*70)
        print("USS TJR LEARNING LOOP — PRODUCTION WEBHOOK TESTS")
        print("Week 3 Real Event Stream Validation")
        print("="*70)

        # Test 1: Health check
        print("\n✅ TEST 1: Health Check")
        is_healthy, latency = self.test_health_check()
        status = "✅ PASS" if is_healthy else "❌ FAIL"
        print(f"   Status: {status}")
        print(f"   Latency: {latency:.1f}ms")

        if not is_healthy:
            print("\n❌ Server not responding. Cannot continue with webhook tests.")
            print("   Ensure server is running at: " + self.base_url)
            return

        # Test 2: Slack webhook
        print("\n✅ TEST 2: Slack Webhook")
        success, latency, status_code = self.test_slack_webhook(slack_secret)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   Status: {status}")
        print(f"   Latency: {latency:.1f}ms")
        print(f"   Response code: {status_code}")

        # Test 3: GitHub webhook
        print("\n✅ TEST 3: GitHub Webhook")
        success, latency, status_code = self.test_github_webhook(github_secret)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   Status: {status}")
        print(f"   Latency: {latency:.1f}ms")
        print(f"   Response code: {status_code}")

        # Test 4: Notion webhook
        print("\n✅ TEST 4: Notion Webhook")
        success, latency, status_code = self.test_notion_webhook(notion_secret)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   Status: {status}")
        print(f"   Latency: {latency:.1f}ms")
        print(f"   Response code: {status_code}")

        # Summary
        print("\n" + "="*70)
        print("PRODUCTION WEBHOOK TEST SUMMARY")
        print("="*70)
        print("\nDeployment checklist:")
        print("  [ ] Server responding to health checks")
        print("  [ ] Slack webhook accepting requests")
        print("  [ ] GitHub webhook accepting requests")
        print("  [ ] Notion webhook accepting requests")
        print("  [ ] All latencies <50ms")
        print("  [ ] All signature verifications passing")
        print("\nNext steps:")
        print("  1. Configure platform credentials (signing secrets)")
        print("  2. Register webhook URLs in each platform")
        print("  3. Test with real events from team")
        print("  4. Monitor production metrics")


if __name__ == "__main__":
    import sys

    # Get base URL from environment or argument
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"

    print(f"\nProduction Webhook Tester")
    print(f"Server: {base_url}")

    tester = ProductionWebhookTester(base_url=base_url)
    tester.run_all_tests()
