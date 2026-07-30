"""MSN-0014A — Paperclip API Discovery Script.

Non-destructive discovery: calls health, lists companies and agents.
Prints IDs only. Never prints secrets.

Usage:
    python3 tools/paperclip/discover_api.py

Requirements:
    - Paperclip running at http://127.0.0.1:3100
    - No auth configuration needed (local_trusted loopback mode)
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Config — no secrets loaded
# ---------------------------------------------------------------------------

BASE_URL = "http://127.0.0.1:3100"
TIMEOUT = 5  # seconds


# ---------------------------------------------------------------------------
# Minimal HTTP client (stdlib only — no requests dependency)
# ---------------------------------------------------------------------------

def _get(path: str) -> Any:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body)
        except Exception:
            return {"error": f"HTTP {e.code}", "body": body}
    except OSError as e:
        return {"error": f"Connection failed: {e}"}


# ---------------------------------------------------------------------------
# Discovery steps
# ---------------------------------------------------------------------------

def check_health() -> bool:
    print("\n=== Health ===")
    result = _get("/api/health")
    if "error" in result:
        print(f"  FAIL: {result['error']}")
        return False
    print(f"  status:         {result.get('status')}")
    print(f"  version:        {result.get('version')}")
    print(f"  deploymentMode: {result.get('deploymentMode')}")
    print(f"  exposure:       {result.get('deploymentExposure')}")
    print(f"  authReady:      {result.get('authReady')}")
    print(f"  bootstrapStatus:{result.get('bootstrapStatus')}")
    return result.get("status") == "ok"


def discover_companies() -> list[dict]:
    print("\n=== Companies ===")
    result = _get("/api/companies")
    if isinstance(result, dict) and "error" in result:
        print(f"  FAIL: {result['error']}")
        return []
    companies = result if isinstance(result, list) else []
    for c in companies:
        print(f"  id:     {c.get('id')}")
        print(f"  name:   {c.get('name')}")
        print(f"  prefix: {c.get('issuePrefix')}")
        print(f"  status: {c.get('status')}")
        print()
    return companies


def discover_agents(company_id: str) -> list[dict]:
    print(f"=== Agents (company: {company_id}) ===")
    result = _get(f"/api/companies/{company_id}/agents")
    if isinstance(result, dict) and "error" in result:
        print(f"  FAIL: {result['error']}")
        return []
    agents = result if isinstance(result, list) else []
    for a in agents:
        print(f"  id:       {a.get('id')}")
        print(f"  name:     {a.get('name')}")
        print(f"  role:     {a.get('role')}")
        print(f"  urlKey:   {a.get('urlKey')}")
        print(f"  model:    {a.get('adapterConfig', {}).get('model', 'unknown')}")
        print(f"  reportsTo:{a.get('reportsTo')}")
        print(f"  status:   {a.get('status')}")
        print()
    return agents


def discover_issues(company_id: str) -> list[dict]:
    print(f"=== Issues (company: {company_id}) ===")
    result = _get(f"/api/companies/{company_id}/issues?limit=10")
    if isinstance(result, dict) and "error" in result:
        print(f"  FAIL: {result['error']}")
        return []
    issues = result if isinstance(result, list) else []
    if not issues:
        print("  (no issues found)")
    for i in issues:
        print(f"  {i.get('identifier'):8s}  {i.get('status'):12s}  {i.get('title', '')[:60]}")
    print()
    return issues


def check_authenticated_endpoint() -> None:
    print("=== Agent self-auth (/api/agents/me) ===")
    result = _get("/api/agents/me")
    if "error" in result:
        print(f"  Expected failure: {result['error']}")
        print("  (This endpoint requires agent JWT — not needed for Commander bridge)")
    else:
        print(f"  Authenticated as agent: {result.get('id')} / {result.get('name')}")
    print()


def print_summary(companies: list[dict], agents: list[dict]) -> None:
    print("=" * 60)
    print("SUMMARY — copy these IDs into .env or client config")
    print("=" * 60)

    # Primary company = smallest issuePrefix (STA before STAA)
    primary = sorted(companies, key=lambda c: len(c.get("issuePrefix", "ZZZ")))[0] if companies else None
    if primary:
        print(f"\nPrimary companyId:  {primary['id']}")
        print(f"  name:   {primary['name']}")
        print(f"  prefix: {primary['issuePrefix']}")

    for a in agents:
        role_label = "XO" if a.get("role") == "ceo" else a.get("name", "Agent")
        print(f"\n{role_label} agentId:  {a['id']}")
        print(f"  name:   {a.get('name')}")
        print(f"  model:  {a.get('adapterConfig', {}).get('model', 'unknown')}")

    print(f"\nBase URL:  {BASE_URL}")
    print("Auth:      none (local_trusted loopback)")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("Paperclip API Discovery — MSN-0014A")
    print(f"Target: {BASE_URL}")

    healthy = check_health()
    if not healthy:
        print("\nERROR: Paperclip is not reachable. Is it running?")
        print("  Start with: paperclip start  (or check the Paperclip menu bar app)")
        return 1

    companies = discover_companies()

    # Use primary company (shortest issuePrefix = original setup)
    primary_company = None
    if companies:
        primary_company = sorted(companies, key=lambda c: len(c.get("issuePrefix", "ZZZ")))[0]

    agents: list[dict] = []
    if primary_company:
        agents = discover_agents(primary_company["id"])
        discover_issues(primary_company["id"])

    check_authenticated_endpoint()
    print_summary(companies, agents)

    return 0


if __name__ == "__main__":
    sys.exit(main())
