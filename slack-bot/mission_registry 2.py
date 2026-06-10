import re
from collections import Counter
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
# MSN-0045 (Captain decision 2): runtime mission logging writes to the AUTHORITATIVE
# registry. Previously this pointed at the deprecated `missions/Mission-Registry.md`
# (a write-only dead-end nothing read back). The deprecated file is retained on disk
# for read compatibility (knowledge_retrieval/repository_awareness reference it) but is
# no longer a write target.
CANONICAL_REGISTRY = BASE_DIR / "core" / "mission-control" / "registry" / "mission-index.txt"
# Legacy (deprecated) write target — RETAINED FOR READ COMPAT ONLY, never written:
DEPRECATED_REGISTRY = BASE_DIR / "missions" / "Mission-Registry.md"

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
    "mission health",
    "blocked missions",
    "overdue missions",
    "mission metrics",
]

OVERDUE_DAYS = 14


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
    lines = MISSION_INDEX.read_text(encoding="utf-8").splitlines()
    return [
        entry
        for entry in (parse_index_entry(line.strip()) for line in lines)
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
    """Append a runtime mission record to the AUTHORITATIVE registry (MSN-0045).

    Runtime records use timestamp IDs (M-YYYYMMDD-HHMMSS) and are appended as
    dash-list lines under the "RUNTIME MISSION LOG" section of mission-index.txt.
    They are intentionally NOT written as canonical table rows (canonical rows use
    USS-TJR-MSN-NNNN identifiers and require full metadata). This keeps the canonical
    table intact while ensuring runtime logging lands in the authoritative file.
    """
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


def mission_age_days(mission: dict) -> Optional[int]:
    try:
        created = datetime.strptime(mission["timestamp"], "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return (datetime.now() - created).days


def mission_owner(mission_id: str) -> str:
    content = get_mission(mission_id)
    if not content:
        return "Unassigned"

    for field in ["Mission Owner", "Assigned Specialists"]:
        match = re.search(rf"^{re.escape(field)}:\s*(.+)$", content, flags=re.MULTILINE)
        if match:
            return match.group(1).split(",")[0].strip()

    return "Unassigned"


def mission_has_blocker(mission: dict) -> bool:
    if mission["status"].lower() == "blocked":
        return True

    content = get_mission(mission["mission_id"]) or ""
    blocker_section = extract_section(content, "Risks / Blockers")
    if not blocker_section:
        return False

    blocker_text = blocker_section.strip().lower()
    if not blocker_text or blocker_text in ["no blockers recorded.", "- no blockers recorded."]:
        return False

    meaningful_lines = [
        line.strip().lower()
        for line in blocker_section.splitlines()
        if line.strip() and "no blockers recorded" not in line.lower()
    ]
    return any(
        any(term in line for term in ["blocked", "blocker", "waiting", "pending"])
        for line in meaningful_lines
    )


def extract_section(content: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)",
        content,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def blocked_missions() -> list[dict]:
    return [mission for mission in load_registry_entries() if mission_has_blocker(mission)]


def overdue_missions(days: int = OVERDUE_DAYS) -> list[dict]:
    overdue = []
    active_statuses = {"Draft", "Planned", "Active", "Review", "Blocked"}

    for mission in load_registry_entries():
        if mission["status"] not in active_statuses:
            continue
        age = mission_age_days(mission)
        if age is not None and age > days:
            overdue.append({**mission, "age_days": age})

    return overdue


def completion_rate(entries: list[dict]) -> float:
    if not entries:
        return 0.0
    completed = len([mission for mission in entries if mission["status"] in ["Completed", "Archived"]])
    return round((completed / len(entries)) * 100, 1)


def owner_workload(entries: list[dict]) -> Counter:
    active_statuses = {"Draft", "Planned", "Active", "Review", "Blocked"}
    owners = [
        mission_owner(mission["mission_id"])
        for mission in entries
        if mission["status"] in active_statuses
    ]
    return Counter(owners)


def format_dashboard_list(missions: list[dict], include_age: bool = True) -> list[str]:
    if not missions:
        return ["- None found."]

    lines = []
    for mission in missions:
        age = mission.get("age_days")
        if age is None:
            age = mission_age_days(mission)
        age_text = f" | Age: {age} days" if include_age and age is not None else ""
        owner = mission_owner(mission["mission_id"])
        lines.append(
            f"- `{mission['mission_id']}` - {mission['title']} | "
            f"Status: {mission['status']} | Owner: {owner}{age_text}"
        )
    return lines


def format_owner_workload(workload: Counter) -> list[str]:
    if not workload:
        return ["- No active owner workload found."]
    return [f"- {owner}: {count}" for owner, count in sorted(workload.items())]


def format_history(entries: list[dict], limit: int = 5) -> list[str]:
    if not entries:
        return ["- No mission history found."]
    return [
        f"- `{mission['mission_id']}` - {mission['title']} | {mission['status']} | {mission['timestamp']}"
        for mission in entries[-limit:]
    ]


def format_status_counts(statuses: Counter) -> list[str]:
    if not statuses:
        return ["- No missions found."]
    return [f"- {status}: {count}" for status, count in sorted(statuses.items())]


def build_mission_health_report() -> str:
    entries = load_registry_entries()
    statuses = Counter(mission["status"] for mission in entries)
    blocked = blocked_missions()
    overdue = overdue_missions()
    rate = completion_rate(entries)
    workload = owner_workload(entries)

    return "\n".join([
        "# MISSION HEALTH",
        "",
        "## Mission Metrics",
        "",
        f"- Total Missions: {len(entries)}",
        f"- Completion Rate: {rate}%",
        f"- Blocked Missions: {len(blocked)}",
        f"- Overdue Missions: {len(overdue)}",
        "",
        "## Status Counts",
        "",
        *format_status_counts(statuses),
        "",
        "## Blocked Missions",
        "",
        *format_dashboard_list(blocked),
        "",
        "## Overdue Missions",
        "",
        *format_dashboard_list(overdue),
        "",
        "## Owner Workload",
        "",
        *format_owner_workload(workload),
        "",
        "## Mission History",
        "",
        *format_history(entries),
        "",
        "## Recommended Next Actions",
        "",
        "- Review blocked missions first.",
        "- Review overdue missions during the next planning checkpoint.",
        "- Balance owner workload before creating additional active missions.",
    ])


def build_blocked_missions_report() -> str:
    blocked = blocked_missions()
    return "\n".join([
        "# BLOCKED MISSIONS",
        "",
        *format_dashboard_list(blocked),
    ])


def build_overdue_missions_report() -> str:
    overdue = overdue_missions()
    return "\n".join([
        "# OVERDUE MISSIONS",
        "",
        f"Overdue threshold: {OVERDUE_DAYS} days",
        "",
        *format_dashboard_list(overdue),
    ])


def build_mission_metrics_report() -> str:
    entries = load_registry_entries()
    workload = owner_workload(entries)
    return "\n".join([
        "# MISSION METRICS",
        "",
        f"Mission Completion Rate: {completion_rate(entries)}%",
        "",
        "## Mission Age",
        "",
        *format_dashboard_list([{**mission, "age_days": mission_age_days(mission)} for mission in entries[-10:]]),
        "",
        "## Blocked Mission Detection",
        "",
        f"- Blocked Missions: {len(blocked_missions())}",
        "",
        "## Owner Workload",
        "",
        *format_owner_workload(workload),
        "",
        "## Mission History Reporting",
        "",
        *format_history(entries, limit=10),
    ])


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
        # Normalize status to title-case for schema compliance
        normalized_status = status.capitalize() if status else None
        missions = [mission for mission in missions if normalized_status and mission["status"] == normalized_status]

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

    status_match = re.search(
        r"\b(?:mark|set|update)\s+(M-\d{8}-\d{6})\s+(?:as|to)\s+(\w+)",
        user_text,
        flags=re.IGNORECASE,
    )
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

    if "mission health" in text:
        return build_mission_health_report()

    if "blocked missions" in text:
        return build_blocked_missions_report()

    if "overdue missions" in text:
        return build_overdue_missions_report()

    if "mission metrics" in text:
        return build_mission_metrics_report()

    if "active missions" in text:
        return format_missions("ACTIVE MISSIONS", filter_missions(status="Active"))

    if "completed missions" in text:
        return format_missions("COMPLETED MISSIONS", filter_missions(status="Completed"))

    if "find" in text or "search" in text or "repository missions" in text:
        query = "repository" if "repository missions" in text else search_query_from_text(user_text)
        return format_missions("MISSION SEARCH RESULTS", filter_missions(query=query))

    return format_missions("MISSION REGISTRY", load_registry_entries()[-10:])
