"""
Deterministic evidence collection for self-improvement analysis.

Gathers facts about:
- Repository state (branch, commit, dirty)
- Recent changes (git log, affected files)
- Code structure (files, tests, references)
- Configuration and infrastructure
- Service state and logs
- Model Router status

Does not infer or guess — only collects observable facts.
"""

import json
import logging
import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("collector")


class RepositoryState:
    """Collects git and working-tree state."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def collect(self) -> dict[str, Any]:
        """Gather repository state."""
        return {
            "branch": self._get_branch(),
            "commit": self._get_commit(),
            "commit_message": self._get_commit_message(),
            "dirty": self._is_dirty(),
            "uncommitted_files": self._get_uncommitted_files(),
            "repo_root": str(self.repo_root),
        }

    def _get_branch(self) -> Optional[str]:
        """Get current branch name."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as exc:
            log.warning(f"Failed to get branch: {exc}")
            return None

    def _get_commit(self) -> Optional[str]:
        """Get current commit hash."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_root), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as exc:
            log.warning(f"Failed to get commit: {exc}")
            return None

    def _get_commit_message(self) -> Optional[str]:
        """Get commit message of HEAD."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_root), "log", "-1", "--format=%B"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as exc:
            log.warning(f"Failed to get commit message: {exc}")
            return None

    def _is_dirty(self) -> bool:
        """Check if working tree has uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_root), "status", "--porcelain"],
                capture_output=True, text=True, timeout=5
            )
            return bool(result.stdout.strip()) if result.returncode == 0 else None
        except Exception as exc:
            log.warning(f"Failed to check dirty status: {exc}")
            return None

    def _get_uncommitted_files(self) -> list[str]:
        """Get list of uncommitted files."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_root), "status", "--porcelain"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return []
            files = []
            for line in result.stdout.splitlines():
                if line.strip():
                    # Format: "XY filename"
                    parts = line.split(None, 1)
                    if len(parts) > 1:
                        files.append(parts[1])
            return files
        except Exception as exc:
            log.warning(f"Failed to get uncommitted files: {exc}")
            return []


class FileSystemAudit:
    """Audits the file system for structure and content."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def collect(self) -> dict[str, Any]:
        """Gather file system state."""
        return {
            "python_files": self._count_python_files(),
            "test_files": self._find_test_files(),
            "doc_files": self._find_doc_files(),
            "config_files": self._find_config_files(),
            "schema_files": self._find_schema_files(),
            "missing_directories": self._check_required_directories(),
        }

    def _count_python_files(self) -> int:
        """Count .py files in repo."""
        try:
            result = subprocess.run(
                ["find", str(self.repo_root), "-name", "*.py", "-type", "f"],
                capture_output=True, text=True, timeout=10
            )
            return len(result.stdout.strip().splitlines()) if result.returncode == 0 else 0
        except Exception as exc:
            log.warning(f"Failed to count Python files: {exc}")
            return 0

    def _find_test_files(self) -> list[str]:
        """Find test files."""
        test_dir = self.repo_root / "tests"
        if not test_dir.exists():
            return []
        return [f.name for f in test_dir.glob("test_*.py")]

    def _find_doc_files(self) -> list[str]:
        """Find documentation files."""
        docs = []
        for pattern in ["*.md", "docs/**/*.md", "**/*.md"]:
            for f in self.repo_root.glob(pattern):
                if f.is_file():
                    docs.append(str(f.relative_to(self.repo_root)))
        return list(set(docs))  # dedup

    def _find_config_files(self) -> list[str]:
        """Find configuration files."""
        configs = []
        for pattern in ["*.yaml", "*.yml", "*.json", "config/**/*", "core/infrastructure/**/*.yaml"]:
            for f in self.repo_root.glob(pattern):
                if f.is_file() and not f.name.startswith("."):
                    configs.append(str(f.relative_to(self.repo_root)))
        return list(set(configs))  # dedup

    def _find_schema_files(self) -> list[str]:
        """Find schema files."""
        schemas = []
        schema_dir = self.repo_root / "schemas"
        if schema_dir.exists():
            for f in schema_dir.glob("*.json"):
                schemas.append(f.name)
        return schemas

    def _check_required_directories(self) -> list[str]:
        """Check for required directories that are missing."""
        required = ["data/self-improvement", "core/model-router"]
        missing = []
        for req in required:
            if not (self.repo_root / req).exists():
                missing.append(req)
        return missing


class ModelRouterAudit:
    """Audits Model Router configuration and status."""

    def __init__(self, repo_root: Path, router_url: str = "http://127.0.0.1:8891"):
        self.repo_root = repo_root
        self.router_url = router_url

    def collect(self) -> dict[str, Any]:
        """Gather Model Router state."""
        return {
            "configured_routes": self._read_router_code(),
            "router_reachable": self._check_router_health(),
            "router_status": self._get_router_status(),
            "call_log_exists": self._check_call_log(),
            "call_log_size_mb": self._get_call_log_size(),
        }

    def _read_router_code(self) -> dict[str, Any]:
        """Extract task types from router code."""
        router_file = self.repo_root / "core/model-router/app.py"
        if not router_file.exists():
            return {"error": "router file not found"}

        try:
            content = router_file.read_text()
            task_types = {}
            # Extract TASK_POLICY dict keys
            match = re.search(r'TASK_POLICY:\s*dict\[str,\s*dict\[str,\s*Any\]\]\s*=\s*\{(.*?)\n\}', content, re.DOTALL)
            if match:
                policy_content = match.group(1)
                for line in policy_content.split('\n'):
                    line = line.strip()
                    if line.startswith('"') and ':' in line:
                        key = line.split('"')[1]
                        task_types[key] = True
            return {"task_types": list(task_types.keys()), "count": len(task_types)}
        except Exception as exc:
            log.warning(f"Failed to read router code: {exc}")
            return {"error": str(exc)}

    def _check_router_health(self) -> bool:
        """Check if Model Router is reachable."""
        try:
            import urllib.request
            response = urllib.request.urlopen(f"{self.router_url}/health", timeout=2)
            return response.status == 200
        except Exception:
            return False

    def _get_router_status(self) -> dict[str, Any]:
        """Get status from Model Router."""
        try:
            import urllib.request
            response = urllib.request.urlopen(f"{self.router_url}/api/model/status", timeout=5)
            return json.loads(response.read().decode())
        except Exception as exc:
            return {"error": str(exc)}

    def _check_call_log(self) -> bool:
        """Check if call_log.jsonl exists."""
        log_file = self.repo_root / "core/model-router/call_log.jsonl"
        return log_file.exists()

    def _get_call_log_size(self) -> Optional[float]:
        """Get size of call_log.jsonl in MB."""
        log_file = self.repo_root / "core/model-router/call_log.jsonl"
        if not log_file.exists():
            return None
        return log_file.stat().st_size / (1024 * 1024)


class CodeAnalysis:
    """Analyzes code for common patterns (TODOs, hardcoded values, etc.)."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def collect(self) -> dict[str, Any]:
        """Gather code analysis."""
        return {
            "todos_and_fixmes": self._find_todos(),
            "dead_imports": self._find_unused_imports_sample(),
            "hardcoded_values": self._find_hardcoded_patterns(),
        }

    def _find_todos(self) -> dict[str, list[str]]:
        """Find TODO and FIXME comments in code."""
        todos = {}
        patterns = [
            (r"# TODO.*", "TODO"),
            (r"# FIXME.*", "FIXME"),
        ]
        try:
            for pattern, label in patterns:
                result = subprocess.run(
                    ["grep", "-r", pattern, str(self.repo_root), "--include=*.py"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout:
                    todos[label] = result.stdout.strip().split('\n')[:10]  # limit to 10
            return todos
        except Exception as exc:
            log.warning(f"Failed to find TODOs: {exc}")
            return {}

    def _find_unused_imports_sample(self) -> list[str]:
        """Sample check for common unused import patterns."""
        # This is a light check, not comprehensive
        try:
            result = subprocess.run(
                ["grep", "-r", "^import .*#.*unused", str(self.repo_root), "--include=*.py"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip().split('\n')[:5]
            return []
        except Exception:
            return []

    def _find_hardcoded_patterns(self) -> list[str]:
        """Find potential hardcoded values."""
        patterns = [
            r"url.*=.*['\"]https?://.*['\"]",
            r"api_key.*=.*['\"][a-zA-Z0-9]+['\"]",
            r"password.*=.*['\"][^'\"]*['\"]",
        ]
        findings = []
        for pattern in patterns:
            try:
                result = subprocess.run(
                    ["grep", "-r", "-E", pattern, str(self.repo_root), "--include=*.py"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout:
                    # Limit to a few examples
                    for line in result.stdout.strip().split('\n')[:2]:
                        if line:
                            findings.append(line)
            except Exception:
                pass
        return findings[:10]  # limit overall


class EvidenceCollector:
    """Orchestrates all evidence collection."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or self._find_repo_root()

    def collect_all(self, since_commit: Optional[str] = None) -> dict[str, Any]:
        """Collect all available evidence."""
        log.info(f"Collecting evidence from {self.repo_root}")

        collection_start = datetime.now(timezone.utc)

        return {
            "collection_timestamp": collection_start.isoformat(),
            "repository_state": RepositoryState(self.repo_root).collect(),
            "filesystem_audit": FileSystemAudit(self.repo_root).collect(),
            "model_router_audit": ModelRouterAudit(self.repo_root).collect(),
            "code_analysis": CodeAnalysis(self.repo_root).collect(),
            "evidence_window": {
                "since_commit": since_commit,
                "collection_timestamp": collection_start.isoformat(),
            },
            "collection_duration_ms": int((datetime.now(timezone.utc) - collection_start).total_seconds() * 1000),
        }

    def _find_repo_root(self) -> Path:
        """Find the repository root by looking for .git."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        raise RuntimeError(f"Could not find git repository root from {Path.cwd()}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    collector = EvidenceCollector()
    evidence = collector.collect_all()
    print(json.dumps(evidence, indent=2))
