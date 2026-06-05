from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def read_markdown(relative_path: str) -> str:
    file_path = BASE_DIR / relative_path

    if not file_path.exists():
        return f"[Missing file: {relative_path}]"

    return file_path.read_text(encoding="utf-8")


def load_commander_context() -> str:
    commander = read_markdown("command/Commander-TJR.md")
    charter = read_markdown("registry/USS-TJR-Charter.md")
    crew_registry = read_markdown("specialists/Crew-Registry.md")

    chief_of_staff = read_markdown("specialists/core-crew/Chief-of-Staff.md")
    chief_engineer = read_markdown("specialists/core-crew/Chief-Engineer.md")
    coder_agent = read_markdown("specialists/core-crew/Coder-Agent.md")
    knowledge_officer = read_markdown("specialists/core-crew/Knowledge-Officer.md")
    qa_test_officer = read_markdown("specialists/core-crew/QA-Test-Officer.md")

    return f"""
# USS TJR COMMAND CONTEXT

## Commander TJR
{commander}

## USS TJR Charter
{charter}

## Crew Registry
{crew_registry}

## Specialist Profiles

### Chief of Staff
{chief_of_staff}

### Chief Engineer
{chief_engineer}

### Coder Agent
{coder_agent}

### Knowledge Officer
{knowledge_officer}

### QA & Test Officer
{qa_test_officer}
"""
