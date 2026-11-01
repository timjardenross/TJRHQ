"""Folder include/exclude filtering for `export-manifest` (USS-TJR-MSN-0207D).

Lets a curated manifest be scoped to specific top-level (or nested) folders
within a source, e.g. `--include-path "Operational Resilience/"`, without
requiring a full scan/config change per folder. Matching is by path
*component* prefix against the POSIX-style `rel_path` (relative to the
source root) — "Operational Resilience/" matches
"Operational Resilience/foo.pdf" but not "Operational Resilience 2/foo.pdf".
A bare filename-style pattern (no "/") is also matched against the file's
own name via fnmatch, so exclude filters can target extensions too, e.g.
`--exclude-path "*.mp4"`.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath


def _norm(prefix: str) -> str:
    return prefix.strip("/")


def path_matches(rel_posix: str, prefix: str) -> bool:
    prefix = _norm(prefix)
    if not prefix:
        return False
    if "/" not in prefix and "*" not in prefix and "?" not in prefix:
        # bare folder name / filename — allow it to match a path component
        # anywhere, not just at the root (e.g. "Transfer 1" or "*.mp4").
        rel = PurePosixPath(rel_posix)
        return prefix in rel.parts or fnmatch(rel.name, prefix)
    if "*" in prefix or "?" in prefix:
        return fnmatch(rel_posix, prefix) or fnmatch(PurePosixPath(rel_posix).name, prefix)
    parts = PurePosixPath(rel_posix).parts
    prefix_parts = PurePosixPath(prefix).parts
    return parts[: len(prefix_parts)] == prefix_parts


@dataclass
class PathFilterDecision:
    included: bool
    reason: str = ""


class PathFilter:
    """Applies `--include-path` / `--exclude-path` semantics to a rel_path.

    - No include patterns configured: everything passes the include stage.
    - One or more include patterns: rel_path must match at least one.
    - Exclude patterns are checked after include and always win.
    """

    def __init__(self, include=None, exclude=None):
        self.include = list(include or [])
        self.exclude = list(exclude or [])

    def decide(self, rel_posix: str) -> PathFilterDecision:
        for pattern in self.exclude:
            if path_matches(rel_posix, pattern):
                return PathFilterDecision(False, f"excluded by '{pattern}'")

        if not self.include:
            return PathFilterDecision(True)

        for pattern in self.include:
            if path_matches(rel_posix, pattern):
                return PathFilterDecision(True, f"included by '{pattern}'")

        return PathFilterDecision(False, "does not match any --include-path")
