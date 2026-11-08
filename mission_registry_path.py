"""Single resolver for the mission registry file (mission-index.txt).

Every consumer and writer of the registry must obtain its path from
``registry_path()`` instead of building the path itself.

Resolution order:

1. ``MISSION_REGISTRY_PATH`` environment variable, when set and non-empty.
   It must be an absolute path; a relative value raises ``ValueError`` so that
   the result never depends on the process working directory.
2. The tracked checkout path. This is the TEMPORARY default. It stays in place
   until the external registry has been verified in production and the
   tracked file is removed (see the migration plan in the PR description).

Changing the default is a separate, later step; this module only adds the
override hook.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "MISSION_REGISTRY_PATH"

REPO_ROOT = Path(__file__).resolve().parent
TRACKED_DEFAULT = REPO_ROOT / "core" / "mission-control" / "registry" / "mission-index.txt"


class MissionRegistryError(OSError):
    """The registry file is missing, is not a regular file, or cannot be read."""


def registry_path() -> Path:
    """Return the path of the mission registry file for this process."""
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        return TRACKED_DEFAULT
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ValueError(f"{ENV_VAR} must be an absolute path")
    return candidate


def read_registry_text(path: Path | None = None) -> str:
    """Return the registry text, or raise ``MissionRegistryError``.

    Missing, non-regular, and undecodable files all raise the same error type,
    so callers can handle one exception for "registry not usable".
    """
    target = path if path is not None else registry_path()
    if not target.is_file():
        raise MissionRegistryError(f"mission registry missing or not a regular file: {target}")
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MissionRegistryError(f"mission registry unreadable: {target} ({exc.__class__.__name__})") from exc
