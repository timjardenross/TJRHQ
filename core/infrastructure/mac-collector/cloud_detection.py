"""Cloud-placeholder detection for the Mac File Collector Agent (USS-TJR-MSN-0206J-3).

MSN-0205E surfaced a real gap: OneDrive "Files On-Demand" and iCloud Drive
can leave a file's directory entry on disk without its content ever being
downloaded. The collector previously had no way to tell that apart from a
real file — it just hashed whatever bytes `open()` returned, which either
reads garbage/zero-byte data or silently triggers an OS-level download the
moment the file is touched. During that mission, 7 such placeholders had to
be identified and excluded by hand via ad-hoc symlink staging.

On macOS, a cloud-only placeholder (modern OneDrive/iCloud Files On-Demand)
has the SF_DATALESS bit set in `st_flags` — this is the same signal Finder
and `mdls` use to show the cloud-download badge, and it holds even though
the placeholder shares the real file's exact name (unlike the older iCloud
convention below). `st_flags` doesn't exist on Linux, so access is wrapped
with `getattr` to degrade gracefully off macOS.

The older iCloud Drive convention renames a not-yet-downloaded file to
`.{filename}.icloud` in the same directory. That pattern predates
Files On-Demand-style dataless files but still shows up on older syncs, so
it's checked as a secondary/fallback signal.
"""

from __future__ import annotations

import os
from pathlib import Path

SF_DATALESS = 0x40000000  # 1073741824 — macOS st_flags bit for cloud-only placeholders


def _has_icloud_placeholder(path: Path) -> bool:
    """True if `path`'s parent contains the older-style `.{name}.icloud` stub.

    Checked regardless of whether `path` itself exists on disk under its
    real name — a not-yet-downloaded file may only exist as the dot-prefixed
    placeholder.
    """
    icloud_stub = path.parent / f".{path.name}.icloud"
    return icloud_stub.exists()


def check_availability(path: Path) -> str:
    """Classify `path` as 'local', 'cloud_only', or 'unavailable'.

    - 'cloud_only': SF_DATALESS is set on the real file, or only the
      older-style `.{name}.icloud` placeholder exists.
    - 'unavailable': `os.stat()` failed (broken symlink, permission denied,
      vanished mid-scan, ...) and no `.icloud` placeholder was found either.
    - 'local': stats cleanly and isn't cloud-flagged.
    """
    try:
        stat_result = os.stat(path, follow_symlinks=False)
    except OSError:
        return "cloud_only" if _has_icloud_placeholder(path) else "unavailable"

    # st_flags doesn't exist on non-macOS platforms.
    st_flags = getattr(stat_result, "st_flags", 0)
    if st_flags & SF_DATALESS:
        return "cloud_only"

    if _has_icloud_placeholder(path):
        return "cloud_only"

    return "local"
