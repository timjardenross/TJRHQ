"""USS TJR — Paperclip API Client (MSN-0014B).

Thin HTTP client for the local Paperclip instance.  Requires no authentication
in local_trusted + loopback mode — all requests from 127.0.0.1 are implicitly
authenticated as the built-in local-board user.

Design principles:
  - Zero auth config.  No tokens are read, stored, or logged.
  - Silent failure.  Every method returns None / [] on error; Commander never
    blocks on Paperclip availability.
  - Stdlib only.  No third-party dependencies beyond what USS TJR already uses.
  - Read from environment first, fall back to discovered defaults.

Configuration (all optional — defaults match MSN-0014A discovery):
    PAPERCLIP_ENABLED=true
    PAPERCLIP_BASE_URL=http://127.0.0.1:3100
    PAPERCLIP_COMPANY_ID=d416eafd-625d-4474-a53e-cc6966689bde
    PAPERCLIP_XO_AGENT_ID=664f7f52-15d8-4358-957e-d095868f74e1
    PAPERCLIP_CHIEF_ENGINEER_AGENT_ID=0b911a35-0c82-420c-86dc-5ca35ae05df4

Usage:
    from tools.paperclip.client import PaperclipClient
    pc = PaperclipClient()
    if pc.is_enabled():
        issue = pc.create_issue("MSN-0015: Implement Voice Core", priority="high")
        print(issue["identifier"])   # e.g. "STA-3"
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


# ---------------------------------------------------------------------------
# Defaults (from MSN-0014A discovery)
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL = "http://127.0.0.1:3100"
_DEFAULT_COMPANY_ID = "d416eafd-625d-4474-a53e-cc6966689bde"
_DEFAULT_XO_AGENT_ID = "664f7f52-15d8-4358-957e-d095868f74e1"
_DEFAULT_CHIEF_ENGINEER_AGENT_ID = "0b911a35-0c82-420c-86dc-5ca35ae05df4"
_DEFAULT_TIMEOUT = 8  # seconds — generous for local


class PaperclipClient:
    """HTTP client for the local Paperclip API.

    All public methods return None / [] on any error.  Callers should treat
    a None return as "Paperclip unavailable" and continue normally.
    """

    def __init__(
        self,
        base_url: str | None = None,
        company_id: str | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (base_url or os.getenv("PAPERCLIP_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
        self.company_id = company_id or os.getenv("PAPERCLIP_COMPANY_ID", _DEFAULT_COMPANY_ID)
        self.xo_agent_id = os.getenv("PAPERCLIP_XO_AGENT_ID", _DEFAULT_XO_AGENT_ID)
        self.chief_engineer_agent_id = os.getenv(
            "PAPERCLIP_CHIEF_ENGINEER_AGENT_ID", _DEFAULT_CHIEF_ENGINEER_AGENT_ID
        )
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        """Return True if Paperclip integration is enabled and the server is reachable."""
        enabled_flag = os.getenv("PAPERCLIP_ENABLED", "true").lower()
        if enabled_flag in ("false", "0", "no", "off"):
            return False
        result = self.health()
        return result.get("status") == "ok"

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """GET /api/health — no auth required."""
        return self._get("/api/health") or {}

    # ------------------------------------------------------------------
    # Companies
    # ------------------------------------------------------------------

    def list_companies(self) -> list[dict[str, Any]]:
        """GET /api/companies — returns all companies visible to local-board."""
        result = self._get("/api/companies")
        return result if isinstance(result, list) else []

    def get_company(self, company_id: str | None = None) -> dict[str, Any] | None:
        """GET /api/companies/{id}."""
        cid = company_id or self.company_id
        result = self._get(f"/api/companies/{cid}")
        return result if isinstance(result, dict) and "id" in result else None

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    def list_agents(self, company_id: str | None = None) -> list[dict[str, Any]]:
        """GET /api/companies/{id}/agents."""
        cid = company_id or self.company_id
        result = self._get(f"/api/companies/{cid}/agents")
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    def list_issues(
        self,
        status: str | None = None,
        limit: int = 20,
        company_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /api/companies/{id}/issues — optionally filtered by status."""
        cid = company_id or self.company_id
        params = f"?limit={limit}"
        if status:
            params += f"&status={status}"
        result = self._get(f"/api/companies/{cid}/issues{params}")
        return result if isinstance(result, list) else []

    def create_issue(
        self,
        title: str,
        description: str | None = None,
        priority: str = "medium",
        assignee_agent_id: str | None = None,
        company_id: str | None = None,
    ) -> dict[str, Any] | None:
        """POST /api/companies/{id}/issues.

        Args:
            title: Issue title (required).
            description: Markdown body (optional).
            priority: "low" | "medium" | "high" | "urgent" (default "medium").
            assignee_agent_id: Agent UUID to assign the issue to (optional).
            company_id: Override default company (optional).

        Returns:
            Full issue dict on success, None on failure.
        """
        cid = company_id or self.company_id
        payload: dict[str, Any] = {"title": title, "priority": priority}
        if description is not None:
            payload["description"] = description
        if assignee_agent_id is not None:
            payload["assigneeAgentId"] = assignee_agent_id
        result = self._post(f"/api/companies/{cid}/issues", payload)
        return result if isinstance(result, dict) and "id" in result else None

    def get_issue(self, issue_id: str) -> dict[str, Any] | None:
        """GET /api/issues/{uuid} — top-level path (company-scoped path returns 404)."""
        result = self._get(f"/api/issues/{issue_id}")
        return result if isinstance(result, dict) and "id" in result else None

    def update_issue(self, issue_id: str, **fields: Any) -> dict[str, Any] | None:
        """PATCH /api/issues/{uuid} — update any writable fields.

        Common fields: status, title, priority, assigneeAgentId.
        Valid status values: backlog | todo | in_progress | done | cancelled.
        """
        result = self._patch(f"/api/issues/{issue_id}", fields)
        return result if isinstance(result, dict) and "id" in result else None

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def list_comments(self, issue_id: str) -> list[dict[str, Any]]:
        """GET /api/issues/{uuid}/comments."""
        result = self._get(f"/api/issues/{issue_id}/comments")
        return result if isinstance(result, list) else []

    def add_comment(self, issue_id: str, body: str) -> dict[str, Any] | None:
        """POST /api/issues/{uuid}/comments.

        Args:
            issue_id: Issue UUID (not identifier like STA-3).
            body: Comment text in plain text or markdown.

        Returns:
            Comment dict on success, None on failure.
        """
        result = self._post(f"/api/issues/{issue_id}/comments", {"body": body})
        return result if isinstance(result, dict) and "id" in result else None

    # ------------------------------------------------------------------
    # Agent ID helpers
    # ------------------------------------------------------------------

    def agent_id_for_specialist(self, specialist_name: str) -> str | None:
        """Map a USS TJR specialist name to a Paperclip agent UUID.

        Returns None if no mapping exists — issue will be created unassigned.
        """
        mapping = {
            "XO": self.xo_agent_id,
            "Chief of Staff": self.xo_agent_id,   # XO is the strategic lead
            "Chief Engineer": self.chief_engineer_agent_id,
            "Coder Agent": self.chief_engineer_agent_id,  # Engineering work → Chief Engineer
        }
        return mapping.get(specialist_name)

    # ------------------------------------------------------------------
    # Internal HTTP helpers — all return None on any failure
    # ------------------------------------------------------------------

    def _get(self, path: str) -> Any:
        return self._request("GET", path)

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", path, payload)

    def _patch(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("PATCH", path, payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            try:
                err_body = json.loads(exc.read().decode())
                _warn(f"Paperclip {method} {path} → HTTP {exc.code}: {err_body.get('error', exc.reason)}")
            except Exception:  # noqa: BLE001
                _warn(f"Paperclip {method} {path} → HTTP {exc.code}")
            return None
        except OSError as exc:
            _warn(f"Paperclip {method} {path} → connection error: {exc}")
            return None
        except Exception as exc:  # noqa: BLE001
            _warn(f"Paperclip {method} {path} → unexpected error: {exc}")
            return None


def _warn(msg: str) -> None:
    """Print a non-blocking warning — never raises."""
    try:
        print(f"[paperclip] Warning: {msg}")
    except Exception:  # noqa: BLE001
        pass
