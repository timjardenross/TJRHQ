def route_request(user_text: str) -> dict:
    text = user_text.lower()

    assigned_specialists = []
    domain = "Command"

    issue_triggers = [
        "github issue",
        "create issue",
        "draft issue",
        "issue for",
        "backlog item",
        "acceptance criteria",
        "codex task",
    ]

    testing_triggers = ["test", "qa", "validate", "validation", "quality", "acceptance"]

    if any(phrase in text for phrase in issue_triggers):
        assigned_specialists = [
            "Chief of Staff",
            "Chief Engineer",
            "Coder Agent",
            "Knowledge Officer",
        ]
        domain = "Engineering"

        if any(word in text for word in testing_triggers):
            assigned_specialists.append("QA & Test Officer")

        return {
            "mission_domain": domain,
            "assigned_specialists": assigned_specialists,
            "priority": "P3 – Normal",
            "status": "Active",
        }

    if any(word in text for word in ["priority", "focus", "plan", "roadmap", "strategy"]):
        assigned_specialists.append("Chief of Staff")
        domain = "Command"

    if any(word in text for word in ["architecture", "repo", "repository", "system", "technical", "security"]):
        assigned_specialists.append("Chief Engineer")
        domain = "Engineering"

    if any(word in text for word in ["code", "bug", "build", "implement", "fix", "feature"]):
        assigned_specialists.append("Coder Agent")
        domain = "Engineering"

    if any(word in text for word in ["document", "knowledge", "folder", "structure", "registry", "log"]):
        assigned_specialists.append("Knowledge Officer")
        domain = "Knowledge"

    if any(word in text for word in testing_triggers):
        assigned_specialists.append("QA & Test Officer")
        domain = "Engineering"

    if not assigned_specialists:
        assigned_specialists.append("Chief of Staff")

    return {
        "mission_domain": domain,
        "assigned_specialists": assigned_specialists,
        "priority": "P3 – Normal",
        "status": "Active",
    }
