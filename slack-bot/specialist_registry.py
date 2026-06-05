import re
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent

SPECIALIST_FILES = [
    "command/Commander-TJR.md",
    "specialists/core-crew/Chief-of-Staff.md",
    "specialists/core-crew/Chief-Engineer.md",
    "specialists/core-crew/Coder-Agent.md",
    "specialists/core-crew/Knowledge-Officer.md",
    "specialists/core-crew/QA-Test-Officer.md",
]

SPECIALIST_QUERY_TRIGGERS = [
    "what specialists",
    "available specialists",
    "list crew",
    "current crew",
    "who handles",
    "who should handle",
    "which specialist",
    "handle testing",
    "what does",
    "specialist registry",
    "crew registry",
]

MATCH_KEYWORDS = {
    "Chief of Staff": ["priority", "focus", "plan", "roadmap", "strategy", "coordination"],
    "Chief Engineer": ["architecture", "repo", "repository", "system", "technical", "security"],
    "Coder Agent": ["code", "bug", "build", "implement", "implementation", "fix", "feature"],
    "Knowledge Officer": ["document", "documentation", "knowledge", "folder", "structure", "registry", "log", "mission logging", "memory"],
    "QA & Test Officer": ["test", "qa", "validate", "validation", "quality", "acceptance"],
}


def read_markdown(relative_path: str) -> str:
    path = BASE_DIR / relative_path

    if not path.exists():
        return ""

    return path.read_text(encoding="utf-8")


def load_specialist_registry() -> str:
    return read_markdown("specialists/Crew-Registry.md")


def is_specialist_query(user_text: str) -> bool:
    text = user_text.lower()
    return any(trigger in text for trigger in SPECIALIST_QUERY_TRIGGERS)


def extract_field(markdown: str, field: str) -> str:
    match = re.search(rf"^{re.escape(field)}:\s*(.+)$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_section(markdown: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)"
    match = re.search(pattern, markdown, flags=re.MULTILINE)

    if not match:
        return ""

    return match.group(1).strip()


def first_paragraph(markdown: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", markdown) if part.strip()]
    return paragraphs[0] if paragraphs else ""


def load_specialist_profiles() -> dict:
    profiles = {}

    for relative_path in SPECIALIST_FILES:
        markdown = read_markdown(relative_path)

        if not markdown:
            continue

        title = extract_field(markdown, "Title") or Path(relative_path).stem
        profiles[title] = {
            "registry_number": extract_field(markdown, "Registry Number"),
            "title": title,
            "department": extract_field(markdown, "Department"),
            "status": extract_field(markdown, "Status"),
            "reports_to": extract_field(markdown, "Reports To"),
            "authority": extract_field(markdown, "Authority"),
            "decision_authority": extract_field(markdown, "Decision Authority"),
            "implementation_authority": extract_field(markdown, "Implementation Authority"),
            "mission": first_paragraph(extract_section(markdown, "Mission")),
            "core_responsibilities": extract_section(markdown, "Core Responsibilities"),
            "areas_of_responsibility": extract_section(markdown, "Areas of Responsibility"),
            "source": relative_path,
        }

    return profiles


def get_available_specialists() -> list:
    return list(load_specialist_profiles().values())


def find_specialist_by_name(name: str) -> Optional[dict]:
    text = name.lower()

    for profile in load_specialist_profiles().values():
        title = profile["title"].lower()

        if title in text or text in title:
            return profile

    return None


def match_specialists_to_request(user_text: str) -> list:
    text = user_text.lower()
    matches = []
    named_profile = find_specialist_by_name(user_text)

    if named_profile:
        return [named_profile]

    if "mission logging" in text or "mission log" in text:
        return [
            load_specialist_profiles()[name]
            for name in ["Knowledge Officer", "Chief Engineer", "Coder Agent", "QA & Test Officer"]
        ]

    for title, keywords in MATCH_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            profile = load_specialist_profiles().get(title)
            if profile:
                matches.append(profile)

    if not matches:
        chief_of_staff = load_specialist_profiles().get("Chief of Staff")
        if chief_of_staff:
            matches.append(chief_of_staff)

    return matches


def summarise_specialists() -> str:
    profiles = get_available_specialists()
    by_department = {}

    for profile in profiles:
        by_department.setdefault(profile["department"], []).append(profile)

    lines = [
        "# MISSION SUMMARY",
        "",
        "Mission Domain: Command",
        "Assigned Specialists: Commander TJR",
        "Status: Completed",
        "",
        "# ASSESSMENT",
        "",
        "The current USS TJR crew includes:",
    ]

    for department, department_profiles in by_department.items():
        lines.extend(["", f"## {department}"])

        for profile in department_profiles:
            mission = profile["mission"] or profile["authority"]
            lines.extend(
                [
                    f"- {profile['registry_number']} {profile['title']}",
                    f"  - {mission}",
                ]
            )

    return "\n".join(lines)


def answer_specialist_query(user_text: str) -> str:
    text = user_text.lower()

    if any(trigger in text for trigger in ["what specialists", "available specialists", "list crew", "current crew", "crew registry"]):
        return summarise_specialists()

    named_profile = find_specialist_by_name(user_text)

    if named_profile and "what does" in text:
        return "\n".join(
            [
                "# SPECIALIST PROFILE",
                "",
                f"## {named_profile['title']}",
                "",
                f"Registry Number: {named_profile['registry_number']}",
                "",
                f"Department: {named_profile['department']}",
                "",
                f"Authority: {named_profile['authority']}",
                "",
                "## Mission",
                "",
                named_profile["mission"] or "Mission details are not available.",
            ]
        )

    matches = match_specialists_to_request(user_text)

    lines = [
        "# SPECIALIST RECOMMENDATION",
        "",
        "Recommended Specialists:",
        "",
    ]

    for profile in matches:
        lines.extend(
            [
                f"- {profile['registry_number']} {profile['title']}",
                f"  - {profile['authority']}",
            ]
        )

    if any(profile["title"] == "Coder Agent" for profile in matches):
        chief_engineer = load_specialist_profiles().get("Chief Engineer")
        if chief_engineer and not any(profile["title"] == "Chief Engineer" for profile in matches):
            lines.extend(
                [
                    "",
                    "Escalation:",
                    f"- {chief_engineer['title']} should review architecture or approve implementation decisions before build work proceeds.",
                ]
            )

    return "\n".join(lines)
