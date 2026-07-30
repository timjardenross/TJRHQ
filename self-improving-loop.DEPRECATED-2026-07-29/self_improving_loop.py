#!/usr/bin/env python3
"""
USS TJR Self-Improving Loop Orchestrator.

Main entry point for the self-improvement system. Coordinates evidence collection,
analysis, classification, review, and optional auto-remediation.

Usage:
    python scripts/self_improving_loop.py collect
    python scripts/self_improving_loop.py analyse
    python scripts/self_improving_loop.py classify
    python scripts/self_improving_loop.py review
    python scripts/self_improving_loop.py run [--dry-run]
    python scripts/self_improving_loop.py status
"""

import sys
import os
import json
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.self_improvement.collector import EvidenceCollector
from scripts.self_improvement.router_client import ModelRouterClient
from scripts.self_improvement.policy import classify_findings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("self-improvement")


class SelfImprovementOrchestrator:
    """Orchestrates the self-improvement workflow."""

    def __init__(self, repo_root: Path = None, dry_run: bool = False):
        self.repo_root = repo_root or self._find_repo_root()
        self.dry_run = dry_run
        self.run_id = self._generate_run_id()
        self.data_root = self.repo_root / "data/self-improvement"
        self.policy_file = self.repo_root / "config/self_improvement_policy.json"

        # Ensure data directories exist
        self._ensure_directories()

        self.collector = EvidenceCollector(self.repo_root)
        self.router = ModelRouterClient()
        self.evidence = None
        self.findings = None
        self.classified_findings = None

    def collect_evidence(self) -> dict:
        """Phase 1: Collect evidence."""
        log.info(f"[{self.run_id}] Collecting evidence...")
        self.evidence = self.collector.collect_all()
        self._save_artifact("evidence.json", self.evidence)
        log.info(f"[{self.run_id}] Collected evidence with {len(self.evidence)} sections")
        return self.evidence

    def analyse_evidence(self) -> list[dict]:
        """Phase 2: Analyse evidence → findings."""
        if not self.evidence:
            log.error("No evidence collected. Run collect first.")
            return []

        log.info(f"[{self.run_id}] Analysing evidence via Model Router...")

        if not self.router.health_check():
            log.error("Model Router not reachable. Cannot continue.")
            return []

        response = self.router.analyse_evidence(self.evidence)

        if not response.get("success"):
            log.error(f"Analysis failed: {response.get('error')}")
            return []

        findings = self._extract_findings_from_response(response)
        self.findings = findings
        self._save_artifact("findings_raw.json", findings)
        log.info(f"[{self.run_id}] Analysis produced {len(findings)} findings")
        return findings

    def classify_findings_internal(self) -> list[dict]:
        """Phase 3: Classify findings according to policy."""
        if not self.findings:
            log.error("No findings to classify. Run analyse first.")
            return []

        log.info(f"[{self.run_id}] Classifying {len(self.findings)} findings...")

        try:
            self.classified_findings = classify_findings(self.findings, self.policy_file)
            self._save_artifact("findings_classified.json", self.classified_findings)
            log.info(f"[{self.run_id}] Classification complete")
            return self.classified_findings
        except Exception as exc:
            log.error(f"Classification failed: {exc}")
            return []

    def generate_review_report(self) -> str:
        """Generate human-readable review report."""
        if not self.classified_findings:
            log.error("No classified findings. Run classify first.")
            return ""

        log.info(f"[{self.run_id}] Generating review report...")

        report_lines = [
            f"# Self-Improvement Review Report",
            f"",
            f"**Run ID:** {self.run_id}",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"**Repository:** {self.repo_root}",
            f"",
            f"## Summary",
            f"",
            f"- **Total findings:** {len(self.classified_findings)}",
        ]

        # Summary by automation eligibility
        by_eligibility = {}
        for f in self.classified_findings:
            elig = f.get("automation_eligibility", "unknown")
            by_eligibility[elig] = by_eligibility.get(elig, 0) + 1

        report_lines.append("- **By automation eligibility:**")
        for elig, count in sorted(by_eligibility.items()):
            report_lines.append(f"  - {elig}: {count}")

        report_lines.extend(["", "## Findings", ""])

        # Group by automation eligibility
        for elig in ["auto_apply", "auto_with_verification", "needs_signoff", "needs_more_evidence", "manual_only"]:
            findings_in_elig = [f for f in self.classified_findings if f.get("automation_eligibility") == elig]
            if not findings_in_elig:
                continue

            report_lines.append(f"### {elig.replace('_', ' ').title()}")
            report_lines.append("")

            for i, finding in enumerate(findings_in_elig, 1):
                report_lines.extend([
                    f"{i}. **{finding.get('title', 'Untitled')}**",
                    f"   - Category: `{finding.get('category')}`",
                    f"   - Severity: `{finding.get('severity')}`",
                    f"   - Risk: `{finding.get('risk_level', 'unknown')}`",
                    f"   - Confidence: {finding.get('confidence', 0.0):.2f}",
                    f"   - Description: {finding.get('description', 'N/A')}",
                    f"   - Action: {finding.get('proposed_action', {}).get('type', 'N/A')}",
                ])

                # Evidence summary
                evidence = finding.get("evidence", [])
                if evidence:
                    report_lines.append(f"   - Evidence:")
                    for ev in evidence[:3]:  # limit to 3
                        if isinstance(ev, dict):
                            report_lines.append(f"     - {ev.get('observation', 'N/A')} ({ev.get('type')})")
                        else:
                            report_lines.append(f"     - {ev}")
                    if len(evidence) > 3:
                        report_lines.append(f"     - ... and {len(evidence) - 3} more")

                report_lines.append("")

        report_lines.extend([
            "## Next Steps",
            "",
            "1. Review findings above",
            "2. Approve or reject each finding",
            "3. Run auto-remediation on approved findings (if applicable)",
            "4. Verify changes",
            ""
        ])

        report_text = "\n".join(report_lines)
        self._save_artifact("review.md", report_text, text=True)
        return report_text

    def run_full_cycle(self) -> int:
        """Run the full analysis cycle: collect → analyse → classify → review."""
        log.info(f"[{self.run_id}] Starting full cycle (dry_run={self.dry_run})...")

        try:
            self.collect_evidence()
            self.analyse_evidence()
            self.classify_findings_internal()
            report = self.generate_review_report()

            log.info(f"[{self.run_id}] Cycle complete. Review report generated.")
            print("\n" + report)

            return 0
        except Exception as exc:
            log.error(f"[{self.run_id}] Cycle failed: {exc}", exc_info=True)
            return 1

    def get_status(self) -> dict:
        """Get status of recent runs."""
        runs_dir = self.data_root / "runs"
        if not runs_dir.exists():
            return {"message": "No runs yet"}

        runs = sorted([d for d in runs_dir.iterdir() if d.is_dir()], reverse=True)[:5]
        status = []
        for run_dir in runs:
            evidence_file = run_dir / "evidence.json"
            findings_file = run_dir / "findings_classified.json"
            if evidence_file.exists():
                status.append({
                    "run_id": run_dir.name,
                    "has_evidence": evidence_file.exists(),
                    "has_findings": findings_file.exists(),
                })

        return {"recent_runs": status}

    def _find_repo_root(self) -> Path:
        """Find repository root."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        raise RuntimeError("Could not find git repository")

    def _generate_run_id(self) -> str:
        """Generate unique run ID."""
        now = datetime.now(timezone.utc)
        return f"r_{now.strftime('%Y%m%d')}_{now.microsecond // 10000:03d}"

    def _ensure_directories(self):
        """Ensure data directories exist."""
        (self.data_root / "runs" / self.run_id).mkdir(parents=True, exist_ok=True)
        (self.data_root / "review").mkdir(parents=True, exist_ok=True)

    def _save_artifact(self, name: str, data, text: bool = False) -> Path:
        """Save an artifact to the run directory."""
        path = self.data_root / "runs" / self.run_id / name
        try:
            if text:
                path.write_text(data)
            else:
                path.write_text(json.dumps(data, indent=2))
            log.debug(f"Saved {name} to {path}")
            return path
        except Exception as exc:
            log.error(f"Failed to save {name}: {exc}")
            return None

    def _extract_findings_from_response(self, response: dict) -> list[dict]:
        """Extract findings from Model Router response."""
        # The response should have a "response" field with JSON
        response_text = response.get("response", "")
        try:
            parsed = json.loads(response_text)
            return parsed.get("findings", [])
        except json.JSONDecodeError:
            log.error("Failed to parse Model Router response as JSON")
            return []


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Self-Improvement System Orchestrator")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["collect", "analyse", "classify", "review", "run", "status"],
                        help="Command to run")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no changes)")
    parser.add_argument("--repo", type=Path, help="Repository root (default: auto-detect)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        orchestrator = SelfImprovementOrchestrator(repo_root=args.repo, dry_run=args.dry_run)

        if args.command == "collect":
            orchestrator.collect_evidence()
        elif args.command == "analyse":
            orchestrator.analyse_evidence()
        elif args.command == "classify":
            orchestrator.classify_findings_internal()
        elif args.command == "review":
            orchestrator.generate_review_report()
        elif args.command == "run":
            return orchestrator.run_full_cycle()
        elif args.command == "status":
            status = orchestrator.get_status()
            print(json.dumps(status, indent=2))

        return 0
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        return 130
    except Exception as exc:
        log.error(f"Fatal error: {exc}", exc_info=args.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
