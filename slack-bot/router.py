from specialist_registry import match_specialists_to_request
from github_awareness import is_github_awareness_request
from mission_registry import is_mission_registry_request
from repository_awareness import is_repository_awareness_request
from knowledge_retrieval import is_knowledge_retrieval_request, identify_knowledge_domain
from mission_executor import is_mission_execution_request


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
    collaboration_triggers = [
        "assessment",
        "assess",
        "review",
        "recommend",
        "roadmap",
        "priority",
        "prioritise",
        "prioritize",
        "design",
        "architecture",
        "strategy",
        "should we",
        "what next",
        "plan",
    ]
    mission_history_triggers = [
        "active missions",
        "recent missions",
        "mission history",
        "completed missions",
        "mission status",
        "what missions",
        "show missions",
        "show mission",
        "mission log",
        "mission summary",
        "today's work",
        "todays work",
        "weekly summary",
    ]

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

    if is_github_awareness_request(user_text):
        return {
            "mission_domain": "Engineering",
            "assigned_specialists": [
                "Chief Engineer",
                "Knowledge Officer",
                "Chief of Staff",
            ],
            "priority": "P3 – Normal",
            "status": "Active",
        }

    if is_mission_execution_request(user_text):
        return {
            "mission_domain": "Mission Execution",
            "assigned_specialists": ["Chief of Staff", "Knowledge Officer"],
            "priority": "P3 – Normal",
            "status": "Active",
        }

    if is_mission_registry_request(user_text):
        return {
            "mission_domain": "Command",
            "assigned_specialists": ["Chief of Staff", "Knowledge Officer"],
            "priority": "P3 – Normal",
            "status": "Active",
        }

    if is_repository_awareness_request(user_text):
        return {
            "mission_domain": "Knowledge / Engineering",
            "assigned_specialists": ["Knowledge Officer", "Chief Engineer"],
            "priority": "P3 – Normal",
            "status": "Active",
        }

    if is_knowledge_retrieval_request(user_text):
        knowledge_domain = identify_knowledge_domain(user_text)
        specialists = ["Knowledge Officer"]
        if knowledge_domain in ["architecture", "runtime", "capabilities"]:
            specialists.append("Chief Engineer")
        if knowledge_domain in ["missions", "procedures", "governance", "directives"]:
            specialists.append("Chief of Staff")

        return {
            "mission_domain": f"Knowledge / {knowledge_domain.title()}",
            "assigned_specialists": specialists,
            "priority": "P3 – Normal",
            "status": "Active",
        }

    if any(phrase in text for phrase in mission_history_triggers):
        return {
            "mission_domain": "Knowledge",
            "assigned_specialists": ["Knowledge Officer"],
            "priority": "P3 – Normal",
            "status": "Active",
        }

    if any(phrase in text for phrase in collaboration_triggers):
        assigned_specialists = [
            "Chief of Staff",
            "Chief Engineer",
            "Knowledge Officer",
            "QA & Test Officer",
        ]
        domain = "Command / Engineering"

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
        assigned_specialists = [
            profile["title"]
            for profile in match_specialists_to_request(user_text)
        ]

    if not assigned_specialists:
        assigned_specialists = ["Chief of Staff"]

    return {
        "mission_domain": domain,
        "assigned_specialists": assigned_specialists,
        "priority": "P3 – Normal",
        "status": "Active",
    }
