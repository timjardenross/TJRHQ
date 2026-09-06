"""
Deterministic policy engine for self-improvement classification.

Applies configurable rules to determine automation eligibility and risk.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional
from enum import Enum

log = logging.getLogger("policy")


class AutomationEligibility(Enum):
    """Possible automation states."""
    AUTO_APPLY = "auto_apply"
    AUTO_WITH_VERIFICATION = "auto_with_verification"
    NEEDS_SIGNOFF = "needs_signoff"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    MANUAL_ONLY = "manual_only"


class RiskLevel(Enum):
    """Risk classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyEngine:
    """Applies policy rules to findings."""

    def __init__(self, policy_file: Path):
        self.config = self._load_policy(policy_file)
        self.category_policy = self.config.get("categories", {})

    def classify_finding(self, finding: dict[str, Any]) -> dict[str, Any]:
        """
        Classify a finding according to policy.

        Adds:
        - automation_eligibility
        - risk_level
        - policy_decision_rationale
        """
        category = finding.get("category", "unknown")
        category_rules = self.category_policy.get(category, {})

        # Determine automation eligibility
        automation_eligibility = self._determine_automation_eligibility(finding, category_rules)

        # Determine risk level
        risk_level = self._determine_risk(finding, category_rules)

        # Build rationale
        rationale = self._build_rationale(finding, category_rules, automation_eligibility, risk_level)

        return {
            **finding,
            "automation_eligibility": automation_eligibility.value,
            "risk_level": risk_level.value,
            "policy_decision_rationale": rationale,
        }

    def _determine_automation_eligibility(
        self, finding: dict[str, Any], category_rules: dict[str, Any]
    ) -> AutomationEligibility:
        """Determine if a finding can be auto-remediated.

        HQ V1 Integration QA §14/§28 (authority firewall): `confidence` and
        `evidence_strength` are the LLM's own self-reported fields. This
        function must remain a monotonic DOWNGRADE-ONLY ratchet on those
        two inputs — the ceiling is always `category_rules`'s deterministic
        default (config the model has no influence over); a self-reported
        confidence/evidence_strength value may only ever push the result to
        a MORE restrictive tier (NEEDS_MORE_EVIDENCE), never to a less
        restrictive one. There is no code path here that raises eligibility
        above the category default, by design — an overconfident or
        prompt-injected model can lower its own authority but can never
        raise it. See test_policy_confidence_cannot_raise_eligibility.
        """

        # Start with category default
        default_eligibility = category_rules.get("automation_eligibility", "needs_signoff")
        eligibility = AutomationEligibility[default_eligibility.upper().replace("-", "_")]

        # Override if evidence is insufficient
        evidence_required = category_rules.get("evidence_required", "moderate")
        evidence_strength = finding.get("evidence_strength", "weak")
        if self._compare_strength(evidence_strength, evidence_required) < 0:
            return AutomationEligibility.NEEDS_MORE_EVIDENCE

        # Override if confidence is too low
        confidence = finding.get("confidence", 0.0)
        if confidence < 0.8 and eligibility in (AutomationEligibility.AUTO_APPLY, AutomationEligibility.AUTO_WITH_VERIFICATION):
            return AutomationEligibility.NEEDS_MORE_EVIDENCE

        return eligibility

    def _determine_risk(self, finding: dict[str, Any], category_rules: dict[str, Any]) -> RiskLevel:
        """Determine risk level of a finding."""
        risk_indicators = self.config.get("risk_assessment", {})

        # Check high-risk indicators
        for indicator in risk_indicators.get("high_risk_indicators", []):
            if self._matches_indicator(finding, indicator):
                return RiskLevel.HIGH

        # Check medium-risk indicators
        for indicator in risk_indicators.get("medium_risk_indicators", []):
            if self._matches_indicator(finding, indicator):
                return RiskLevel.MEDIUM

        # Default to severity field if present
        severity = finding.get("severity", "low")
        severity_map = {
            "critical": RiskLevel.CRITICAL,
            "high": RiskLevel.HIGH,
            "medium": RiskLevel.MEDIUM,
            "low": RiskLevel.LOW,
            "info": RiskLevel.LOW,
        }
        return severity_map.get(severity, RiskLevel.LOW)

    def _matches_indicator(self, finding: dict[str, Any], indicator: dict[str, Any]) -> bool:
        """Check if a finding matches a risk indicator."""
        for key, value in indicator.items():
            if key == "reason":
                continue  # reason is metadata, not a match criterion

            if key == "category":
                if finding.get("category") != value:
                    return False
            elif key == "severity":
                if finding.get("severity") != value:
                    return False
            elif key == "change_surface_files":
                # Parse "10+" format
                if value.endswith("+"):
                    threshold = int(value[:-1])
                    impact = finding.get("impact", {})
                    num_files = impact.get("affected_components", [])
                    if len(num_files) < threshold:
                        return False
            elif key == "reversibility":
                if finding.get("reversibility") != value:
                    return False
            # Add more matching logic as needed

        return True

    def _compare_strength(self, actual: str, required: str) -> int:
        """
        Compare evidence strength.

        Returns:
        - 1 if actual >= required
        - 0 if equal
        - -1 if actual < required
        """
        scale = {"weak": 0, "moderate": 1, "strong": 2, "conclusive": 3}
        actual_val = scale.get(actual, 0)
        required_val = scale.get(required, 0)

        if actual_val > required_val:
            return 1
        elif actual_val == required_val:
            return 0
        else:
            return -1

    def _build_rationale(
        self, finding: dict[str, Any], category_rules: dict[str, Any],
        automation_eligibility: AutomationEligibility, risk_level: RiskLevel
    ) -> str:
        """Build human-readable rationale for the classification."""
        parts = [
            f"Category: {finding.get('category')}",
            f"Evidence strength: {finding.get('evidence_strength')}",
            f"Confidence: {finding.get('confidence', 0.0):.2f}",
            f"Risk: {risk_level.value}",
            f"Automation: {automation_eligibility.value}",
        ]

        if automation_eligibility == AutomationEligibility.NEEDS_MORE_EVIDENCE:
            parts.append(f"Reason: Evidence insufficient (need {category_rules.get('evidence_required', 'strong')})")

        if category_rules.get("reason"):
            parts.append(f"Category reason: {category_rules['reason']}")

        return "; ".join(parts)

    def _load_policy(self, policy_file: Path) -> dict[str, Any]:
        """Load policy configuration from JSON (or YAML if available)."""
        # Try JSON first (stdlib), then YAML if available
        json_file = policy_file.parent / policy_file.stem / "policy.json"
        if json_file.exists():
            try:
                with json_file.open("r") as f:
                    config = json.load(f)
                log.info(f"Loaded policy from {json_file}")
                return config
            except Exception as exc:
                log.error(f"Failed to load policy: {exc}")

        # Fall back to YAML if available
        try:
            import yaml
            with policy_file.open("r") as f:
                config = yaml.safe_load(f)
            log.info(f"Loaded policy from {policy_file}")
            return config
        except ImportError:
            log.warning("PyYAML not available; policy loading will use defaults")
        except Exception as exc:
            log.error(f"Failed to load policy: {exc}")

        # Return minimal default policy
        return {"categories": {}}


def classify_findings(
    findings: list[dict[str, Any]], policy_file: Path
) -> list[dict[str, Any]]:
    """
    Classify a list of findings according to policy.

    Returns findings with added classification fields.
    """
    engine = PolicyEngine(policy_file)
    return [engine.classify_finding(f) for f in findings]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Test policy loading
    policy_file = Path("config/self_improvement_policy.yaml")
    if policy_file.exists():
        engine = PolicyEngine(policy_file)
        print(f"Loaded {len(engine.category_policy)} policy categories")
    else:
        print(f"Policy file not found: {policy_file}")
