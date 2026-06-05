import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from mission_logger import MISSION_INDEX, MISSIONS_DIR, ensure_missions_dir

MISSION_MANAGEMENT_TRIGGERS = [
    "active missions",
    "completed missions",
    "mission status",
    "mission history",
    "recent missions",
    "what missions",
    "show mission",
    "mission summary",
    "completed recently",
    "today's work",
    "todays work",
    "weekly summary",
]


def is_mission_management_request(user_text: str) -> bool:
    text = user_text.lower()
    return bool(extract_mission_id(user_text)) or any(
        trigger in text for trigger in MISSION_MANAGEMENT_TRIGGERS
    )


def extract_mission_id(user_text: str) -> Optional[str]:
    match = re.search(r"\bM-\d{8}-\d{6}\b", user_text)
    return match.group(0) if match else None


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


def load_index_entries() -> list:
    ensure_missions_dir()

    return [
        entry
        for entry in (
            parse_index_entry(line.strip())
            for line in MISSION_INDEX.read_text(encoding="utf-8").splitlines()
        )
        if entry
    ]


def get_recent_missions(limit=10):
    return load_index_entries()[-limit:]


def get_active_missions():
    return [
        mission
        for mission in load_index_entries()
        if mission["status"].lower() == "active"
    ]


def get_completed_missions():
    return [
        mission
        for mission in load_index_entries()
        if mission["status"].lower() == "completed"
    ]


def get_completed_missions_this_week():
    week_start = datetime.now() - timedelta(days=7)
    missions = []

    for mission in get_completed_missions():
        try:
            mission_time = datetime.strptime(mission["timestamp"], "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        if mission_time >= week_start:
            missions.append(mission)

    return missions


def get_mission_by_id(mission_id):
    ensure_missions_dir()
    mission_path = MISSIONS_DIR / f"{mission_id}.md"

    if not mission_path.exists():
        return None

    return mission_path.read_text(encoding="utf-8")


def format_mission_list(title: str, missions: list) -> str:
    if not missions:
        return f"# {title}\n\nNo matching missions found."

    lines = [f"# {title}", ""]

    for mission in missions:
        lines.extend(
            [
                f"- {mission['mission_id']}",
                f"  {mission['title']}",
                f"  Status: {mission['status']} | Domain: {mission['domain']} | {mission['timestamp']}",
            ]
        )

    return "\n".join(lines)


def build_mission_summary():
    entries = load_index_entries()
    active = [entry for entry in entries if entry["status"].lower() == "active"]
    completed = [entry for entry in entries if entry["status"].lower() == "completed"]
    recent = entries[-5:]

    lines = [
        "# MISSION SUMMARY",
        "",
        f"Active Missions: {len(active)}",
        "",
        f"Completed Missions: {len(completed)}",
        "",
        "Recent Work:",
        "",
    ]

    if recent:
        for mission in recent:
            lines.extend(
                [
                    f"- {mission['mission_id']}",
                    f"  {mission['title']}",
                ]
            )
    else:
        lines.append("No missions have been logged yet.")

    lines.extend(
        [
            "",
            "Recommended Next Mission:",
            "",
            "- Continue the highest-priority active mission or define the next Commander TJR capability.",
        ]
    )

    return "\n".join(lines)


def build_daily_summary():
    today = datetime.now().strftime("%Y-%m-%d")
    missions = [
        mission
        for mission in load_index_entries()
        if mission["timestamp"].startswith(today)
    ]

    return format_mission_list("TODAY'S WORK", missions)


def build_weekly_summary():
    week_start = datetime.now() - timedelta(days=7)
    missions = []

    for mission in load_index_entries():
        try:
            mission_time = datetime.strptime(mission["timestamp"], "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        if mission_time >= week_start:
            missions.append(mission)

    return format_mission_list("WEEKLY MISSION SUMMARY", missions)


def answer_mission_management_request(user_text: str) -> str:
    text = user_text.lower()
    mission_id = extract_mission_id(user_text)

    if mission_id:
        mission = get_mission_by_id(mission_id)

        if not mission:
            return f"# MISSION LOOKUP\n\nNo mission found for `{mission_id}`."

        return mission

    if "active missions" in text or "missions are active" in text:
        return format_mission_list("ACTIVE MISSIONS", get_active_missions())

    if "completed missions" in text or "completed this week" in text:
        if "week" in text:
            return format_mission_list(
                "COMPLETED MISSIONS THIS WEEK",
                get_completed_missions_this_week(),
            )
        return format_mission_list("COMPLETED MISSIONS", get_completed_missions())

    if "today's work" in text or "todays work" in text:
        return build_daily_summary()

    if "weekly summary" in text:
        return build_weekly_summary()

    if "mission summary" in text or "mission status" in text:
        return build_mission_summary()

    return format_mission_list("RECENT MISSIONS", get_recent_missions())
