import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from mission_logger import redact_secrets

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_EVENT_LOG = BASE_DIR / "logs" / "runtime-events.jsonl"


@dataclass
class RuntimeEvent:
    event_type: str
    mission_id: str
    timestamp: str
    level: str
    stage: int
    message: str
    metadata: dict = field(default_factory=dict)
    duration_ms: Optional[int] = None


def redact_metadata(metadata: dict) -> dict:
    redacted = {}
    for key, value in metadata.items():
        if isinstance(value, str):
            redacted[key] = redact_secrets(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_secrets(item) if isinstance(item, str) else item
                for item in value
            ]
        elif isinstance(value, dict):
            redacted[key] = redact_metadata(value)
        else:
            redacted[key] = value
    return redacted


def emit(event: RuntimeEvent) -> None:
    try:
        RUNTIME_EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(event)
        payload["message"] = redact_secrets(payload["message"])
        payload["metadata"] = redact_metadata(payload["metadata"])
        with RUNTIME_EVENT_LOG.open("a", encoding="utf-8") as event_log:
            event_log.write(json.dumps(payload, sort_keys=True) + "\n")
    except Exception:
        pass


def emit_info(
    event_type: str,
    mission_id: str,
    message: str,
    metadata: dict = None,
    stage: int = 0,
    duration_ms: Optional[int] = None,
) -> None:
    emit(RuntimeEvent(
        event_type=event_type,
        mission_id=mission_id,
        timestamp=datetime.now().isoformat(),
        level="INFO",
        stage=stage,
        message=message,
        metadata=metadata or {},
        duration_ms=duration_ms,
    ))


def emit_error(
    event_type: str,
    mission_id: str,
    message: str,
    metadata: dict = None,
    stage: int = 0,
    duration_ms: Optional[int] = None,
) -> None:
    emit(RuntimeEvent(
        event_type=event_type,
        mission_id=mission_id,
        timestamp=datetime.now().isoformat(),
        level="ERROR",
        stage=stage,
        message=message,
        metadata=metadata or {},
        duration_ms=duration_ms,
    ))
