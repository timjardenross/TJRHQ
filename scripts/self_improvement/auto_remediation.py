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
                    return {"success": True, "mode": "direct", "message": f"Deleted {file_path}"}
                except Exception as exc:
                    return {"success": False, "error": str(exc)}

        return {"success": False, "error": "No safe files to delete (code deletions require manual review)"}


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
                            "mode": "direct",
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
                        "mode": "direct",
                        "message": f"Created metrics template at {metrics_file} - integrate with dashboard"
                    }
                except Exception as exc:
                    return {"success": False, "error": f"Failed to create metrics: {exc}"}

        return {
            "success": False,
            "error": "Observability improvement type not yet supported"
        }


class HandoffPRStrategy(RemediationStrategy):
    """Catch-all: hand any finding the narrower strategies above didn't claim
    to the same coding-agent pipeline the platform already uses for
    engineering handoffs (core.engineering.batch_coding), instead of a
    hardcoded per-category matcher that can never keep pace with finding
    variety. Council follow-up, 2026-08-29 ("how do we make this autonomous
    and cycle-based").

    Never commits to main. Writes an ENG-HANDOFF-*.md file describing the
    finding and shells out to platform-runtime/.venv (this venv has no
    mistralai) to run `batch_coding.py sync-one` on it, which — per its own
    docstring — writes generated files into a throwaway worktree and opens a
    **draft** GitHub PR for review. That's the platform's only existing
    precedent for AI-authored code changes; matching it here (confirmed with
    the Captain) rather than direct-committing, even though this path is
    gated to risk_level=low + automation_eligibility in (auto_apply,
    auto_with_verification) by should_remediate() before this class is ever
    reached. A hard fence against CI/CD config and anything credential-
    shaped lives in batch_coding._is_fenced_path, applied regardless of risk
    level.

    Only reached when nothing narrower claimed the finding first (registered
    last in AutoRemediationExecutor.strategies) - always True so a low-risk,
    high-eligibility finding never silently falls through with "no strategy
    available" the way it did before this class existed.
    """

    def can_remediate(self, finding: dict[str, Any]) -> bool:
        return True

    def remediate(self, repo_root: Path, finding: dict[str, Any]) -> dict[str, Any]:
        fid = finding.get("finding_id", "UNKNOWN")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        handoff_id = f"ENG-HANDOFF-SD-{fid}-{stamp}"
        handoffs_dir = repo_root / "Missions" / "Engineering-Handoffs"
        handoffs_dir.mkdir(parents=True, exist_ok=True)
        handoff_path = handoffs_dir / f"{handoff_id}.md"

        action = finding.get("proposed_action", {}) or {}
        evidence_lines = "\n".join(
            f"- {ev.get('observation', '')} (`{ev.get('location', '')}`)"
            for ev in finding.get("evidence", []) or []
        ) or "(none recorded)"

        handoff_path.write_text(
            f"- Status: APPROVED_FOR_ENGINEERING\n"
            f"- Batch Status: PENDING\n"
            f"- Mission ID: {handoff_id}\n"
            f"- Priority: P3\n"
            f"- Batch Group: Self-Improvement Engine\n"
            f"\n## Mission Title\n{finding.get('title', fid)}\n"
            f"\n## Summary\n{action.get('description') or finding.get('title', '')}\n"
            f"\n## Rationale\n"
            f"{finding.get('policy_decision_rationale', '')}\n\nEvidence:\n{evidence_lines}\n"
            f"\n## Suggested Next Step\n{action.get('description', 'See summary.')}\n"
            f"\n## Risks\n"
            f"Auto-generated by the self-improvement engine (risk_level="
            f"{finding.get('risk_level')}, automation_eligibility="
            f"{finding.get('automation_eligibility')}). Opened as a draft PR "
            f"only — review before merging, same as any other batch-coded "
            f"handoff.\n",
            encoding="utf-8",
        )

        venv_python = repo_root / "platform-runtime" / ".venv" / "bin" / "python"
        try:
            result = subprocess.run(
                [str(venv_python), "-m", "core.engineering.batch_coding", "sync-one",
                 "--handoff", str(handoff_path)],
                cwd=repo_root, capture_output=True, text=True, timeout=180,
            )
        except Exception as exc:
            return {"success": False, "error": f"sync-one subprocess failed: {exc}"}

        if result.returncode != 0:
            return {"success": False, "error": f"sync-one exited {result.returncode}: {result.stderr[-500:]}"}

        try:
            out = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"success": False, "error": f"sync-one produced unparseable output: {result.stdout[-500:]}"}

        if out.get("status") != "delivered":
            return {"success": False, "error": f"sync-one status={out.get('status')}: {out.get('error', '')}"}

        pr_url = out.get("pr_url") or ""
        return {
            "success": True,
            "mode": "pr",
            "message": (
                f"Draft PR opened for review: {pr_url}" if pr_url
                else f"Handoff coded (artifact: {out.get('artifact')}) but no PR opened "
                     f"(GitHub not configured or no new files to add) — review the artifact manually."
            ),
        }


class AutoRemediationExecutor:
    """Executes auto-remediation for approved findings."""

    def __init__(self, repo_root: Path, data_root: Path):
        self.repo_root = repo_root
        self.data_root = data_root
        self.result_file = data_root / "review" / "remediation_results.jsonl"
        # HandoffPRStrategy is the catch-all (always True) — must stay last,
        # so the narrower/free/direct strategies get first refusal.
        self.strategies = [
            DeleteFileStrategy(),
            DocumentStrategy(),
            ObservabilityStrategy(),
            HandoffPRStrategy(),
        ]

    def load_latest_findings(self) -> tuple[list[dict[str, Any]], str]:
        """Load latest findings.

        2026-08-29: was a lexicographic sort on directory name, same bug
        already found and fixed in dashboard.py's get_latest_run() - the
        persistent data root's old r_20260712_NNN-style dirs (mixed in from
        the /tmp migration) sort ahead of the new date-prefixed ones
        ('r' > '2' in ASCII), and that July dir has no
        findings_classified.json at all - crashed this exact way live while
        testing the autonomous-remediation changes. Independent copy of the
        same bug; fixed the same way (mtime, not name).
        """
        run_dir = sorted(
            (d for d in (self.data_root / "runs").iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime, reverse=True,
        )[0]
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
        """Decide if this finding should be auto-remediated.

        2026-08-29 (autonomous-remediation council, confirmed with the
        Captain): tightened from "anything not high/critical risk" to
        strictly risk_level == low, and added the automation_eligibility
        gate the classifier (policy.py) already computes but this method
        was previously ignoring entirely - a "low risk, needs more
        evidence" finding (the actual state of every finding seen so far)
        should NOT be auto-remediated just because its risk is low; the
        classifier's own evidence-strength judgment matters too.
        """
        risk = (finding.get("risk_level") or "medium").lower()
        eligibility = (finding.get("automation_eligibility") or "").lower()

        if model_confidence < 0.8:
            log.info(f"Skipping {finding.get('finding_id')}: model confidence {model_confidence:.0%} < 80%")
            return False

        if risk != "low":
            log.info(f"Skipping {finding.get('finding_id')}: risk_level={risk} (only 'low' auto-remediates)")
            return False

        if eligibility not in ("auto_apply", "auto_with_verification"):
            log.info(f"Skipping {finding.get('finding_id')}: automation_eligibility={eligibility!r} "
                     f"(needs auto_apply or auto_with_verification)")
            return False

        return True

    def git_commit(self, message: str) -> str | None:
        """Create a git commit. Returns the new commit sha, or None on failure."""
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
            sha = subprocess.run(
                ["git", "-C", str(self.repo_root), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            log.info(f"Git commit: {message} ({sha[:8]})")
            return sha
        except subprocess.CalledProcessError as exc:
            log.error(f"Git commit failed: {exc}")
            return None

    def git_revert(self, sha: str) -> bool:
        """Revert one commit by sha (creates a new commit, doesn't rewrite
        history) — the actual rollback that execute() previously only
        logged about doing. Reverts in reverse order (most recent first)
        so each revert applies cleanly against the current HEAD."""
        try:
            subprocess.run(
                ["git", "-C", str(self.repo_root), "revert", "--no-edit", sha],
                check=True, capture_output=True,
            )
            log.info(f"Reverted {sha[:8]}")
            return True
        except subprocess.CalledProcessError as exc:
            log.error(f"Revert of {sha[:8]} failed: {exc.stderr.decode(errors='replace') if exc.stderr else exc}")
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

    def _notify(self, results: dict[str, Any]) -> None:
        """Best-effort cycle summary to Slack/Telegram — an autonomous path
        that commits or opens PRs unattended must never do so silently.
        Self-contained import (matches heartbeat.py's own convention) so a
        notify failure can never break remediation itself."""
        if results["remediated_count"] == 0 and results["failed_count"] == 0:
            return
        try:
            import sys
            sys.path.insert(0, str(self.repo_root / "core" / "platform"))
            from notification_service import notify, Severity, Transport  # type: ignore

            lines = [f"Self-improvement auto-remediation cycle ({results['run_id']}):",
                     f"{results['remediated_count']} remediated, {results['failed_count']} failed, "
                     f"{results['skipped_count']} skipped."]
            for entry in results["remediation_results"]:
                for fid, msg in entry.items():
                    lines.append(f"• {fid}: {msg}")
            notify("\n".join(lines), severity=Severity.INFO, transport=Transport.SLACK)
        except Exception as exc:
            log.warning(f"Cycle-summary notify failed (non-fatal): {exc}")

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
        # (finding_id, sha) for every direct-mode commit this cycle, in
        # commit order — used for real rollback if tests fail afterward.
        direct_commits: list[tuple[str, str]] = []

        for finding in findings:
            fid = finding.get("finding_id")
            if fid not in decisions or decisions[fid].get("decision") != "approved":
                continue

            results["approved_count"] += 1

            if not self.should_remediate(model_confidence, finding):
                results["skipped_count"] += 1
                self.record_result(fid, False, "Skipped: model confidence, risk level, or automation eligibility")
                continue

            strategy = self.get_remediation_strategy(finding)
            if not strategy:
                results["skipped_count"] += 1
                log.info(f"{fid}: No remediation strategy available")
                continue

            if dry_run:
                # 2026-08-29: strategy.remediate() used to run unconditionally
                # even under --dry-run - harmless when the only strategies were
                # narrow local file writes, but HandoffPRStrategy shells out and
                # can open a real draft GitHub PR. --dry-run must mean "touch
                # nothing", so simulate without invoking remediate() at all.
                results["remediated_count"] += 1
                msg = f"[dry-run] would use {type(strategy).__name__}"
                self.record_result(fid, True, msg)
                results["remediation_results"].append({fid: msg})
                continue

            log.info(f"Remediating {fid}...")
            rem_result = strategy.remediate(self.repo_root, finding)

            if not rem_result.get("success"):
                results["failed_count"] += 1
                self.record_result(fid, False, rem_result.get("error", "Unknown error"))
                continue

            # Only "direct" mode (working-tree mutation, e.g. DeleteFileStrategy)
            # commits to main here. "pr" mode (HandoffPRStrategy) already
            # pushed to its own branch and opened a draft PR — committing
            # here too would double-apply the change directly to main,
            # defeating the whole point of the draft-PR review step.
            if not dry_run and rem_result.get("mode") == "direct":
                commit_msg = f"[SD] fix: {finding.get('title')}\n\nFinding: {fid}\n{rem_result.get('message', '')}"
                sha = self.git_commit(commit_msg)
                if not sha:
                    results["failed_count"] += 1
                    self.record_result(fid, False, "Git commit failed")
                    continue
                direct_commits.append((fid, sha))

            results["remediated_count"] += 1
            self.record_result(fid, True, rem_result.get("message", ""))
            results["remediation_results"].append({fid: rem_result.get("message", "")})

        # Run tests only if a *direct* commit happened — a "pr" mode result
        # never touched this working tree, nothing here to verify or revert.
        if not dry_run and direct_commits:
            log.info("Running tests to verify changes...")
            if not self.run_tests():
                log.error(f"Tests failed! Reverting {len(direct_commits)} direct commit(s) from this cycle.")
                reverted, revert_failed = [], []
                for fid, sha in reversed(direct_commits):
                    if self.git_revert(sha):
                        reverted.append(fid)
                        self.record_result(fid, False, f"Reverted after test failure ({sha[:8]})")
                    else:
                        revert_failed.append(fid)
                        self.record_result(fid, False, f"Test failure AND revert failed ({sha[:8]}) — manual intervention needed")
                results["tests_passed"] = False
                results["reverted"] = reverted
                results["revert_failed"] = revert_failed
                self._notify({**results, "remediated_count": 0, "failed_count": len(direct_commits),
                              "remediation_results": [{fid: "reverted (tests failed)"} for fid in reverted]})
                return {**results, "error": "Tests failed; direct-mode commits were reverted"
                                             + (f" ({len(revert_failed)} revert FAILED, needs manual fix)" if revert_failed else "")}

            results["tests_passed"] = True

        log.info(f"Remediation complete: {results['remediated_count']} fixed, {results['failed_count']} failed")
        if not dry_run:
            self._notify(results)
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    repo_root = Path("/opt/starship-endeavour")
    data_root = Path("/opt/starship-endeavour/data/self-improvement")

    executor = AutoRemediationExecutor(repo_root, data_root)
    results = executor.execute(model_confidence=0.8, dry_run=True)
    print(json.dumps(results, indent=2))
