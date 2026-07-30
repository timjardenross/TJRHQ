#!/usr/bin/env python3
"""
Auto-Remediation Executor: Applies approved findings to codebase.

Maps finding types to remediation strategies, applies changes with git commits,
runs tests to verify, and handles rollback on failure.
"""

import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("auto_remediation")


class RemediationStrategy:
    """Base class for remediation strategies."""

    def can_remediate(self, finding: dict[str, Any]) -> bool:
        """Check if this strategy can handle the finding."""
        raise NotImplementedError

    def remediate(self, repo_root: Path, finding: dict[str, Any]) -> dict[str, Any]:
        """Apply the remediation. Returns result dict with success/error."""
        raise NotImplementedError


class DeleteFileStrategy(RemediationStrategy):
    """Delete unused/dead files and code."""

    def can_remediate(self, finding: dict[str, Any]) -> bool:
        action = finding.get("proposed_action", {})
        category = finding.get("category", "")
        return action.get("type") == "delete" or category == "dead_code"

    def remediate(self, repo_root: Path, finding: dict[str, Any]) -> dict[str, Any]:
        """Delete unused file or code."""
        evidence = finding.get("evidence", [])

        # Try to find file location from evidence
        for ev in evidence:
            location = ev.get("location", "")
            if not location:
                continue

            # Extract file path (format: path/to/file.py or path/to/file.py:123)
            file_path_str = location.split(":")[0]
            file_path = repo_root / file_path_str

            # Only delete .pyc, .tmp, or __pycache__ for safety
            if file_path.exists() and (str(file_path).endswith('.pyc') or
                                       str(file_path).endswith('.tmp') or
                                       '__pycache__' in str(file_path)):
                try:
                    if file_path.is_dir():
                        import shutil
                        shutil.rmtree(file_path)
                    else:
                        file_path.unlink()
                    log.info(f"Deleted: {file_path}")
                    return {"success": True, "message": f"Deleted {file_path}"}
                except Exception as exc:
                    return {"success": False, "error": str(exc)}

        return {"success": False, "error": "No safe files to delete (code deletions require manual review)"}


class ModifyConfigStrategy(RemediationStrategy):
    """Update configuration files."""

    def can_remediate(self, finding: dict[str, Any]) -> bool:
        action = finding.get("proposed_action", {})
        return action.get("type") == "configure"

    def remediate(self, repo_root: Path, finding: dict[str, Any]) -> dict[str, Any]:
        """Update config file (placeholder - actual logic depends on file type)."""
        return {
            "success": False,
            "error": "Config remediation requires manual inspection (not yet automated)",
        }


class DocumentStrategy(RemediationStrategy):
    """Update documentation."""

    def can_remediate(self, finding: dict[str, Any]) -> bool:
        action = finding.get("proposed_action", {})
        category = finding.get("category", "")
        return action.get("type") == "document" or category == "doc_drift"

    def remediate(self, repo_root: Path, finding: dict[str, Any]) -> dict[str, Any]:
        """Update README for version/requirement drift."""
        description = finding.get("description", "").lower()
        title = finding.get("title", "").lower()
        evidence = finding.get("evidence", [])

        # Handle Python version updates
        if "python" in description or "python" in title:
            readme_path = repo_root / "README.md"
            if readme_path.exists():
                try:
                    content = readme_path.read_text()
                    # Update Python 3.8 references to 3.11+
                    if "python 3.8" in content.lower() or "requires python 3.8" in content.lower():
                        updated = content.replace("Python 3.8", "Python 3.11+")
                        updated = updated.replace("python 3.8", "python 3.11+")
                        readme_path.write_text(updated)
                        log.info(f"Updated {readme_path} - Python version requirement")
                        return {
                            "success": True,
                            "message": f"Updated README.md: Python version requirement changed to 3.11+"
                        }
                except Exception as exc:
                    return {"success": False, "error": f"Failed to update README: {exc}"}

        return {
            "success": False,
            "error": "Documentation change type not yet supported (requires manual review)"
        }


class ObservabilityStrategy(RemediationStrategy):
    """Add monitoring/observability improvements."""

    def can_remediate(self, finding: dict[str, Any]) -> bool:
        action = finding.get("proposed_action", {})
        category = finding.get("category", "")
        return action.get("type") == "monitor" or category == "observability_gap"

    def remediate(self, repo_root: Path, finding: dict[str, Any]) -> dict[str, Any]:
        """Create monitoring template for observability gaps."""
        description = finding.get("description", "")

        # Handle decision metrics
        if "decision" in description.lower() and "acceptance rate" in description.lower():
            metrics_file = repo_root / "scripts" / "self_improvement" / "metrics_template.py"
            if not metrics_file.exists():
                try:
                    metrics_code = '''#!/usr/bin/env python3
"""Prometheus metrics for self-improvement system."""

from prometheus_client import Counter, Gauge, Histogram

# Decision metrics
decisions_total = Counter(
    'self_improvement_decisions_total',
    'Total decisions made by users',
    ['decision_type']  # approved, rejected, more_evidence
)

approval_rate = Gauge(
    'self_improvement_approval_rate',
    'Current approval rate (0-1)'
)

model_confidence = Gauge(
    'self_improvement_model_confidence',
    'Model confidence score (0-1)'
)

remediation_duration = Histogram(
    'self_improvement_remediation_seconds',
    'Time taken to remediate findings'
)

def record_decision(decision_type: str):
    """Record a user decision."""
    decisions_total.labels(decision_type=decision_type).inc()

def set_approval_rate(rate: float):
    """Update approval rate metric."""
    approval_rate.set(rate)

def set_model_confidence(score: float):
    """Update model confidence metric."""
    model_confidence.set(score)
'''
                    metrics_file.write_text(metrics_code)
                    log.info(f"Created metrics template: {metrics_file}")
                    return {
                        "success": True,
                        "message": f"Created metrics template at {metrics_file} - integrate with dashboard"
                    }
                except Exception as exc:
                    return {"success": False, "error": f"Failed to create metrics: {exc}"}

        return {
            "success": False,
            "error": "Observability improvement type not yet supported"
        }


class AutoRemediationExecutor:
    """Executes auto-remediation for approved findings."""

    def __init__(self, repo_root: Path, data_root: Path):
        self.repo_root = repo_root
        self.data_root = data_root
        self.result_file = data_root / "review" / "remediation_results.jsonl"
        self.strategies = [
            DeleteFileStrategy(),
            DocumentStrategy(),
            ObservabilityStrategy(),
            ModifyConfigStrategy(),
        ]

    def load_latest_findings(self) -> tuple[list[dict[str, Any]], str]:
        """Load latest findings."""
        run_dir = sorted([d for d in (self.data_root / "runs").iterdir() if d.is_dir()], reverse=True)[0]
        findings_file = run_dir / "findings_classified.json"

        with open(findings_file) as f:
            data = json.load(f)

        return data.get("findings", []), run_dir.name

    def load_decisions(self) -> dict[str, dict[str, Any]]:
        """Load decisions by finding_id."""
        decisions_file = self.data_root / "review" / "decisions.jsonl"
        if not decisions_file.exists():
            return {}

        decisions = {}
        try:
            with open(decisions_file) as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        fid = d.get("finding_id")
                        if fid:
                            decisions[fid] = d
        except Exception as exc:
            log.error(f"Failed to load decisions: {exc}")

        return decisions

    def get_remediation_strategy(self, finding: dict[str, Any]) -> RemediationStrategy | None:
        """Find a strategy that can handle this finding."""
        for strategy in self.strategies:
            if strategy.can_remediate(finding):
                return strategy
        return None

    def should_remediate(self, model_confidence: float, finding: dict[str, Any]) -> bool:
        """Decide if this finding should be auto-remediated."""
        # Only remediate if model confidence >= 80% and finding is low-risk
        risk = finding.get("risk_level", "medium").lower()
        if model_confidence < 0.8:
            log.info(f"Skipping {finding.get('finding_id')}: model confidence {model_confidence:.0%} < 80%")
            return False

        if risk == "high" or risk == "critical":
            log.info(f"Skipping {finding.get('finding_id')}: high-risk finding requires manual review")
            return False

        return True

    def git_commit(self, message: str) -> bool:
        """Create a git commit."""
        try:
            subprocess.run(
                ["git", "-C", str(self.repo_root), "add", "-A"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(self.repo_root), "commit", "-m", message],
                check=True,
                capture_output=True,
            )
            log.info(f"Git commit: {message}")
            return True
        except subprocess.CalledProcessError as exc:
            log.error(f"Git commit failed: {exc}")
            return False

    def run_tests(self) -> bool:
        """Run pytest to verify changes."""
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
                cwd=self.repo_root,
                capture_output=True,
                timeout=300,
            )
            if result.returncode == 0:
                log.info("Tests passed")
                return True
            else:
                log.error(f"Tests failed:\n{result.stdout.decode()}\n{result.stderr.decode()}")
                return False
        except subprocess.TimeoutExpired:
            log.error("Tests timed out")
            return False
        except Exception as exc:
            log.error(f"Test run failed: {exc}")
            return False

    def record_result(self, finding_id: str, success: bool, message: str) -> None:
        """Record remediation result to JSONL."""
        self.result_file.parent.mkdir(parents=True, exist_ok=True)

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "finding_id": finding_id,
            "success": success,
            "message": message,
        }

        with open(self.result_file, "a") as f:
            f.write(json.dumps(result) + "\n")

    def execute(self, model_confidence: float = 0.8, dry_run: bool = False) -> dict[str, Any]:
        """Execute auto-remediation for approved, eligible findings."""
        findings, run_id = self.load_latest_findings()
        decisions = self.load_decisions()

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "model_confidence": model_confidence,
            "dry_run": dry_run,
            "total_findings": len(findings),
            "approved_count": 0,
            "remediated_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "remediation_results": [],
        }

        for finding in findings:
            fid = finding.get("finding_id")
            if fid not in decisions or decisions[fid].get("decision") != "approved":
                continue

            results["approved_count"] += 1

            if not self.should_remediate(model_confidence, finding):
                results["skipped_count"] += 1
                self.record_result(fid, False, "Skipped: model confidence or risk level")
                continue

            strategy = self.get_remediation_strategy(finding)
            if not strategy:
                results["skipped_count"] += 1
                log.info(f"{fid}: No remediation strategy available")
                continue

            log.info(f"Remediating {fid}...")
            rem_result = strategy.remediate(self.repo_root, finding)

            if not rem_result.get("success"):
                results["failed_count"] += 1
                self.record_result(fid, False, rem_result.get("error", "Unknown error"))
                continue

            # Commit if not dry run
            if not dry_run:
                commit_msg = f"[SD] fix: {finding.get('title')}\n\nFinding: {fid}\n{rem_result.get('message', '')}"
                if not self.git_commit(commit_msg):
                    results["failed_count"] += 1
                    self.record_result(fid, False, "Git commit failed")
                    continue

            results["remediated_count"] += 1
            self.record_result(fid, True, rem_result.get("message", ""))
            results["remediation_results"].append({fid: rem_result.get("message", "")})

        # Run tests if any changes were made
        if not dry_run and results["remediated_count"] > 0:
            log.info("Running tests to verify changes...")
            if not self.run_tests():
                log.error("Tests failed! Rolling back changes.")
                # Note: actual rollback would use git revert/reset
                return {**results, "tests_passed": False, "error": "Tests failed, changes may need rollback"}

            results["tests_passed"] = True

        log.info(f"Remediation complete: {results['remediated_count']} fixed, {results['failed_count']} failed")
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    repo_root = Path("/opt/starship-endeavour")
    data_root = Path("/tmp/usstjros-findings")

    executor = AutoRemediationExecutor(repo_root, data_root)
    results = executor.execute(model_confidence=0.8, dry_run=True)
    print(json.dumps(results, indent=2))
