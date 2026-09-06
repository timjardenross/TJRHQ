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

        The router itself is generic infra - its result dict never has a
        "findings" key, only a raw "response" string (the model's text
        completion). orchestrator.py does analysis_result.get("findings", [])
        directly on the router's dict, which silently returned [] on every
        single run regardless of what the model actually produced - the
        real cause of 5 straight days of "0 findings" (not the oversized
        evidence payload fixed in collector.py, though that was worth
        fixing too). Parse "response" as the JSON the prompt asked for and
        surface "findings" on the returned dict so the caller's .get()
        actually finds something.
        """
        prompt = self._build_analysis_prompt(evidence, context)
        result = self._call_router("self-improvement-analyse", prompt)
        if result.get("success"):
            result["findings"] = self._parse_findings(result.get("response", ""))
        return result

    @staticmethod
    def _parse_findings(response_text: str) -> list[dict[str, Any]]:
        """Extract the findings array from the model's raw JSON text response."""
        text = response_text.strip()
        # The prompt forbids markdown fences, but models don't always comply.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            log.error(f"Failed to parse findings JSON from model response: {exc}")
            return []
        return parsed.get("findings", []) if isinstance(parsed, dict) else []

    def critique_findings(self, findings: list[dict[str, Any]], context: Optional[str] = None) -> dict[str, Any]:
        """
        Send findings to Model Router for adversarial critique.

        Expected route: /api/model/self-improvement-critique
        Returns: Review feedback with high-confidence findings flagged
        """
        prompt = self._build_critique_prompt(findings, context)
        return self._call_router("self-improvement-critique", prompt)

    def investigate_opportunity(self, candidate: dict[str, Any], context: Optional[str] = None) -> dict[str, Any]:
        """
        HQ Evolution (section 22): ask the model to interpret already-
        collected evidence into an investigation narrative. The model may
        propose an interpretation; it must not invent evidence, and its
        output is never treated as a permission decision (relevance.py and
        PolicyEngine remain authoritative for that).

        Expected route: /api/model/hq-evolution-investigate
        Returns: investigation dict with why/fit/benefits/risks/alternatives/recommendation
        """
        prompt = self._build_investigation_prompt(candidate, context)
        result = self._call_router("hq-evolution-investigate", prompt)
        if result.get("success"):
            result["investigation"] = self._parse_json_object(result.get("response", ""))
        return result

    @staticmethod
    def _parse_json_object(response_text: str) -> dict[str, Any]:
        text = response_text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            log.error(f"Failed to parse investigation JSON from model response: {exc}")
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _build_investigation_prompt(self, candidate: dict[str, Any], context: Optional[str] = None) -> str:
        prompt = """TASK: Investigate whether this HQ Evolution candidate is genuinely worth pursuing for TJR HQ.

CRITICAL: Use ONLY the evidence provided below. Do NOT invent evidence, metrics, or claims not present in the candidate data. You may interpret the evidence; you may not manufacture it. Output ONLY valid JSON, no markdown, no explanation outside the JSON.

CANDIDATE:
"""
        prompt += json.dumps(candidate, indent=2)
        if context:
            prompt += f"\n\nCONTEXT:\n{context}"

        prompt += """

OUTPUT FORMAT (REQUIRED - ONLY OUTPUT THIS, NOTHING ELSE):
{
  "why_hq_is_looking_at_this": "...",
  "fit_with_hq": "weak|moderate|strong",
  "potential_benefits": ["..."],
  "cost_impact": "lower|neutral|higher|unknown",
  "risks": ["..."],
  "implementation_effort": "low|moderate|high",
  "alternatives": ["..."],
  "confidence": 0.7,
  "recommendation": "worth_pursuing|keep_watching|not_useful",
  "recommendation_rationale": "..."
}
"""
        return prompt

    def evaluate_outcome(self, evidence_bundle: dict[str, Any], context: Optional[str] = None) -> dict[str, Any]:
        """
        HQ Evolution V2 (sections 10, 15): ask the model to interpret
        already-collected outcome evidence — the Outcome Contract, its
        baseline, and the evidence gathered during the observation window.
        The model may propose an interpretation of qualitative evidence; it
        must not invent evidence, and its output is never treated as a
        permission decision — only as one input to the fixed
        IMPROVED/NO_MATERIAL_CHANGE/REGRESSED/INCONCLUSIVE vocabulary,
        schema-validated by outcome_schema.py.

        Expected route: /api/model/hq-evolution-evaluate-outcome
        Returns: evaluation dict with outcome_result/evidence_summary/confidence/...
        """
        prompt = self._build_outcome_evaluation_prompt(evidence_bundle, context)
        result = self._call_router("hq-evolution-evaluate-outcome", prompt)
        if result.get("success"):
            result["evaluation"] = self._parse_json_object(result.get("response", ""))
        return result

    def _build_outcome_evaluation_prompt(self, evidence_bundle: dict[str, Any], context: Optional[str] = None) -> str:
        prompt = """TASK: Evaluate whether an HQ change actually delivered the benefit it was approved for.

CRITICAL: Use ONLY the evidence provided below. Do NOT invent evidence, metrics, or claims not present in the bundle. If the evidence is genuinely insufficient or ambiguous, say so — outcome_result must be "inconclusive" rather than a guess. A technically successful implementation does NOT by itself mean the expected benefit occurred. Output ONLY valid JSON, no markdown, no explanation outside the JSON.

EVIDENCE BUNDLE (outcome contract, baseline, and evidence collected during the observation window):
"""
        prompt += json.dumps(evidence_bundle, indent=2, default=str)
        if context:
            prompt += f"\n\nCONTEXT:\n{context}"

        prompt += """

OUTPUT FORMAT (REQUIRED - ONLY OUTPUT THIS, NOTHING ELSE):
{
  "outcome_result": "improved|no_material_change|regressed|inconclusive",
  "evidence_summary": "...",
  "confidence": "low|moderate|high",
  "what_worked": "...",
  "what_did_not": "...",
  "unexpected_effects": ["..."],
  "future_implication": "..."
}
"""
        return prompt

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
        prompt = """TASK: Analyze USS TJR repository evidence and produce JSON findings.

CRITICAL: Output ONLY valid JSON. Do NOT output any text before or after JSON. Do NOT output markdown. Do NOT output explanations.

EVIDENCE:
"""
        prompt += json.dumps(evidence, indent=2)

        if context:
            prompt += f"\n\nCONTEXT:\n{context}"

        prompt += """

OUTPUT FORMAT (REQUIRED - ONLY OUTPUT THIS, NOTHING ELSE):
```json
{
  "findings": [
    {
      "category": "doc_drift|duplicate_implementation|placeholder_code|dead_code|missing_test|config_drift|stale_adr|observability_gap|security_gap|resilience_gap|router_bypass|route_policy_drift|silent_fallback|model_catalogue_drift|knowledge_health|performance_gap|operational_failure|governance_violation|automation_opportunity",
      "title": "SHORT_TITLE",
      "evidence": [{"type": "file_exists|file_missing|code_reference|git_history|test_result|config_value|service_status|log_entry|broken_link|duplicate_file|unreferenced_code|timing_data|model_output|manual_inspection", "observation": "WHAT_WAS_FOUND", "location": "PATH_OR_URL"}],
      "confidence": 0.95,
      "severity": "info|low|medium|high|critical",
      "proposed_action": {"type": "delete|add|modify|consolidate|document|refactor|test|configure|monitor", "description": "ACTION_DESC"},
      "expected_benefit": "WHAT_IMPROVES"
    }
  ]
}
```

RULES:
- Output ONLY the JSON object, nothing else
- Do NOT output markdown code blocks
- Do NOT output explanations before or after
- Category must be from the list above
- Severity must be: info, low, medium, high, or critical
- confidence must be a number between 0.0 and 1.0
- If no findings, output: {"findings": []}
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
