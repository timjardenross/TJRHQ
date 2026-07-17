#!/usr/bin/env python3
"""
Self-Improvement Orchestrator: Coordinates the full improvement workflow.

1. Collect evidence from codebase
2. Analyze with model
3. Classify findings
4. Process user decisions
5. Auto-remediate if confident
6. Report results
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone

from collector import EvidenceCollector
from router_client import ModelRouterClient
from policy import PolicyEngine
from decision_processor import DecisionProcessor
from auto_remediation import AutoRemediationExecutor

log = logging.getLogger("orchestrator")


class SelfImprovementOrchestrator:
    """Orchestrates the full self-improvement workflow."""

    def __init__(self, repo_root: Path, data_root: Path, router_url: str = "http://127.0.0.1:8891"):
        self.repo_root = repo_root
        self.data_root = data_root
        self.router_url = router_url

        self.collector = EvidenceCollector(repo_root)
        self.router = ModelRouterClient(router_url)
        policy_file = repo_root / "config" / "self_improvement_policy.json"
        self.policy = PolicyEngine(policy_file)
        self.decision_processor = DecisionProcessor(data_root)
        self.executor = AutoRemediationExecutor(repo_root, data_root)

    def run_full_cycle(self, dry_run: bool = False, remediate: bool = True) -> dict:
        """Run the complete self-improvement cycle."""
        log.info("=" * 80)
        log.info("SELF-IMPROVEMENT CYCLE START")
        log.info("=" * 80)

        # Every run needs its own runs/<run_id>/ directory - previously
        # nothing ever wrote one after the initial 2026-07-12 run, so
        # dashboard.py and AutoRemediationExecutor.load_latest_findings()
        # (both of which just pick the newest runs/ subdirectory) kept
        # reprocessing that same stale batch regardless of what a given
        # day's analysis/classification actually produced.
        run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
        run_dir = self.data_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Phase 1: Collect evidence
        log.info("\nPhase 1: Collecting evidence...")
        evidence = self.collector.collect_all()
        log.info(f"Collected {len(evidence)} evidence sections")
        with open(run_dir / "evidence.json", "w") as f:
            json.dump(evidence, f, indent=2, default=str)

        # Phase 2: Analyze with model
        log.info("\nPhase 2: Analyzing evidence...")
        if not self.router.health_check():
            log.error("Model Router unreachable - stopping")
            return {"success": False, "error": "Model Router unavailable"}

        analysis_result = self.router.analyse_evidence(evidence)
        if not analysis_result.get("success"):
            log.error(f"Analysis failed: {analysis_result.get('error')}")
            return {"success": False, "error": analysis_result.get("error")}

        findings = analysis_result.get("findings", [])
        log.info(f"Analysis produced {len(findings)} findings")
        with open(run_dir / "findings_raw.json", "w") as f:
            json.dump({"findings": findings}, f, indent=2)

        # Phase 3: Classify findings
        #
        # classify_finding() returns {**finding, automation_eligibility,
        # risk_level, policy_decision_rationale} - it never raises for a
        # structurally reasonable finding and never returns "valid"/
        # "reason"/"finding" keys. The old check here (result.get("valid"))
        # was reading keys that never existed, so every finding landed in
        # errors regardless of evidence quality - the actual reason
        # classification always showed "0 valid" before this fix, separate
        # from (and on top of) the router "findings" key bug fixed earlier.
        #
        # The model's schema also never asks for finding_id, but
        # decision_processor.py and auto_remediation.py both key off it -
        # assign one here so decisions persist against something stable.
        log.info("\nPhase 3: Classifying findings...")
        classified_findings = []
        errors = []
        for i, finding in enumerate(findings):
            finding.setdefault("finding_id", f"FND-{i + 1:03d}")
            try:
                classified_findings.append(self.policy.classify_finding(finding))
            except Exception as exc:
                errors.append({"finding_id": finding.get("finding_id"), "error": str(exc)})
        log.info(f"Classified: {len(classified_findings)} valid, {len(errors)} errors")
        with open(run_dir / "findings_classified.json", "w") as f:
            json.dump({"findings": classified_findings, "errors": errors}, f, indent=2)

        # Phase 4: Process decisions
        log.info("\nPhase 4: Processing user decisions...")
        decision_report = self.decision_processor.process(classified_findings)
        log.info(f"Decision report: {decision_report['total_decisions']} decisions")
        log.info(f"Model confidence: {decision_report['model_confidence']:.0%}")
        log.info(f"Auto-remediation eligible: {decision_report['auto_remediation_eligible_count']} findings")

        # Phase 5: Auto-remediation (if enabled and confident)
        remediation_result = {"skipped": True}
        if remediate and decision_report["model_confidence"] >= 0.75:
            log.info("\nPhase 5: Auto-remediating approved findings...")
            remediation_result = self.executor.execute(
                model_confidence=decision_report["model_confidence"],
                dry_run=dry_run,
            )
            log.info(f"Remediation: {remediation_result['remediated_count']} applied, {remediation_result['failed_count']} failed")
        else:
            log.info("\nPhase 5: Skipped (model confidence too low or remediation disabled)")

        # Summary
        log.info("\n" + "=" * 80)
        log.info("SELF-IMPROVEMENT CYCLE COMPLETE")
        log.info("=" * 80)

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "success": True,
            "evidence_collected": len(evidence),
            "findings_analyzed": len(findings),
            "findings_classified": len(classified_findings),
            "findings_errors": len(errors),
            "decisions_processed": decision_report["total_decisions"],
            "model_confidence": decision_report["model_confidence"],
            "auto_remediation_eligible": decision_report["auto_remediation_eligible_count"],
            "auto_remediation": remediation_result,
            "decision_report": decision_report,
            "recommendations": decision_report.get("recommendations", []),
        }

        # Save summary
        summary_file = self.data_root / "review" / "cycle_summary.json"
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        log.info(f"\nSummary saved: {summary_file}")
        return summary


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run self-improvement cycle")
    parser.add_argument("--repo-root", type=Path, default=Path("/root/USSTJROS"), help="Repository root")
    parser.add_argument("--data-root", type=Path, default=Path("/tmp/usstjros-findings"), help="Data directory")
    parser.add_argument("--router-url", default="http://127.0.0.1:8891", help="Model Router URL")
    parser.add_argument("--dry-run", action="store_true", help="Don't apply changes")
    parser.add_argument("--no-remediate", action="store_true", help="Skip auto-remediation")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    orchestrator = SelfImprovementOrchestrator(
        repo_root=args.repo_root,
        data_root=args.data_root,
        router_url=args.router_url,
    )

    result = orchestrator.run_full_cycle(
        dry_run=args.dry_run,
        remediate=not args.no_remediate,
    )

    # Print summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(json.dumps(result, indent=2, default=str))

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
