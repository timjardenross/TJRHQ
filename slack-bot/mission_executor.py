import re
from datetime import datetime
from typing import Optional

from knowledge_retrieval import recommend_knowledge_sources
from mission_logger import (
    MISSION_INDEX,
    MISSIONS_DIR,
    build_title,
    ensure_missions_dir,
    generate_mission_id,
    redact_secrets,
    update_mission_index,
)
from mission_registry import VALID_STATUSES, extract_mission_id, get_mission, mission_file_for
from specialist_registry import load_specialist_profiles

EXECUTION_MARKERS = [
    "Execution Plan Created",
    "Assigned",
    "In Progress",
    "Waiting",
    "Ready for Review",
    "Closed",
]

MISSION_EXECUTION_TRIGGERS = [
    "create a mission to",
    "create mission to",
    "start a mission",
    "start mission",
    "assign mission",
    "assign specialist",
    "assign officer",
    "build an execution plan",
    "execution plan",
    "next action for this mission",
    "continue the current mission",
    "show mission execution plan",
    "show progress on mission",
    "close mission",
    "close this mission",
    "update mission",
]

def is_secret_request(user_text: str) -> bool:
    text = user_text.lower()
    if any(term in text for term in [".env", ".venv", "api key", "token", "secret"]):
        return True
    return "credential" in text and any(action in text for action in ["read", "show", "print", "expose", "display"])


def is_mission_execution_request(user_text: str) -> bool:
    text = user_text.lower()

    if is_secret_request(text):
        return False

    if re.search(r"\bupdate mission\s+M-[A-Z0-9-]+\s+as\s+\w+", user_text, flags=re.IGNORECASE):
        return True

    if re.search(
        r"\b(close|show progress on|show mission execution plan)\s+mission\s+M-[A-Z0-9-]+",
        user_text,
        flags=re.IGNORECASE,
    ):
        return True

    if re.search(r"\bassign\b.*\b(officer|specialist|mission)\b", user_text, flags=re.IGNORECASE):
        return True

    return any(trigger in text for trigger in MISSION_EXECUTION_TRIGGERS)


def classify_mission_type(user_text: str) -> str:
    text = user_text.lower()

    if any(word in text for word in ["medical bay", "chronic pain", "health", "wellness", "coaching"]):
        return "Health / Product Review"
    if any(word in text for word in ["voice core", "voice", "runtime", "architecture", "technical"]):
        return "Technical Planning"
    if any(word in text for word in ["ui", "ux", "website", "command deck", "redesign", "design"]):
        return "Product / UX Mission"
    if any(word in text for word in ["research", "evidence"]):
        return "Research Mission"
    if any(word in text for word in ["governance", "standard", "policy"]):
        return "Governance Mission"
    if any(word in text for word in ["knowledge", "repository", "documentation"]):
        return "Knowledge Mission"
    return "General Mission"


def profile_exists(name: str, profiles: dict) -> bool:
    return name in profiles


def assign_execution_team(mission_type: str, user_text: str) -> dict:
    profiles = load_specialist_profiles()
    text = user_text.lower()

    explicit_team = []
    for title in profiles:
        if title.lower() in text:
            explicit_team.append(title)

    if "ux officer" in text and "UX Design Officer" in profiles:
        explicit_team.append("UX Design Officer")

    if explicit_team:
        owner = explicit_team[0]
        specialists = dedupe(explicit_team)
        return {"owner": owner, "specialists": specialists}

    teams = {
        "Product / UX Mission": ["Operations Officer", "Knowledge Officer", "Chief Engineer", "UX Design Officer"],
        "Technical Planning": ["Chief Engineer", "Research Officer", "Knowledge Officer"],
        "Health / Product Review": ["Medical Officer", "Research Officer", "Knowledge Officer"],
        "Research Mission": ["Research Officer", "Knowledge Officer", "Chief of Staff"],
        "Governance Mission": ["Chief of Staff", "Knowledge Officer"],
        "Knowledge Mission": ["Knowledge Officer", "Chief of Staff"],
        "General Mission": ["Chief of Staff", "Knowledge Officer"],
    }

    desired = teams.get(mission_type, teams["General Mission"])
    available = [name for name in desired if profile_exists(name, profiles)]

    if not available:
        available = ["Chief of Staff"] if "Chief of Staff" in profiles else list(profiles.keys())[:1]

    return {
        "owner": available[0],
        "specialists": available,
    }


def identify_required_sources(user_text: str) -> list[str]:
    sources = recommend_knowledge_sources(user_text)
    text = user_text.lower()

    if "voice core" in text:
        sources.extend([
            "knowledge/architecture/Runtime-Module-Design.md",
            "knowledge/architecture/Integration-Strategy.md",
            "specialists/knowledge-packs/Voice-Experience-Guidelines.md",
        ])
    if "ui" in text or "website" in text or "command deck" in text:
        sources.extend([
            "specialists/knowledge-packs/Human-Centred-Design.md",
            "specialists/knowledge-packs/Dashboard-Design-Framework.md",
            "specialists/knowledge-packs/UX-Design-Officer-Knowledge.md",
        ])
    if "medical bay" in text or "chronic pain" in text:
        sources.extend([
            "specialists/knowledge-packs/Medical-Officer-Knowledge.md",
            "specialists/knowledge-packs/Chronic-Pain-Framework.md",
            "specialists/knowledge-packs/Research-Methodology.md",
        ])

    return dedupe(sources)[:10]


def build_execution_steps(user_text: str, team: dict, sources: list[str]) -> list[str]:
    owner = team["owner"]
    specialists = ", ".join(team["specialists"])

    return [
        f"Confirm objective, scope and mission owner with {owner}.",
        f"Review required sources: {', '.join(sources[:4]) or 'No source list available'}.",
        f"Collect specialist input from {specialists}.",
        "Define deliverables and acceptance criteria.",
        "Identify risks, dependencies and blockers.",
        "Prepare review summary and next action recommendation.",
        "Move mission to Review or Completed when closure criteria are met.",
    ]


def create_execution_plan(user_text: str, context: dict = None) -> dict:
    mission_type = classify_mission_type(user_text)
    team = assign_execution_team(mission_type, user_text)
    sources = identify_required_sources(user_text)
    steps = build_execution_steps(user_text, team, sources)
    objective = extract_objective(user_text)

    return {
        "objective": objective,
        "mission_type": mission_type,
        "owner": team["owner"],
        "specialists": team["specialists"],
        "sources": sources,
        "steps": steps,
        "deliverables": [
            "Mission execution plan",
            "Specialist review summary",
            "Risks and blocker list",
            "Final recommendation or closure summary",
        ],
        "acceptance_criteria": [
            "Mission owner is assigned.",
            "Supporting specialists are identified.",
            "Required knowledge sources are listed.",
            "Next actions and review point are clear.",
        ],
        "closure_criteria": [
            "Deliverables are produced.",
            "Acceptance criteria are reviewed.",
            "Outcome and follow-up actions are recorded.",
        ],
    }


def create_mission_execution_record(user_text: str) -> dict:
    ensure_missions_dir()
    mission_id = generate_mission_id()
    plan = create_execution_plan(user_text)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = build_title(plan["objective"])

    content = render_mission_record(mission_id, timestamp, plan, status="Active", marker="Execution Plan Created")
    mission_file_for(mission_id).write_text(content, encoding="utf-8")
    update_mission_index(mission_id, plan["mission_type"], "Active", title)

    return {"mission_id": mission_id, "plan": plan, "status": "Active", "marker": "Execution Plan Created"}


def render_mission_record(mission_id: str, timestamp: str, plan: dict, status: str, marker: str, note: str = "") -> str:
    return f"""# Mission Execution Record

## Metadata

Mission ID: {mission_id}

Timestamp: {timestamp}

Mission Type: {plan['mission_type']}

Mission Owner: {plan['owner']}

Assigned Specialists: {', '.join(plan['specialists'])}

Status: {status}

Execution Marker: {marker}

Source: BOT-013 Mission Executor

## Objective

{redact_secrets(plan['objective'])}

## Scope

Plan, coordinate, review and close the mission through Commander Runtime.

## Out of Scope

- Background workers
- Autonomous long-running tasks
- Shell command execution
- Unapproved file or code changes

## Required Knowledge Sources

{format_bullets(plan['sources'])}

## Execution Plan

{format_numbered(plan['steps'])}

## Deliverables

{format_bullets(plan['deliverables'])}

## Acceptance Criteria

{format_bullets(plan['acceptance_criteria'])}

## Review Point

Review after the execution plan is accepted or whenever a blocker is added.

## Closure Criteria

{format_bullets(plan['closure_criteria'])}

## Risks / Blockers

{redact_secrets(note) if note else 'No blockers recorded.'}

## Next Actions

- Confirm plan and owner.
- Start the first execution step.

## Mission Log

- {timestamp}: Mission execution plan created.
"""


def update_execution_status(mission_id: str, status: str, note: str) -> dict:
    normalized_status = status.title()
    if normalized_status not in VALID_STATUSES:
        return {
            "success": False,
            "error": "Invalid status",
            "valid_statuses": VALID_STATUSES,
        }

    mission = get_mission(mission_id)
    if not mission:
        return {"success": False, "error": "Mission not found", "mission_id": mission_id}

    marker = marker_for_status(normalized_status)
    updated = re.sub(r"^Status:\s*.+$", f"Status: {normalized_status}", mission, flags=re.MULTILINE)
    updated = re.sub(r"^Execution Marker:\s*.+$", f"Execution Marker: {marker}", updated, flags=re.MULTILINE)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"\n- {timestamp}: Status updated to {normalized_status}."
    if note:
        log_line += f" Note: {redact_secrets(note)}"
    updated = append_to_section(updated, "Mission Log", log_line)

    if note and normalized_status == "Blocked":
        updated = append_to_section(updated, "Risks / Blockers", f"\n- {redact_secrets(note)}")

    mission_file_for(mission_id).write_text(updated, encoding="utf-8")
    update_index_status(mission_id, normalized_status)

    return {"success": True, "mission_id": mission_id, "status": normalized_status, "marker": marker, "note": note}


def generate_progress_summary(mission_id: str) -> str:
    mission = get_mission(mission_id)
    if not mission:
        return not_found_response(mission_id)

    return "\n".join([
        "# MISSION EXECUTION",
        "",
        "## Mission Summary",
        "",
        extract_section_text(mission, "Objective") or "Mission objective unavailable.",
        "",
        "## Mission ID",
        "",
        mission_id,
        "",
        "## Current Status",
        "",
        extract_metadata_field(mission, "Status") or "Unknown",
        "",
        "## Mission Owner",
        "",
        extract_metadata_field(mission, "Mission Owner") or "Unknown",
        "",
        "## Assigned Specialists",
        "",
        extract_metadata_field(mission, "Assigned Specialists") or "Unknown",
        "",
        "## Next Actions",
        "",
        extract_section_text(mission, "Next Actions") or "- Review mission record and define next action.",
        "",
        "## Mission Log Update",
        "",
        extract_section_text(mission, "Mission Log") or "No mission log entries found.",
    ])


def generate_closure_summary(mission_id: str) -> str:
    mission = get_mission(mission_id)
    if not mission:
        return "# MISSION EXECUTION\n\n## Mission Summary\n\nMission closure refused because no mission record was found.\n\n## Mission ID\n\n" + mission_id

    acceptance = extract_section_text(mission, "Acceptance Criteria")
    final_status = "Completed" if acceptance else "Review"
    update_execution_status(mission_id, final_status, "Mission closure summary generated.")

    return "\n".join([
        "# MISSION EXECUTION",
        "",
        "## Mission Summary",
        "",
        "Mission closure summary generated from the current execution record.",
        "",
        "## Mission ID",
        "",
        mission_id,
        "",
        "## Current Status",
        "",
        final_status,
        "",
        "## Mission Log Update",
        "",
        "Closure summary captured. Mission status updated based on available acceptance criteria.",
        "",
        "## Next Actions",
        "",
        "- Review closure summary.",
        "- Capture any follow-up missions if needed.",
    ])


def execute_mission_request(user_text: str) -> str:
    if is_secret_request(user_text):
        return "# MISSION EXECUTION\n\n## Mission Summary\n\nCredential and secret requests are refused. BOT-013 does not read `.env`, `.venv/`, tokens, API keys or credentials."

    text = user_text.lower()
    loose_mission_id = extract_loose_mission_id(user_text)

    if "update mission" in text:
        mission_id = loose_mission_id or extract_mission_id(user_text)
        if not mission_id:
            return "# MISSION EXECUTION\n\n## Mission Summary\n\nNo mission ID was provided for the status update."
        status, note = parse_status_update(user_text)
        result = update_execution_status(mission_id, status, note)
        return format_status_update_response(result)

    if "show progress on mission" in text or "next action for this mission" in text or "continue the current mission" in text:
        mission_id = loose_mission_id or latest_active_mission_id()
        if not mission_id:
            return "# MISSION EXECUTION\n\n## Mission Summary\n\nNo current mission was found."
        return generate_progress_summary(mission_id)

    if "close mission" in text or "close this mission" in text:
        mission_id = loose_mission_id or latest_active_mission_id()
        if not mission_id:
            return "# MISSION EXECUTION\n\n## Mission Summary\n\nMission closure refused because no mission ID or current mission was found."
        return generate_closure_summary(mission_id)

    if "show mission execution plan" in text:
        mission_id = loose_mission_id or latest_active_mission_id()
        if not mission_id:
            return "# MISSION EXECUTION\n\n## Mission Summary\n\nNo mission execution plan was found."
        mission = get_mission(mission_id)
        return mission if mission else not_found_response(mission_id)

    record = create_mission_execution_record(user_text)
    return format_execution_response(record)


def format_execution_response(record: dict) -> str:
    plan = record["plan"]
    return "\n".join([
        "# MISSION EXECUTION",
        "",
        "## Mission Summary",
        "",
        plan["objective"],
        "",
        "## Mission ID",
        "",
        record["mission_id"],
        "",
        "## Mission Type",
        "",
        plan["mission_type"],
        "",
        "## Mission Owner",
        "",
        plan["owner"],
        "",
        "## Assigned Specialists",
        "",
        *[f"- {name}" for name in plan["specialists"]],
        "",
        "## Required Knowledge Sources",
        "",
        *[f"- `{source}`" for source in plan["sources"]],
        "",
        "## Execution Plan",
        "",
        *[f"{idx}. {step}" for idx, step in enumerate(plan["steps"], start=1)],
        "",
        "## Current Status",
        "",
        f"{record['status']} / {record['marker']}",
        "",
        "## Risks / Blockers",
        "",
        "- No blockers recorded.",
        "",
        "## Next Actions",
        "",
        "- Confirm plan and owner.",
        "- Start the first execution step.",
        "",
        "## Mission Log Update",
        "",
        "Mission execution plan created and recorded.",
    ])


def format_status_update_response(result: dict) -> str:
    if not result["success"]:
        if result["error"] == "Invalid status":
            return "# MISSION EXECUTION\n\n## Mission Summary\n\nInvalid mission status.\n\n## Current Status\n\nValid statuses: " + ", ".join(result["valid_statuses"])
        return not_found_response(result.get("mission_id", "Unknown"))

    return "\n".join([
        "# MISSION EXECUTION",
        "",
        "## Mission Summary",
        "",
        "Mission execution status updated.",
        "",
        "## Mission ID",
        "",
        result["mission_id"],
        "",
        "## Current Status",
        "",
        f"{result['status']} / {result['marker']}",
        "",
        "## Risks / Blockers",
        "",
        result["note"] or "No blocker note provided.",
        "",
        "## Mission Log Update",
        "",
        "Status update recorded in the mission execution log.",
    ])


def extract_objective(user_text: str) -> str:
    cleaned = re.sub(r"<@[^>]+>", "", user_text).strip()
    cleaned = re.sub(r"(?i)^(create|start|build)\s+(?:a|an)?\s*(mission|execution plan)?\s*(to|for)?\s*", "", cleaned).strip()
    cleaned = re.sub(r"(?i)^assign\s+", "Assign ", cleaned).strip()
    return cleaned or "Commander Runtime Mission"


def extract_loose_mission_id(user_text: str) -> Optional[str]:
    match = re.search(r"\bM-[A-Z0-9-]+\b", user_text, flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def parse_status_update(user_text: str) -> tuple[str, str]:
    status_match = re.search(r"\bas\s+(\w+)", user_text, flags=re.IGNORECASE)
    status = status_match.group(1) if status_match else "Active"
    note_match = re.search(r"\bbecause\s+(.+)$", user_text, flags=re.IGNORECASE)
    note = note_match.group(1).strip() if note_match else ""
    return status, note


def marker_for_status(status: str) -> str:
    return {
        "Draft": "Execution Plan Created",
        "Planned": "Assigned",
        "Active": "In Progress",
        "Blocked": "Waiting",
        "Review": "Ready for Review",
        "Completed": "Closed",
        "Archived": "Closed",
    }.get(status, "In Progress")


def append_to_section(markdown: str, heading: str, addition: str) -> str:
    pattern = rf"(## {re.escape(heading)}\n\n)([\s\S]*?)(?=\n## |\Z)"
    match = re.search(pattern, markdown)
    if not match:
        return markdown + f"\n\n## {heading}\n\n{addition.strip()}\n"
    return markdown[:match.end(2)] + addition + markdown[match.end(2):]


def extract_metadata_field(markdown: str, field: str) -> str:
    match = re.search(rf"^{re.escape(field)}:\s*(.+)$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_section_text(markdown: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)"
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def update_index_status(mission_id: str, status: str) -> None:
    if not MISSION_INDEX.exists():
        return
    lines = MISSION_INDEX.read_text(encoding="utf-8").splitlines()
    updated_lines = []
    for line in lines:
        if line.startswith(f"- {mission_id} |"):
            parts = [part.strip() for part in line[2:].split("|")]
            if len(parts) >= 5:
                parts[3] = status
                line = "- " + " | ".join(parts)
        updated_lines.append(line)
    MISSION_INDEX.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def latest_active_mission_id() -> Optional[str]:
    if not MISSION_INDEX.exists():
        return None
    mission_ids = []
    for line in MISSION_INDEX.read_text(encoding="utf-8").splitlines():
        if " | Active | " in line and line.startswith("- "):
            mission_ids.append(line[2:].split("|")[0].strip())
    return mission_ids[-1] if mission_ids else None


def not_found_response(mission_id: str) -> str:
    return "\n".join([
        "# MISSION EXECUTION",
        "",
        "## Mission Summary",
        "",
        "Mission not found.",
        "",
        "## Mission ID",
        "",
        mission_id,
        "",
        "## Current Status",
        "",
        "Unknown",
        "",
        "## Next Actions",
        "",
        "- Check the mission ID and try again.",
    ])


def format_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None identified."


def format_numbered(items: list[str]) -> str:
    return "\n".join(f"{idx}. {item}" for idx, item in enumerate(items, start=1)) if items else "1. Define next step."


def dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result
