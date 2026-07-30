#!/usr/bin/env python3
"""JSON logging for collaborative specialist runtime."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid


ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs/collaboration"


def write_collaboration_log(payload: dict[str, Any]) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S-%f")
    collaboration_id = payload.get("collaboration_id") or f"COL-{timestamp}-{uuid.uuid4().hex[:8]}"
    path = LOG_DIR / f"{timestamp}-collaboration.json"
    safe_payload = {
        "collaboration_id": collaboration_id,
        "timestamp": now.isoformat(),
        **payload,
    }
    path.write_text(json.dumps(safe_payload, indent=2), encoding="utf-8")
    return path
