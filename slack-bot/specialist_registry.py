import re
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent

REGISTRY_FILE = "registry/Crew-Registry.md"
SPECIALIST_DIRS = ["specialists/core-crew", "specialists/future-crew"]

SPECIALIST_QUERY_TRIGGERS = [
    "what specialists",
    "future specialists",
    "available specialists",
    "list crew",
    "current crew",
    "who handles",
    "who should handle",
    "who should review",
    "which specialist",
    "specialist registry",
    "crew registry",
    "why did you select",
    "why did you choose",
]

MISSION_KEYWORDS = {
    "Chief of Staff": ["priority", "focus", "plan", "roadmap", "strategy", "coordination", "sprint"],
    "Chief Engineer": ["architecture", "repo", "repository", "system", "technical", "security", "platform", "runtime"],
    "Coder Agent": ["code", "bug", "build", "implement", "implementation", "fix", "feature"],
    "Knowledge Officer": ["document", "documentation", "knowledge", "folder", "structure", "registry", "log", "source of truth"],
    "QA & Test Officer": ["test", "qa", "validate", "validation", "quality", "acceptance", "release"],
    "Research Officer": ["research", "evidence", "source", "sources", "compare", "trend", "intelligence"],
    "Medical Officer": ["health", "medical", "pain", "chronic pain", "recovery", "appointment", "wellbeing"],
    "UX Officer": ["ux", "user experience", "usability", "accessibility", "interaction", "friction"],
    "Knowledge Architect": ["information architecture", "taxonomy", "navigation", "findability", "knowledge model"],
    "Product Designer": ["product", "feature", "product design", "scope", "acceptance criteria"],
}

TITLE_ALIASES = {
    "qa officer": "QA & Test Officer",
    "qa test officer": "QA & Test Officer",
    "engineer": "Chief Engineer",
    "ux officer": "UX Officer",
    "ia": "Knowledge Architect",
}


def read_markdown(relative_path: str) -> str:
    path = BASE_DIR / relative_path
    if not path.exists() or ".venv" in path.parts:
        return ""
    return path.read_text(encoding="utf-8")


def is_specialist_query(user_text: str) -> bool:
    text = user_text.lower()
    return any(trigger in text for trigger in SPECIALIST_QUERY_TRIGGERS)


def extract_field(markdown: str, *field_names: str) -> str:
    for field in field_names:
        flexible_field = re.escape(field).replace(r"\ ", "[_ -]")
        patterns = [
            rf"^\*\*{re.escape(field)}:\*\*\s*(.+?)(?:\s\s|$)",
            rf"^{re.escape(field)}:\s*(.+)$",
            rf"^{flexible_field}:\s*(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, markdown, flags=re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1).strip().strip("`")
    return ""


def extract_section(markdown: str, heading: str) -> str:
    pattern = rf"^#+\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^#+\s+|\Z)"
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def first_paragraph(markdown: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", markdown) if part.strip()]
    return paragraphs[0] if paragraphs else ""


def title_from_path(relative_path: str) -> str:
    return Path(relative_path).stem.replace("-", " ")


def parse_profile(relative_path: str, fallback_status: str = "") -> Optional[dict]:
    markdown = read_markdown(relative_path)
    if not markdown:
        return None

    first_heading = ""
    for line in markdown.splitlines():
        if line.startswith("# "):
            first_heading = re.sub(r"^#\s+", "", line).strip()
            break

    title = extract_field(markdown, "Title", "title") or first_heading or title_from_path(relative_path)
    status = extract_field(markdown, "Status", "status") or fallback_status
    department = extract_field(markdown, "Department", "Division", "department")
    mission_types = extract_section(markdown, "Mission Types")

    return {
        "registry_number": extract_field(markdown, "Registry Number", "Registry ID", "registry_id", "Registry"),
        "title": title,
        "status": status or "Unknown",
        "department": department or "Unknown",
        "mission_types": [line.strip("- ").strip() for line in mission_types.splitlines() if line.strip().startswith("-")],
        "maturity_level": extract_field(markdown, "Maturity Level") or "Unknown",
        "readiness": extract_field(markdown, "Operational Readiness") or "Unknown",
        "authority": extract_field(markdown, "Authority") or "Advisory",
        "mission": first_paragraph(extract_section(markdown, "Mission")) or extract_field(markdown, "Runtime Role"),
        "source": relative_path,
    }


def registry_status_by_source() -> dict:
    markdown = read_markdown(REGISTRY_FILE)
    statuses = {}
    current = None

    for line in markdown.splitlines():
        heading = re.match(r"^##\s+(.+)$", line)
        if heading and not re.match(r"^##\s+\d+\.", line):
            current = {"title": heading.group(1).strip()}
            continue

        if not current:
            continue

        source = re.search(r"\*\*Source File:\*\*\s*`([^`]+)`", line)
        status = re.search(r"\*\*Status:\*\*\s*(.+?)(?:\s\s|$)", line)

        if status:
            current["status"] = status.group(1).strip()

        if source:
            statuses[source.group(1)] = current.get("status", "")

    return statuses


def load_specialist_profiles() -> dict:
    profiles = {}
    registry_statuses = registry_status_by_source()

    for directory in SPECIALIST_DIRS:
        for path in sorted((BASE_DIR / directory).glob("*.md")):
            relative_path = str(path.relative_to(BASE_DIR))
            profile = parse_profile(relative_path, registry_statuses.get(relative_path, ""))
            if profile:
                profiles[profile["title"]] = profile

    return profiles


def get_available_specialists(include_future: bool = True) -> list[dict]:
    profiles = list(load_specialist_profiles().values())
    if include_future:
        return profiles
    return [profile for profile in profiles if profile["status"].lower() == "active"]


def find_specialist_by_name(name: str) -> Optional[dict]:
    text = name.lower()
    profiles = load_specialist_profiles()

    for alias, title in TITLE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text) and title in profiles:
            return profiles[title]

    for title, profile in profiles.items():
        if title.lower() in text or text in title.lower():
            return profile

    return None


def match_specialists_to_request(user_text: str) -> list[dict]:
    text = user_text.lower()
    profiles = load_specialist_profiles()
    named_profile = find_specialist_by_name(user_text)

    if named_profile and not text.startswith("why did"):
        return [named_profile]

    scored = []
    for title, keywords in MISSION_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score and title in profiles:
            scored.append((score, profiles[title]))

    scored.sort(key=lambda item: item[0], reverse=True)
    matches = []
    seen = set()
    for _, profile in scored:
        if profile["title"] not in seen:
            matches.append(profile)
            seen.add(profile["title"])

    if "chronic pain" in text:
        for title in ["Medical Officer", "Research Officer"]:
            if title in profiles and title not in seen:
                matches.append(profiles[title])
                seen.add(title)

    if not matches and "unknown" in text:
        return []

    if not matches and "review" in text:
        chief = profiles.get("Chief of Staff")
        if chief:
            matches.append(chief)

    if not matches:
        chief = profiles.get("Chief of Staff")
        if chief:
            matches.append(chief)

    return matches


def explain_selection(profile: dict, user_text: str) -> str:
    text = user_text.lower()
    matched = [keyword for keyword in MISSION_KEYWORDS.get(profile["title"], []) if keyword in text]
    if matched:
        return f"Matched mission signals: {', '.join(matched)}."
    if profile["mission_types"]:
        return f"Profile mission types include: {', '.join(profile['mission_types'][:4])}."
    if profile["title"] in MISSION_KEYWORDS:
        return f"{profile['title']} owns {', '.join(MISSION_KEYWORDS[profile['title']][:4])} mission signals in the runtime routing map."
    return profile["mission"] or "Selected as the default coordination owner when the mission type is unclear."


def format_profile_line(profile: dict) -> str:
    return (
        f"- `{profile['registry_number'] or 'Unregistered'}` {profile['title']} "
        f"({profile['status']}, {profile['department']}) - {profile['source']}"
    )


def summarise_specialists(include_future: bool = False) -> str:
    profiles = get_available_specialists(include_future=True)
    selected = profiles if include_future else [profile for profile in profiles if profile["status"].lower() == "active"]
    title = "SPECIALIST REGISTRY" if include_future else "ACTIVE SPECIALISTS"

    if not selected:
        return f"# {title}\n\nNo matching specialists found. Review `registry/Crew-Registry.md` and specialist charters."

    lines = [f"# {title}", ""]
    for profile in selected:
        if include_future or profile["status"].lower() == "active":
            lines.append(format_profile_line(profile))
    return "\n".join(lines)


def answer_specialist_query(user_text: str) -> str:
    text = user_text.lower()

    if "future specialists" in text or "future crew" in text:
        future = [profile for profile in get_available_specialists(True) if profile["status"].lower() != "active"]
        return "\n".join(["# FUTURE SPECIALISTS", "", *(format_profile_line(profile) for profile in future)])

    if any(trigger in text for trigger in ["what specialists", "available specialists", "list crew", "current crew", "crew registry", "specialist registry"]):
        return summarise_specialists(include_future="registry" in text or "crew" in text)

    if "why did you select" in text or "why did you choose" in text:
        profile = find_specialist_by_name(user_text)
        if not profile:
            return "# ROUTING EXPLANATION\n\nNo matching specialist found. Review the crew registry and specialist charters."
        return "\n".join([
            "# ROUTING EXPLANATION",
            "",
            f"Primary Specialist: {profile['title']}",
            "",
            explain_selection(profile, user_text),
            "",
            f"Source: `{profile['source']}`",
        ])

    matches = match_specialists_to_request(user_text)
    if not matches:
        return "# SPECIALIST RECOMMENDATION\n\nNo matching specialist found. Suggest a crew registry review."

    primary = matches[0]
    supporting = matches[1:]

    lines = [
        "# SPECIALIST RECOMMENDATION",
        "",
        "## Primary Specialist",
        "",
        format_profile_line(primary),
        explain_selection(primary, user_text),
        "",
        "## Supporting Specialists",
        "",
    ]

    if supporting:
        for profile in supporting:
            lines.extend([format_profile_line(profile), explain_selection(profile, user_text)])
    else:
        lines.append("No supporting specialist required from the current request signals.")

    lines.extend([
        "",
        "## Routing Decision",
        "",
        f"Commander selected {primary['title']} because the request matches that specialist's mission ownership and source profile.",
    ])

    return "\n".join(lines)
