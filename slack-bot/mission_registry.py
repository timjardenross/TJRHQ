import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from mission_logger import (
    MISSION_INDEX,
    MISSIONS_DIR,
    build_title,
    ensure_missions_dir,
    generate_mission_id,
    redact_secrets,
    update_mission_index,
)

BASE_DIR = Path(__file__).resolve().parent.parent
CANONICAL_REGISTRY = BASE_DIR / "missions" / "Mission-Registry.md"

VALID_STATUSES = ["Draft", "Planned", "Active", "Blocked", "Review", "Completed", "Archived"]

MISSION_REGISTRY_TRIGGERS = [
    "create mission",
    "create a mission",
    "new mission",
    "active missions",
    "completed missions",
    "show status",
    "mission status",
    "show mission",
    "find ",
    "search missions",
    "repository missions",
]


def is_mission_registry_request(user_text: str) -> bool:
    text = user_text.lower()
    return bool(extract_mission_id(text)) or any(trigger in text for trigger in MISSION_REGISTRY_TRIGGERS)


def extract_mission_id(user_text: str) -> Optional[str]:
    match = re.search(r"\bM-\d{8}-\d{6}\b", user_text, flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def parse_index_entry(line: str) -> Optional[dict]:
    if not line.startswith("- "):
        return None

    parts = [part.strip() for part in line[2:].split("|")]
    if len(parts) < 5:
        return None

    return {
        "mission_id": parts[0],
        "timestamp": parts[1],
        "domain": parts[2],
        "status": parts[3],
        "title": " | ".join(parts[4:]),
    }


def load_registry_entries() -> list[dict]:
    ensure_missions_dir()
    return [
        entry
        for entry in (parse_index_entry(line.strip()) for line in MISSION_INDEX.read_text(encoding="utf-8").splitlines())
        if entry
    ]


def mission_file_for(mission_id: str) -> Path:
    return MISSIONS_DIR / f"{mission_id}.md"


def infer_domain(title: str) -> str:
    text = title.lower()
    if any(word in text for word in ["repo", "repository", "architecture", "code", "runtime"]):
        return "Engineering"
    if any(word in text for word in ["crew", "specialist", "registry", "knowledge"]):
        return "Knowledge"
    return "Command"


def create_mission(user_text: str) -> dict:
    ensure_missions_dir()
    mission_id = generate_mission_id()
    raw_title = re.sub(r"(?i)^.*?create (?:a )?mission(?: for|:)?", "", user_text).strip()
    title = build_title(raw_title or user_text)
    domain = infer_domain(title)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = f"""# Mission Record

## Metadata

Mission ID: {mission_id}

Timestamp: {timestamp}

Mission Domain: {domain}

Assigned Specialists: Chief of Staff

Priority: P3 - Normal

Status: Active

Source: Mission Registry Runtime

## Mission

{redact_secrets(title)}

## Notes

Created from Commander mission registry request.
"""

    mission_file_for(mission_id).write_text(content, encoding="utf-8")
    update_mission_index(mission_id, domain, "Active", title)
    append_canonical_registry(mission_id, title, domain, "Active")
    return {"mission_id": mission_id, "title": title, "domain": domain, "status": "Active"}


def append_canonical_registry(mission_id: str, title: str, domain: str, status: str) -> None:
    if not CANONICAL_REGISTRY.exists():
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with CANONICAL_REGISTRY.open("a", encoding="utf-8") as registry:
        registry.write(f"\n- {mission_id} | {timestamp} | {domain} | {status} | {redact_secrets(title)}\n")


def get_mission(mission_id: str) -> Optional[str]:
    path = mission_file_for(mission_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def update_mission_status(mission_id: str, status: str) -> bool:
    if status.title() not in VALID_STATUSES:
        return False

    path = mission_file_for(mission_id)
    if not path.exists():
        return False

    content = path.read_text(encoding="utf-8")
    updated = re.sub(r"^Status:\s*.+$", f"Status: {status.title()}", content, flags=re.MULTILINE)
    path.write_text(updated, encoding="utf-8")
    return True


def filter_missions(status: Optional[str] = None, query: Optional[str] = None) -> list[dict]:
    missions = load_registry_entries()

    if status:
        missions = [mission for mission in missions if mission["status"].lower() == status.lower()]

    if query:
        query_text = query.lower()
        missions = [
            mission for mission in missions
            if query_text in mission["title"].lower()
            or query_text in mission["domain"].lower()
            or query_text in mission["mission_id"].lower()
        ]

    return missions


def format_missions(title: str, missions: list[dict]) -> str:
    if not missions:
        return f"# {title}\n\nNo matching missions found."

    lines = [f"# {title}", ""]
    for mission in missions:
        lines.extend([
            f"- `{mission['mission_id']}` - {mission['title']}",
            f"  Status: {mission['status']} | Domain: {mission['domain']} | {mission['timestamp']}",
        ])
    return "\n".join(lines)


def search_query_from_text(user_text: str) -> str:
    text = re.sub(r"(?i)\b(find|search|show)\b", "", user_text)
    text = re.sub(r"(?i)\b(missions?|for)\b", "", text)
    text = re.sub(r"<@[^>]+>", "", text)
    return text.strip() or user_text.strip()


def answer_mission_registry_request(user_text: str) -> str:
    text = user_text.lower()
    mission_id = extract_mission_id(user_text)

    status_match = re.search(r"\b(?:mark|set|update)\s+(M-\d{8}-\d{6})\s+(?:as|to)\s+(\w+)", user_text, flags=re.IGNORECASE)
    if status_match:
        requested_status = status_match.group(2).title()
        if requested_status not in VALID_STATUSES:
            return "# MISSION STATUS UPDATE\n\nUnknown mission status. Valid statuses: " + ", ".join(VALID_STATUSES)
        if update_mission_status(status_match.group(1).upper(), requested_status):
            return f"# MISSION STATUS UPDATE\n\n`{status_match.group(1).upper()}` updated to {requested_status}."
        return f"# MISSION STATUS UPDATE\n\nNo mission found for `{status_match.group(1).upper()}`."

    if "create mission" in text or "create a mission" in text or "new mission" in text:
        mission = create_mission(user_text)
        return "\n".join([
            "# MISSION CREATED",
            "",
            f"Mission ID: `{mission['mission_id']}`",
            f"Title: {mission['title']}",
            f"Domain: {mission['domain']}",
            f"Status: {mission['status']}",
        ])

    if mission_id:
        mission = get_mission(mission_id)
        if mission:
            return mission
        return f"# MISSION LOOKUP\n\nNo mission found for `{mission_id}`."

    if "active missions" in text:
        return format_missions("ACTIVE MISSIONS", filter_missions(status="Active"))

    if "completed missions" in text:
        return format_missions("COMPLETED MISSIONS", filter_missions(status="Completed"))

    if "find" in text or "search" in text or "repository missions" in text:
        query = "repository" if "repository missions" in text else search_query_from_text(user_text)
        return format_missions("MISSION SEARCH RESULTS", filter_missions(query=query))

    return format_missions("MISSION REGISTRY", load_registry_entries()[-10:])
