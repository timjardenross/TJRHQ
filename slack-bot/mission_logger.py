import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
import id_registry
MISSIONS_DIR = BASE_DIR / "Missions"
MISSION_INDEX = MISSIONS_DIR / "Mission-Index.md"
# MSN-0145: authoritative runtime registry sink
_CANONICAL_REGISTRY = BASE_DIR / "core" / "mission-control" / "registry" / "mission-index.txt"

MISSION_HISTORY_TRIGGERS = [
    "recent missions",
    "mission history",
    "completed missions",
    "what missions",
    "show missions",
    "mission log",
]

SECRET_ENV_KEYS = [
    "OPENAI_API_KEY",
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
]


def ensure_missions_dir() -> Path:
    MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    # MSN-BOT-SOR: Mission-Index.md is export/cache only. Do not initialise it as a
    # data source. File creation is skipped — Supabase is the system of record.
    return MISSIONS_DIR


def _append_runtime_to_canonical_registry(
    mission_id: str,
    title: str,
    domain: str,
    status: str,
) -> None:
    """MSN-0145: append a runtime mission row to the authoritative registry.

    Uses the same dash-list format as mission_registry.append_canonical_registry().
    Non-blocking — file write failures are silently suppressed.
    """
    if not _CANONICAL_REGISTRY.exists():
        return
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        with _CANONICAL_REGISTRY.open("a", encoding="utf-8") as f:
            f.write(f"\n- {mission_id} | {ts} | {domain} | {status} | {redact_secrets(title)}\n")
    except Exception:
        pass


def generate_mission_id() -> str:
    return id_registry.next_id("MSN")


def is_mission_history_request(user_text: str) -> bool:
    text = user_text.lower()
    return any(trigger in text for trigger in MISSION_HISTORY_TRIGGERS)


def redact_secrets(value: str) -> str:
    redacted = value

    for key in SECRET_ENV_KEYS:
        secret = os.getenv(key)
        if secret and len(secret) > 4:
            redacted = redacted.replace(secret, f"[REDACTED {key}]")

    return redacted


def build_title(user_request: str) -> str:
    cleaned = re.sub(r"<@[^>]+>", "", user_request).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80] or "Commander TJR Mission"


def save_mission_log(
    mission_id: str,
    user_request: str,
    commander_response: str,
    mission_domain: str,
    assigned_specialists: list,
    priority: str,
    status: str,
) -> Path:
    ensure_missions_dir()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_request = redact_secrets(user_request)
    safe_response = redact_secrets(commander_response)
    specialists = ", ".join(assigned_specialists)

    mission_file = MISSIONS_DIR / f"{mission_id}.md"
    mission_file.write_text(
        f"""# Mission Log

## Metadata

Mission ID: {mission_id}

Timestamp: {timestamp}

Mission Domain: {mission_domain}

Assigned Specialists: {specialists}

Priority: {priority}

Status: {status}

Source: Slack

## User Request

{safe_request}

## Commander Response

{safe_response}

## Notes

Optional future notes.
""",
        encoding="utf-8",
    )

    update_mission_index(
        mission_id=mission_id,
        mission_domain=mission_domain,
        status=status,
        title=build_title(user_request),
    )

    # MSN-BOT-SOR: Supabase is authoritative; file registry is cache/export only
    _supabase_insert_mission(
        mission_id=mission_id,
        title=build_title(user_request),
        domain=mission_domain,
        status=status,
    )
    # MSN-0145: also append to canonical registry file (cache/export, non-authoritative)
    _append_runtime_to_canonical_registry(
        mission_id=mission_id,
        title=build_title(user_request),
        domain=mission_domain,
        status=status,
    )

    # MSN-0040A: Log mission to Command Memory
    try:
        from commands.mission_to_memory import save_mission_after_creation
        save_mission_after_creation(
            mission_id=mission_id,
            title=build_title(user_request),
            user_id="slack-bot",  # Will be replaced by actual user_id when available
        )
    except Exception as e:
        log.error("[mission-logger] Failed to save to Command Memory: %s", e)
        # Non-blocking failure — mission still created locally

    return mission_file


def update_mission_index(
    mission_id: str,
    mission_domain: str,
    status: str,
    title: str,
) -> None:
    # MSN-BOT-SOR: deprecated — mission-index.txt is no longer authoritative.
    # Supabase is now written directly via _supabase_insert_mission().
    # This stub is retained to avoid breaking callers during migration.
    log.warning(
        "[mission-logger] DEPRECATED: update_mission_index() called for %s. "
        "mission-index.txt is not authoritative. Write to Supabase instead.",
        mission_id,
    )


def _supabase_insert_mission(
    mission_id: str,
    title: str,
    domain: str,
    status: str,
) -> None:
    """Insert or upsert a mission row into the Supabase missions table."""
    try:
        sys.path.insert(0, str(_BASE_DIR / "tools" / "supabase"))
        from client import CommanderSupabaseClient
        client = CommanderSupabaseClient()
        if not client.is_enabled():
            return
        payload = {
            "id": mission_id,
            "title": title,
            "domain": domain,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        client.insert("missions", payload)
    except Exception as exc:
        log.debug("[mission-logger] Supabase mission insert failed: %s", exc)


def load_recent_missions(limit: int = 5) -> str:
    ensure_missions_dir()

    lines = [
        line.strip()
        for line in MISSION_INDEX.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("- ")
    ]

    if not lines:
        return "No completed missions have been logged yet."

    recent = lines[-limit:]

    return "\n".join(
        [
            "# RECENT MISSIONS",
            "",
            *recent,
        ]
    )
