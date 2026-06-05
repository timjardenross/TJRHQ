import re
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent

REPOSITORY_SOURCES = [
    "REPOSITORY-MAP.md",
    "knowledge/Repository-Catalogue.md",
    "knowledge/Source-of-Truth-Matrix.md",
    "knowledge/Commander-Knowledge-Index.md",
]

SECURITY_BLOCKLIST = {".env", "slack-bot/.env"}
SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__"}

REPOSITORY_TRIGGERS = [
    "repository",
    "repo",
    "folders exist",
    "folder structure",
    "file structure",
    "where should i put",
    "where do i put",
    "source of truth",
    "codex read",
    "read before implementing",
]

EXPECTED_FOLDERS = [
    "governance/",
    "registry/",
    "command/",
    "specialists/",
    "missions/",
    "knowledge/",
    "procedures/",
    "roadmap/",
    "slack-bot/",
    "testing/",
]


def safe_read(relative_path: str) -> tuple[str, Optional[str]]:
    normalized = relative_path.strip().lstrip("/")

    if normalized in SECURITY_BLOCKLIST or ".venv/" in normalized:
        return "", f"Refused unsafe path: {normalized}"

    path = BASE_DIR / normalized

    if not path.exists():
        return "", f"Missing file: {normalized}"

    if path.is_dir():
        return "", f"Expected file but found directory: {normalized}"

    return path.read_text(encoding="utf-8"), None


def load_repository_context() -> dict:
    documents = {}
    warnings = []

    for source in REPOSITORY_SOURCES:
        content, warning = safe_read(source)
        if warning:
            warnings.append(warning)
        documents[source] = content

    return {"documents": documents, "warnings": warnings}


def is_repository_awareness_request(user_text: str) -> bool:
    text = user_text.lower()

    if any(secret in text for secret in [".env", "api key", "token", "secret"]):
        return True

    if text.strip().startswith("review ") and any(
        phrase in text for phrase in ["repository structure", "repo structure"]
    ):
        return False

    return any(trigger in text for trigger in REPOSITORY_TRIGGERS)


def list_top_level_folders() -> list[str]:
    folders = []

    for child in BASE_DIR.iterdir():
        if child.is_dir() and child.name not in SKIP_DIRS:
            folders.append(f"{child.name}/")

    return sorted(folders)


def source_for_topic(topic: str) -> Optional[str]:
    context = load_repository_context()
    matrix = context["documents"].get("knowledge/Source-of-Truth-Matrix.md", "")

    for line in matrix.splitlines():
        if not line.startswith("|"):
            continue

        cells = [cell.strip(" `") for cell in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0].lower() == topic.lower():
            return cells[1]

    return None


def codex_reading_list(user_text: str) -> list[tuple[str, str]]:
    text = user_text.lower()
    bot_match = re.search(r"\b(bot-\d{3})\b", text, flags=re.IGNORECASE)
    bot_id = bot_match.group(1).upper() if bot_match else None

    files = []
    if bot_id:
        files.append((f"knowledge/architecture/{bot_id}/", f"{bot_id} architecture, requirements and acceptance tests."))

    if bot_id == "BOT-008":
        files.extend([
            ("REPOSITORY-MAP.md", "Top-level repository structure."),
            ("knowledge/Repository-Catalogue.md", "Folder purpose and ownership."),
            ("knowledge/Source-of-Truth-Matrix.md", "Authoritative source mapping."),
        ])
    elif bot_id == "BOT-009":
        files.extend([
            ("missions/Mission-Registry.md", "Master mission register."),
            ("missions/", "Mission records and templates."),
            ("slack-bot/mission_logger.py", "Existing mission log compatibility layer."),
        ])
    elif bot_id == "BOT-010":
        files.extend([
            ("registry/Crew-Registry.md", "Authoritative crew status and source files."),
            ("specialists/core-crew/", "Active and designed core specialist charters."),
            ("specialists/future-crew/", "Future specialist charters."),
            ("knowledge/architecture/shared/Specialist-Data-Model.md", "Expected shared data model if present."),
            ("command/Mission-Routing-Matrix.md", "Mission type to specialist routing rules."),
        ])
    else:
        files.extend([
            ("knowledge/Commander-Knowledge-Index.md", "Repository navigation map."),
            ("knowledge/Source-of-Truth-Matrix.md", "Best source for each knowledge domain."),
            ("command/Command-Knowledge-Sources.md", "Commander context source guidance."),
        ])

    return files


def placement_recommendation(user_text: str) -> tuple[str, str]:
    text = user_text.lower()

    if "specialist" in text and "charter" in text:
        return (
            "specialists/future-crew/ for planned or draft specialists; specialists/core-crew/ once active or runtime-ready.",
            "Specialist charters live under specialists/, and the crew registry records status and source file location.",
        )

    if "mission" in text:
        return (
            "missions/ for canonical mission records; Missions/ is retained for existing runtime-generated mission logs.",
            "Mission source-of-truth is defined by the Source-of-Truth Matrix and BOT-009 preserves logger compatibility.",
        )

    if "architecture" in text or "bot-" in text.lower():
        return (
            "knowledge/architecture/<BOT-ID>/",
            "Architecture specifications, requirements and acceptance tests are grouped by BOT capability.",
        )

    return (
        "Use the Source-of-Truth Matrix to choose the authoritative folder before creating the file.",
        "The repository has topic-owned folders rather than a single general documents area.",
    )


def format_sources(context: dict) -> list[str]:
    lines = []
    for source, content in context["documents"].items():
        status = "available" if content else "missing"
        lines.append(f"- `{source}` ({status})")
    for warning in context["warnings"]:
        lines.append(f"- Warning: {warning}")
    return lines


def answer_repository_awareness_request(user_text: str) -> str:
    text = user_text.lower()
    context = load_repository_context()

    if any(secret in text for secret in [".env", "api key", "token", "secret"]):
        return "\n".join([
            "# REPOSITORY AWARENESS RESPONSE",
            "",
            "## Request Summary",
            "",
            "A protected configuration or secret was requested.",
            "",
            "## Assessment",
            "",
            "Commander will not read or expose `.env`, `.venv/`, API keys, Slack tokens, or other credentials.",
            "",
            "## Recommendation",
            "",
            "Use documented configuration checks without printing secret values.",
        ])

    if "folders exist" in text or "what folders" in text or "repository structure" in text:
        folders = sorted(set(list_top_level_folders() + EXPECTED_FOLDERS))
        strengths = [
            "Core knowledge domains are separated into command, registry, knowledge, specialists, missions and runtime code.",
            "Testing and Slack runtime documentation are present as first-class folders.",
        ]
        risks = []
        if "REPOSITORY-MAP.md" in context["warnings"][0:] or not context["documents"].get("REPOSITORY-MAP.md"):
            risks.append("`REPOSITORY-MAP.md` is missing, so folder assessment is based on the live tree and catalogue.")
        if "testing/" not in folders:
            risks.append("`testing/` is expected by BOT-008 but was not found.")

        return "\n".join([
            "# REPOSITORY AWARENESS RESPONSE",
            "",
            "## Request Summary",
            "",
            "Review USS TJR repository structure.",
            "",
            "## Relevant Repository Areas",
            "",
            *(f"- `{folder}`" for folder in folders),
            "",
            "## Source Documents Consulted",
            "",
            *format_sources(context),
            "",
            "## Assessment",
            "",
            "Strengths:",
            *(f"- {item}" for item in strengths),
            "",
            "Risks:",
            *(f"- {item}" for item in (risks or ["No blocking repository structure risks found from available local context."])),
            "",
            "## Recommendation",
            "",
            "Keep source-of-truth records in `registry/`, runtime code in `slack-bot/`, capability architecture in `knowledge/architecture/`, and validation coverage in `testing/`.",
            "",
            "Recommended improvements:",
            "",
            "- Keep expected folder casing consistent, especially `missions/` versus existing runtime `Missions/` logs.",
            "- Maintain one authoritative repository map once `REPOSITORY-MAP.md` is restored.",
            "",
            "## Next Actions",
            "",
            "- Add or restore `REPOSITORY-MAP.md` if it is intended to be authoritative.",
            "- Keep `knowledge/Repository-Catalogue.md` aligned with any new top-level folders.",
        ])

    if "source of truth" in text:
        topic = "Crew" if "crew" in text or "specialist" in text else "Knowledge"
        source = source_for_topic(topic) or "No matching source-of-truth entry found."
        return "\n".join([
            "# REPOSITORY AWARENESS RESPONSE",
            "",
            "## Request Summary",
            "",
            f"Identify the source of truth for {topic.lower()}.",
            "",
            "## Source Documents Consulted",
            "",
            *format_sources(context),
            "",
            "## Assessment",
            "",
            f"The source of truth for {topic.lower()} is `{source}`.",
            "",
            "## Recommendation",
            "",
            "Use the source-of-truth file first, then supporting specialist or knowledge files as needed.",
        ])

    if "codex" in text or "read before implementing" in text:
        files = codex_reading_list(user_text)
        return "\n".join([
            "# REPOSITORY AWARENESS RESPONSE",
            "",
            "## Request Summary",
            "",
            "Recommend a Codex reading list for implementation work.",
            "",
            "## Source Documents Consulted",
            "",
            *format_sources(context),
            "",
            "## Recommendation",
            "",
            *(f"- `{path}` - {reason}" for path, reason in files),
            "",
            "## Next Actions",
            "",
            "- Read capability architecture first, then runtime modules, then acceptance tests.",
        ])

    if "where should i put" in text or "where do i put" in text:
        destination, reason = placement_recommendation(user_text)
        return "\n".join([
            "# REPOSITORY AWARENESS RESPONSE",
            "",
            "## Request Summary",
            "",
            "Recommend a repository location for a new file.",
            "",
            "## Source Documents Consulted",
            "",
            *format_sources(context),
            "",
            "## Recommendation",
            "",
            destination,
            "",
            "## Assessment",
            "",
            reason,
        ])

    return "\n".join([
        "# REPOSITORY AWARENESS RESPONSE",
        "",
        "## Request Summary",
        "",
        user_text.strip(),
        "",
        "## Relevant Repository Areas",
        "",
        *(f"- `{folder}`" for folder in EXPECTED_FOLDERS),
        "",
        "## Source Documents Consulted",
        "",
        *format_sources(context),
        "",
        "## Recommendation",
        "",
        "Use repository catalogue and source-of-truth records before making placement or implementation decisions.",
    ])
