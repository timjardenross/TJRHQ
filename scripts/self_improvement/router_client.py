"""
Model Router client for self-improvement analysis.

Routes analysis requests to the local Model Router instead of calling
Ollama or cloud APIs directly.
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional
from datetime import datetime, timezone

log = logging.getLogger("router_client")


class ModelRouterClient:
    """Client for communicating with Model Router."""

    def __init__(self, base_url: str = "http://127.0.0.1:8891"):
        self.base_url = base_url.rstrip("/")
        self.call_log = []

    def analyse_evidence(self, evidence: dict[str, Any], context: Optional[str] = None) -> dict[str, Any]:
        """
        Send evidence to Model Router for analysis.

        Expected route: /api/model/self-improvement-analyse
        Expects response: JSON with findings array
        """
        prompt = self._build_analysis_prompt(evidence, context)
        return self._call_router("self-improvement-analyse", prompt)

    def critique_findings(self, findings: list[dict[str, Any]], context: Optional[str] = None) -> dict[str, Any]:
        """
        Send findings to Model Router for adversarial critique.

        Expected route: /api/model/self-improvement-critique
        Returns: Review feedback with high-confidence findings flagged
        """
        prompt = self._build_critique_prompt(findings, context)
        return self._call_router("self-improvement-critique", prompt)

    def generate_mission(self, finding: dict[str, Any], context: Optional[str] = None) -> dict[str, Any]:
        """
        Convert an approved finding into a mission document.

        Expected route: /api/model/self-improvement-mission
        Returns: Mission specification
        """
        prompt = self._build_mission_prompt(finding, context)
        return self._call_router("self-improvement-mission", prompt)

    def _call_router(self, task_type: str, prompt: str) -> dict[str, Any]:
        """
        Call Model Router with task_type and prompt.

        Handles network errors, timeout, schema validation.
        """
        url = f"{self.base_url}/api/model/{task_type}"
        payload = json.dumps({
            "prompt": prompt,
            "skip_escalation": True,  # self-improvement routes never escalate
        }).encode()

        log.info(f"Calling {task_type}...")
        t0 = datetime.now(timezone.utc)

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                response_data = json.loads(resp.read().decode())

            duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)

            if not response_data.get("success"):
                log.error(f"{task_type} failed: {response_data.get('error')}")
                return {
                    "success": False,
                    "error": response_data.get("error"),
                    "task_type": task_type,
                    "duration_ms": duration_ms,
                }

            # Log the call
            self._log_call(task_type, response_data, duration_ms)

            return response_data

        except urllib.error.URLError as exc:
            duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
            log.error(f"{task_type} network error: {exc}")
            self._log_call(task_type, None, duration_ms, error=str(exc))
            return {
                "success": False,
                "error": f"Network error: {exc}",
                "task_type": task_type,
                "duration_ms": duration_ms,
            }
        except Exception as exc:
            duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
            log.error(f"{task_type} unexpected error: {exc}")
            self._log_call(task_type, None, duration_ms, error=str(exc))
            return {
                "success": False,
                "error": f"Unexpected error: {exc}",
                "task_type": task_type,
                "duration_ms": duration_ms,
            }

    def _build_analysis_prompt(self, evidence: dict[str, Any], context: Optional[str] = None) -> str:
        """Build prompt for evidence analysis."""
        prompt = """You are an expert code auditor for USS TJR. Analyze the provided evidence and identify concrete improvement opportunities.

For EACH finding:
1. Cite specific evidence (file paths, line numbers, git commits)
2. Assign a category (doc_drift, dead_code, placeholder_code, etc.)
3. Estimate severity (info/low/medium/high/critical)
4. Propose concrete action
5. Be honest about confidence (0.0-1.0)

Output ONLY valid JSON. No markdown, no explanation, no preamble.

Evidence:
"""
        prompt += json.dumps(evidence, indent=2)

        if context:
            prompt += f"\n\nAdditional context:\n{context}"

        prompt += """

Respond with JSON object:
{
  "findings": [
    {
      "category": "...",
      "title": "...",
      "evidence": [...],
      "confidence": 0.95,
      "severity": "...",
      "proposed_action": { "type": "...", "description": "..." },
      "expected_benefit": "..."
    }
  ]
}
"""
        return prompt

    def _build_critique_prompt(self, findings: list[dict[str, Any]], context: Optional[str] = None) -> str:
        """Build prompt for finding critique."""
        prompt = """You are a skeptical code reviewer. Review these proposed findings and challenge any that are weak.

For EACH finding:
1. Is the evidence truly conclusive?
2. Could there be an alternative explanation?
3. Does the confidence level match the evidence?
4. Flag weak or speculative findings.

Output ONLY valid JSON.

Findings:
"""
        prompt += json.dumps(findings, indent=2)

        if context:
            prompt += f"\n\nContext:\n{context}"

        prompt += """

Respond with JSON object:
{
  "reviews": [
    {
      "finding_index": 0,
      "verdict": "strong|weak|speculative",
      "confidence_adjustment": -0.1,
      "concerns": ["..."],
      "keep_finding": true
    }
  ]
}
"""
        return prompt

    def _build_mission_prompt(self, finding: dict[str, Any], context: Optional[str] = None) -> str:
        """Build prompt for mission generation."""
        prompt = """Convert this improvement finding into a bounded mission specification.

Finding:
"""
        prompt += json.dumps(finding, indent=2)

        if context:
            prompt += f"\n\nContext:\n{context}"

        prompt += """

Create a mission that:
1. Has a specific, measurable objective
2. Lists exact files/components to touch
3. Explicitly excludes out-of-scope work
4. Includes success criteria
5. Describes required tests
6. Has a rollback plan

Output ONLY valid JSON:
{
  "mission": {
    "objective": "...",
    "scope": { "include": [...], "exclude": [...] },
    "success_criteria": [...],
    "required_tests": [...],
    "rollback_plan": "...",
    "estimated_duration_hours": 2
  }
}
"""
        return prompt

    def _log_call(
        self,
        task_type: str,
        response: Optional[dict[str, Any]],
        duration_ms: int,
        error: Optional[str] = None
    ) -> None:
        """Log a Model Router call."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "task_type": task_type,
            "duration_ms": duration_ms,
            "success": error is None,
            "error": error,
        }
        if response:
            entry["model"] = response.get("model")
            entry["escalated"] = response.get("escalated")
            entry["token_info"] = response.get("token_info")

        self.call_log.append(entry)
        log.debug(f"Logged call: {task_type} duration={duration_ms}ms success={error is None}")

    def health_check(self) -> bool:
        """Check if Model Router is healthy."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/health", timeout=2) as resp:
                return resp.status == 200
        except Exception as exc:
            log.error(f"Health check failed: {exc}")
            return False

    def get_router_status(self) -> dict[str, Any]:
        """Get router status (loaded models, routing policy)."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/model/status", timeout=5) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            log.error(f"Failed to get router status: {exc}")
            return {"error": str(exc)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    client = ModelRouterClient()

    # Test health check
    if client.health_check():
        log.info("Model Router is healthy")
        status = client.get_router_status()
        log.info(f"Router status: {status}")
    else:
        log.error("Model Router is not reachable")
