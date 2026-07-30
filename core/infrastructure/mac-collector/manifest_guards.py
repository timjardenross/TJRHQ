"""File-type filtering and safety hard stops for `export-manifest`
(USS-TJR-MSN-0208).

Two independent layers, applied on top of `path_filters.PathFilter`:

1. `ExtensionFilter` — a whitelist. Only `DEFAULT_INCLUDE_EXTENSIONS` pass
   by default; `DEFAULT_EXCLUDE_EXTENSIONS` names the extensions this
   mission specifically exists to keep out of a bulk transfer (images,
   video, ebooks), documented explicitly rather than left as "whatever
   isn't in the include list" so the intent is visible in code and in
   `--help`. `--allow-ext` is the one sanctioned way to let a normally-
   blocked extension through for a specific run.

2. `check_hard_stops()` — a post-filter safety net, not a replacement for
   --include-path/--exclude-path/the extension whitelist. It re-inspects
   the FINAL candidate list (after both filters already ran) for the
   specific dangerous conditions this mission was written to prevent
   (the 415-file bulk-manifest mistake: Scoliosis Images, image/video/
   ebook files, an unbounded file count, an unbounded transfer size) and
   refuses to let export-manifest write a file if any are tripped. This
   catches the case those other filters were supposed to prevent but
   didn't — e.g. no --include-path given at all (so every folder,
   including Scoliosis Images, passes trivially), or --allow-ext used by
   mistake — rather than silently producing a manifest that looks fine at
   a glance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

DEFAULT_INCLUDE_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".xls",
}

DEFAULT_EXCLUDE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".mp4", ".mov", ".epub", ".mobi",
}

SCOLIOSIS_MARKER = "Scoliosis Images"


def _normalize_ext(ext: str) -> str:
    ext = ext.strip().lower()
    return ext if ext.startswith(".") else f".{ext}"


@dataclass
class ExtensionDecision:
    included: bool
    reason: str = ""


class ExtensionFilter:
    """Whitelist by extension, with an explicit opt-in escape hatch.

    A file's extension must be in `include` (default:
    DEFAULT_INCLUDE_EXTENSIONS) or in `allow` (extra extensions
    explicitly permitted for this run, e.g. via --allow-ext) to pass.
    Extensionless files never pass — a whitelist that admits "anything
    with no extension" would defeat the purpose of a whitelist.
    """

    def __init__(self, include=None, allow=None):
        self.include = {_normalize_ext(e) for e in (include or DEFAULT_INCLUDE_EXTENSIONS)}
        self.allow = {_normalize_ext(e) for e in (allow or [])}

    def decide(self, rel_posix: str) -> ExtensionDecision:
        suffix = PurePosixPath(rel_posix).suffix.lower()
        if not suffix:
            return ExtensionDecision(False, "no file extension")
        if suffix in self.include:
            return ExtensionDecision(True)
        if suffix in self.allow:
            return ExtensionDecision(True, f"extension '{suffix}' explicitly allowed via --allow-ext")
        return ExtensionDecision(False, f"extension '{suffix}' not in the default include list")


def _has_scoliosis_images(rel_posix: str) -> bool:
    return SCOLIOSIS_MARKER in PurePosixPath(rel_posix).parts


@dataclass
class HardStopResult:
    violations: list = field(default_factory=list)

    @property
    def stopped(self) -> bool:
        return bool(self.violations)


def check_hard_stops(
    files: list,
    *,
    max_files: int | None = None,
    max_total_bytes: int | None = None,
    allow_scoliosis_images: bool = False,
) -> HardStopResult:
    """Inspect a final candidate file list for the conditions this mission
    exists to prevent. `files` is a list of manifest entry dicts (each
    with at least `rel_path` and `size_bytes`)."""
    violations = []

    if not allow_scoliosis_images:
        scoliosis_hits = [f["rel_path"] for f in files if _has_scoliosis_images(f["rel_path"])]
        if scoliosis_hits:
            violations.append(
                f"{len(scoliosis_hits)} file(s) under 'Scoliosis Images' would be included "
                f"— pass --allow-scoliosis-images to proceed anyway. Examples: "
                f"{scoliosis_hits[:3]}"
            )

    blocked_ext_hits = [
        f["rel_path"] for f in files
        if PurePosixPath(f["rel_path"]).suffix.lower() in DEFAULT_EXCLUDE_EXTENSIONS
    ]
    if blocked_ext_hits:
        violations.append(
            f"{len(blocked_ext_hits)} image/video/ebook file(s) would be included "
            f"(extensions {sorted(DEFAULT_EXCLUDE_EXTENSIONS)}) — pass --allow-ext to allow "
            f"specific extensions. Examples: {blocked_ext_hits[:3]}"
        )

    if max_files is not None and len(files) > max_files:
        violations.append(
            f"manifest would include {len(files)} files, exceeding --max-files {max_files}"
        )

    total_bytes = sum(f["size_bytes"] for f in files)
    if max_total_bytes is not None and total_bytes > max_total_bytes:
        violations.append(
            f"manifest would total {total_bytes} bytes, exceeding --max-total-bytes {max_total_bytes}"
        )

    return HardStopResult(violations=violations)
