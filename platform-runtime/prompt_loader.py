from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def read_markdown(relative_path: str) -> str:
    file_path = BASE_DIR / relative_path

    if not file_path.exists():
        return f"[Missing file: {relative_path}]"

    return file_path.read_text(encoding="utf-8")


def build_section(title: str, content: str) -> str:
    return f"\n\n# {title}\n\n{content}"


# -----------------------------
# Core + Memory Context
# -----------------------------

def load_core_context() -> str:
    return "".join([
        build_section("Commander TJR", read_markdown("command/Commander-TJR.md")),
        build_section("USS TJR Charter", read_markdown("registry/USS-TJR-Charter.md")),
        build_section("Crew Registry", read_markdown("registry/Crew-Registry.md")),
        build_section("Crew Authority Matrix", read_markdown("registry/Crew-Authority-Matrix.md")),
        build_section("Division Registry", read_markdown("registry/Division-Registry.md")),
    ])


def load_memory_context() -> str:
    return "".join([
        build_section("Crew Context", read_markdown("memory/Crew-Context.md")),
        build_section("Captain Profile", read_markdown("memory/Captain-Profile.md")),
        build_section("Active Priorities", read_markdown("memory/Active-Priorities.md")),
        build_section("Decision Register", read_markdown("memory/Decision-Register.md")),
        build_section("Active Missions", read_markdown("memory/Active-Missions.md")),
        build_section("Health Summary", read_markdown("memory/Health-Summary.md")),
    ])


# -----------------------------
# Specialist Context
# -----------------------------

SPECIALISTS = {
    "chief_of_staff": {
        "title": "Chief of Staff",
        "charter": "specialists/core-crew/Chief-of-Staff.md",
        "knowledge": [
            "specialists/knowledge-packs/Chief-of-Staff-Knowledge.md",
            "specialists/knowledge-packs/Priority-Management-Framework.md",
            "specialists/knowledge-packs/Mission-Coordination-Framework.md",
            "specialists/knowledge-packs/Weekly-Review-Framework.md",
            "specialists/knowledge-packs/Sprint-Planning-Framework.md",
        ],
    },
    "chief_engineer": {
        "title": "Chief Engineer",
        "charter": "specialists/core-crew/Chief-Engineer.md",
        "knowledge": [
            "specialists/knowledge-packs/Chief-Engineer-Knowledge.md",
            "specialists/knowledge-packs/Architecture-Review-Framework.md",
            "specialists/knowledge-packs/Technical-Debt-Framework.md",
            "specialists/knowledge-packs/Security-Review-Framework.md",
            "specialists/knowledge-packs/Engineering-Roadmap-Framework.md",
        ],
    },
    "coder_agent": {
        "title": "Coder Agent",
        "charter": "specialists/core-crew/Coder-Agent.md",
        "knowledge": [
            "specialists/knowledge-packs/Coder-Agent-Knowledge.md",
            "specialists/knowledge-packs/Python-Coding-Standards.md",
            "specialists/knowledge-packs/Git-Workflow-Standard.md",
            "specialists/knowledge-packs/Bug-Fix-Framework.md",
            "specialists/knowledge-packs/Code-Review-Checklist.md",
        ],
    },
    "qa_test_officer": {
        "title": "QA & Test Officer",
        "charter": "specialists/core-crew/QA-Test-Officer.md",
        "knowledge": [
            "specialists/knowledge-packs/QA-Test-Officer-Knowledge.md",
            "specialists/knowledge-packs/Testing-Strategy.md",
            "specialists/knowledge-packs/Release-Readiness-Framework.md",
            "specialists/knowledge-packs/Validation-Checklist.md",
        ],
    },
    "knowledge_officer": {
        "title": "Knowledge Officer",
        "charter": "specialists/core-crew/Knowledge-Officer.md",
        "knowledge": [
            "specialists/knowledge-packs/Knowledge-Officer-Knowledge.md",
            "specialists/knowledge-packs/Knowledge-Governance-Standard.md",
            "specialists/knowledge-packs/Documentation-Lifecycle.md",
            "specialists/knowledge-packs/Repository-Information-Architecture.md",
        ],
    },
    "research_officer": {
        "title": "Research Officer",
        "charter": "specialists/core-crew/Research-Officer.md",
        "knowledge": [
            "specialists/knowledge-packs/Research-Officer-Knowledge.md",
            "specialists/knowledge-packs/Research-Methodology.md",
            "specialists/knowledge-packs/Source-Evaluation-Framework.md",
            "specialists/knowledge-packs/Intelligence-Brief-Standard.md",
        ],
    },
    "medical_officer": {
        "title": "Human Systems Officer — Capacity & Decision Support Officer (Medical Officer)",
        "charter": "specialists/core-crew/Medical-Officer.md",
        "knowledge": [
            "specialists/knowledge-packs/Medical-Officer-Knowledge.md",
            "specialists/knowledge-packs/Human-Systems-Framework.md",
            "specialists/knowledge-packs/Chronic-Pain-Framework.md",
            "specialists/knowledge-packs/Recovery-Support-Framework.md",
            "specialists/knowledge-packs/Health-Escalation-Guidelines.md",
        ],
    },
    "design_officer": {
        "title": "Design Officer",
        "charter": "specialists/core-crew/UX-Design-Officer.md",
        "knowledge": [
            "specialists/knowledge-packs/UX-Design-Officer-Knowledge.md",
        ],
    },
    "visual_design_officer": {
        "title": "Visual Design Officer",
        "charter": "specialists/core-crew/Visual-Design-Officer.md",
        "knowledge": [],
    },
}


def load_specialist_context(specialist_key: str) -> str:
    specialist = SPECIALISTS.get(specialist_key)

    if not specialist:
        return f"[Unknown specialist: {specialist_key}]"

    context = build_section(
        specialist["title"],
        read_markdown(specialist["charter"])
    )

    for knowledge_file in specialist["knowledge"]:
        context += build_section(
            f"{specialist['title']} Knowledge",
            read_markdown(knowledge_file)
        )

    return context


# -----------------------------
# Public Loader Functions
# -----------------------------

def _load_hierarchy_section(text: str) -> str:
    """Return a hierarchy structural context section, or empty string if unavailable."""
    if not text:
        return ""
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _repo_root = str(_Path(__file__).resolve().parents[1])
        if _repo_root not in _sys.path:
            _sys.path.insert(0, _repo_root)
        from core.coordination.hierarchy_memory_adapter import HierarchyMemoryAdapter
        ctx = HierarchyMemoryAdapter().build_hierarchy_note(text=text)
        if ctx.found:
            return build_section("Structural Context", ctx.context_block.strip())
    except Exception:
        pass
    return ""


def load_commander_context(text: str = "") -> str:
    return f"""
# USS TJR COMMAND CONTEXT

{load_core_context()}

{load_memory_context()}
{_load_hierarchy_section(text)}
"""


def load_knowledge_retrieval_context() -> str:
    return "".join([
        build_section("Commander Context Pack", read_markdown("knowledge/Commander-Context-Pack.md")),
        build_section("Commander Knowledge Index", read_markdown("knowledge/Commander-Knowledge-Index.md")),
        build_section("Source of Truth Matrix", read_markdown("knowledge/Source-of-Truth-Matrix.md")),
        build_section("Repository Catalogue", read_markdown("knowledge/Repository-Catalogue.md")),
    ])


def load_commander_with_specialist_context(specialist_key: str) -> str:
    return f"""
# USS TJR COMMAND CONTEXT

{load_core_context()}

{load_memory_context()}

{load_specialist_context(specialist_key)}
"""


def load_engineering_context() -> str:
    return f"""
# USS TJR ENGINEERING DIVISION CONTEXT

{load_core_context()}

{load_memory_context()}

{load_specialist_context("chief_engineer")}

{load_specialist_context("coder_agent")}

{load_specialist_context("qa_test_officer")}
"""


def load_operations_context() -> str:
    return f"""
# USS TJR OPERATIONS DIVISION CONTEXT

{load_core_context()}

{load_memory_context()}

{load_specialist_context("chief_of_staff")}

{load_specialist_context("knowledge_officer")}

{load_specialist_context("research_officer")}
"""


def load_medical_context() -> str:
    return f"""
# USS TJR MEDICAL BAY CONTEXT

{load_core_context()}

{load_memory_context()}

{load_specialist_context("medical_officer")}
"""
