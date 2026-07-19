"""Ignore-rule matching for the Mac File Collector Agent (USS-TJR-MSN-0205A).

Gitignore-lite semantics: patterns are matched with fnmatch against both the
POSIX-style path relative to the source root and the bare filename. A
pattern ending in "/**" ignores an entire directory subtree.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath


@dataclass
class IgnoreDecision:
    ignored: bool
    reason: str = ""


class IgnoreMatcher:
    def __init__(self, patterns, max_file_size_mb: float, ignore_hidden: bool):
        self._dir_patterns = []
        self._file_patterns = []
        for p in patterns:
            if p.endswith("/**"):
                self._dir_patterns.append(p[: -len("/**")])
            else:
                self._file_patterns.append(p)
        self.max_file_size_bytes = int(max_file_size_mb * 1024 * 1024)
        self.ignore_hidden = ignore_hidden

    def _is_hidden(self, rel_posix: str) -> bool:
        return any(part.startswith(".") for part in PurePosixPath(rel_posix).parts)

    def match(self, rel_posix: str, size_bytes: int = 0) -> IgnoreDecision:
        rel = PurePosixPath(rel_posix)
        name = rel.name

        for dir_pattern in self._dir_patterns:
            for i in range(len(rel.parts)):
                candidate = str(PurePosixPath(*rel.parts[: i + 1]))
                if fnmatch(candidate, dir_pattern):
                    return IgnoreDecision(True, f"matches directory rule '{dir_pattern}/**'")

        for pattern in self._file_patterns:
            if fnmatch(rel_posix, pattern) or fnmatch(name, pattern):
                return IgnoreDecision(True, f"matches pattern '{pattern}'")

        if self.ignore_hidden and self._is_hidden(rel_posix):
            return IgnoreDecision(True, "hidden file or directory")

        if size_bytes > self.max_file_size_bytes:
            mb = size_bytes / (1024 * 1024)
            return IgnoreDecision(True, f"exceeds max size ({mb:.1f}MB)")

        return IgnoreDecision(False)
