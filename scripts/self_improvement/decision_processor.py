#!/usr/bin/env python3
"""
Decision Processor: Analyzes user decisions from dashboard review.

Aggregates approval/rejection data, calculates confidence scores,
detects low-confidence models, and generates decision reports.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from typing import Any

log = logging.getLogger("decision_processor")


class DecisionProcessor:
    """Processes user decisions from decisions.jsonl."""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.decisions_file = data_root / "review" / "decisions.jsonl"
        self.report_file = data_root / "review" / "decision_report.json"

    def load_decisions(self) -> list[dict[str, Any]]:
        """Load all decisions from JSONL file."""
        if not self.decisions_file.exists():
            return []

        decisions = []
        try:
            with open(self.decisions_file) as f:
                for line in f:
                    if line.strip():
                        decisions.append(json.loads(line))
        except Exception as exc:
            log.error(f"Failed to load decisions: {exc}")
            return []

        return decisions

    def aggregate_decisions(self, decisions: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate decisions by category and verdict."""
        by_category = defaultdict(lambda: {"approved": 0, "rejected": 0, "more_evidence": 0, "total": 0})
        by_finding = {}

        for d in decisions:
            fid = d.get("finding_id")
            decision = d.get("decision")

            if not fid or not decision:
                continue

            # Store latest decision per finding
            by_finding[fid] = {
                "decision": decision,
                "reasoning": d.get("reasoning", ""),
                "timestamp": d.get("timestamp"),
            }

            # We need category from the finding itself; store for now
            by_category[fid][decision] += 1
            by_category[fid]["total"] += 1

        return {
            "by_finding": by_finding,
            "by_category": dict(by_category),
            "total_decisions": len(decisions),
        }

    def calculate_confidence_scores(self, findings: list[dict[str, Any]], decisions: dict[str, Any]) -> dict[str, float]:
        """Calculate confidence scores for each finding based on decisions."""
        scores = {}
        by_finding = decisions.get("by_finding", {})

        for finding in findings:
            fid = finding.get("finding_id")
            if fid not in by_finding:
                # No decision yet - neutral confidence
                scores[fid] = 0.5
                continue

            decision = by_finding[fid]["decision"]
            if decision == "approved":
                # Approved = high confidence
                scores[fid] = 0.95
            elif decision == "rejected":
                # Rejected = low confidence (model was wrong)
                scores[fid] = 0.1
            elif decision == "more_evidence":
                # More evidence = uncertain
                scores[fid] = 0.5

        return scores

    def calculate_model_confidence(self, decisions_agg: dict[str, Any]) -> float:
        """Calculate overall model confidence based on approval rate."""
        by_finding = decisions_agg.get("by_finding", {})
        if not by_finding:
            return 0.5  # No data yet

        approved_count = sum(1 for d in by_finding.values() if d["decision"] == "approved")
        rejected_count = sum(1 for d in by_finding.values() if d["decision"] == "rejected")

        total = approved_count + rejected_count
        if total == 0:
            return 0.5

        approval_rate = approved_count / total
        return approval_rate

    def generate_report(self, findings: list[dict[str, Any]], decisions_agg: dict[str, Any]) -> dict[str, Any]:
        """Generate decision analysis report."""
        model_confidence = self.calculate_model_confidence(decisions_agg)
        finding_scores = self.calculate_confidence_scores(findings, decisions_agg)

        by_finding = decisions_agg.get("by_finding", {})
        approved = [fid for fid, d in by_finding.items() if d["decision"] == "approved"]
        rejected = [fid for fid, d in by_finding.items() if d["decision"] == "rejected"]
        pending_evidence = [fid for fid, d in by_finding.items() if d["decision"] == "more_evidence"]

        # Findings ready for auto-remediation (approved + high confidence model)
        auto_remediation_eligible = [
            fid for fid in approved
            if model_confidence >= 0.8
        ]

        # Findings needing manual review (rejected or low confidence model)
        # Previously iterated the finding dicts themselves as "fid" and used
        # them directly as by_finding keys - never triggered because
        # classified_findings was always empty (the Phase 3 bug fixed
        # upstream), so this only crashed once real findings started flowing
        # through.
        manual_review_needed = [
            f.get("finding_id") for f in findings
            if f.get("finding_id") not in by_finding
            or by_finding.get(f.get("finding_id"), {}).get("decision") == "rejected"
        ]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_confidence": model_confidence,
            "model_confidence_rating": "high" if model_confidence >= 0.8 else "medium" if model_confidence >= 0.6 else "low",
            "total_decisions": decisions_agg.get("total_decisions", 0),
            "approved_count": len(approved),
            "rejected_count": len(rejected),
            "pending_evidence_count": len(pending_evidence),
            "approval_rate": len(approved) / (len(approved) + len(rejected)) if (len(approved) + len(rejected)) > 0 else 0,
            "auto_remediation_eligible": auto_remediation_eligible,
            "auto_remediation_eligible_count": len(auto_remediation_eligible),
            "manual_review_needed": manual_review_needed,
            "manual_review_count": len(manual_review_needed),
            "finding_scores": finding_scores,
            "recommendations": [
                f"Model confidence is {model_confidence:.0%} — {'safe for auto-remediation' if model_confidence >= 0.8 else 'recommend manual review before auto-fix'}",
                f"{len(approved)} findings approved, {len(rejected)} rejected, {len(pending_evidence)} pending evidence",
                f"{len(auto_remediation_eligible)} findings eligible for auto-remediation",
            ],
        }

    def process(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        """Process decisions and generate report."""
        decisions = self.load_decisions()
        decisions_agg = self.aggregate_decisions(decisions)
        report = self.generate_report(findings, decisions_agg)

        # Save report
        self.report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.report_file, "w") as f:
            json.dump(report, f, indent=2)

        log.info(f"Decision report saved: {self.report_file}")
        return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    from pathlib import Path
    DATA_ROOT = Path("/opt/starship-endeavour/data/self-improvement")

    processor = DecisionProcessor(DATA_ROOT)

    # Load sample findings (mtime sort, not name — see auto_remediation.py's
    # load_latest_findings() for why lexicographic sort is wrong here)
    run_dir = sorted(
        (d for d in (DATA_ROOT / "runs").iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime, reverse=True,
    )[0]
    findings_file = run_dir / "findings_classified.json"
    with open(findings_file) as f:
        data = json.load(f)

    report = processor.process(data.get("findings", []))
    print(json.dumps(report, indent=2))
