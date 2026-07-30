"""
Writes engineering router outputs to the evidence folder with full audit metadata.

Evidence file naming: <mission_id>_<mode>_<backend>_<timestamp>.json
Every file includes: mission_id, mode, backend, model, timestamp, prompt, response.
No repository files are mutated here.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from .schemas import RouterResponse

log = logging.getLogger(__name__)

_EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def write(response: RouterResponse, evidence_dir: Path | None = None) -> Path:
    """
    Persist a RouterResponse to the evidence folder as JSON.

    Returns the path of the written file.
    Does NOT raise — logs a warning and returns a sentinel path on failure.
    """
    target_dir = evidence_dir or _EVIDENCE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{_safe_id(response.mission_id)}_{response.mode}_{_safe_id(response.backend)}_{ts}.json"
    out_path = target_dir / filename

    try:
        out_path.write_text(response.to_json(), encoding="utf-8")
        log.info("[output_writer] saved evidence → %s", out_path)
    except Exception as exc:
        log.warning("[output_writer] failed to write evidence: %s", exc)

    return out_path


def list_evidence(mission_id: str | None = None, evidence_dir: Path | None = None) -> list[Path]:
    """List evidence files, optionally filtered by mission_id prefix."""
    target_dir = evidence_dir or _EVIDENCE_DIR
    if not target_dir.exists():
        return []
    files = sorted(target_dir.glob("*.json"), reverse=True)
    if mission_id:
        safe = _safe_id(mission_id)
        files = [f for f in files if f.name.startswith(safe)]
    return files
