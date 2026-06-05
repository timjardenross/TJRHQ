from datetime import datetime

from specialist_registry import load_specialist_profiles, read_markdown

MAX_COLLABORATION_SPECIALISTS = 4
ENABLE_SPECIALIST_COLLABORATION = True

COLLABORATION_TRIGGERS = [
    "assessment",
    "assess",
    "review",
    "recommendation",
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
    "trade-off",
    "tradeoff",
]

DEFAULT_COLLABORATION_CREW = [
    "Chief of Staff",
    "Chief Engineer",
    "Knowledge Officer",
    "QA & Test Officer",
]

SPECIALIST_FOCUS = {
    "Chief of Staff": "Strategic alignment, priority, effort, sequencing, risks, and recommendation.",
    "Chief Engineer": "Architecture, technical dependencies, security, maintainability, and technical debt.",
    "Coder Agent": "Implementation approach, files likely affected, build steps, and technical risks.",
    "Knowledge Officer": "Documentation, knowledge structure, registry updates, mission logs, and governance records.",
    "QA & Test Officer": "Testability, acceptance criteria, validation, regression risk, and user journey.",
}


def should_use_collaboration(user_text: str, assigned_specialists: list) -> bool:
    if not ENABLE_SPECIALIST_COLLABORATION:
        return False

    text = user_text.lower()
    has_collaboration_trigger = any(trigger in text for trigger in COLLABORATION_TRIGGERS)
    has_multiple_specialists = len(set(assigned_specialists)) > 1

    return has_multiple_specialists or has_collaboration_trigger


def select_collaboration_specialists(user_text: str, assigned_specialists: list) -> list:
    text = user_text.lower()
    selected = []

    for specialist in assigned_specialists:
        if specialist != "Commander TJR" and specialist not in selected:
            selected.append(specialist)

    if any(trigger in text for trigger in ["should we", "what next", "review", "recommend", "roadmap", "priority", "plan", "strategy"]):
        for specialist in DEFAULT_COLLABORATION_CREW:
            if specialist not in selected:
                selected.append(specialist)

    if "build" in text or "implement" in text or "code" in text or "feature" in text:
        if "Coder Agent" not in selected:
            selected.append("Coder Agent")

    return selected[:MAX_COLLABORATION_SPECIALISTS]


def build_specialist_prompt(
    specialist_name: str,
    specialist_profile: str,
    commander_context: str,
    user_text: str,
    routing: dict,
) -> str:
    focus = SPECIALIST_FOCUS.get(specialist_name, "Assess only within your defined USS TJR specialist domain.")

    return f"""
You are acting as the USS TJR specialist: {specialist_name}.

Specialist Profile:
{specialist_profile}

Mission Context:
- Mission Domain: {routing['mission_domain']}
- Assigned Specialists: {', '.join(routing['assigned_specialists'])}

Captain TJR Request:
{user_text}

Focus:
{focus}

Instructions:
- Respond only within your domain.
- Provide assessment, risks, recommendation, and practical next actions.
- Do not claim to have opened GitHub, created issues, changed files, deployed code, accessed private systems, or executed external actions.
- Do not expose secrets, tokens, API keys, environment variables, or .env contents.
- Keep the response concise and useful for Commander TJR synthesis.
"""


def get_specialist_response(
    specialist_name: str,
    specialist_profile: str,
    commander_context: str,
    user_text: str,
    routing: dict,
) -> str:
    from llm import ask_commander

    prompt = build_specialist_prompt(
        specialist_name=specialist_name,
        specialist_profile=specialist_profile,
        commander_context=commander_context,
        user_text=user_text,
        routing=routing,
    )

    return ask_commander(
        system_prompt=commander_context,
        user_prompt=prompt,
    )


def build_synthesis_prompt(user_text: str, routing: dict, specialist_responses: dict) -> str:
    specialist_sections = "\n\n".join(
        f"## {name}\n{response}"
        for name, response in specialist_responses.items()
    )

    return f"""
Captain TJR Request:
{user_text}

Mission Domain:
{routing['mission_domain']}

Specialist Inputs:
{specialist_sections}

Create a consolidated Commander TJR synthesis.

Requirements:
- Provide a clear recommendation.
- Reflect trade-offs and risks.
- Include practical next actions.
- Do not claim external actions were performed.
- Do not expose secrets.
- Keep the synthesis concise.
"""


def build_collaboration_response(
    user_text: str,
    routing: dict,
    specialist_responses: dict,
    commander_context: str = "",
) -> str:
    from llm import ask_commander

    mission_id = f"M-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    synthesis_prompt = build_synthesis_prompt(user_text, routing, specialist_responses)
    synthesis = ask_commander(
        system_prompt=commander_context,
        user_prompt=synthesis_prompt,
    )
    specialist_names = list(specialist_responses.keys())

    specialist_sections = "\n\n".join(
        f"## {name}\n\n{response}"
        for name, response in specialist_responses.items()
    )

    return f"""
# MISSION SUMMARY

Mission ID: {mission_id}

Mission Domain: {routing['mission_domain']}

Assigned Specialists:
{chr(10).join(f'- {name}' for name in specialist_names)}

Priority: {routing['priority']}

Status: Completed

---

# SPECIALIST INPUTS

{specialist_sections}

---

# COMMANDER SYNTHESIS

{synthesis}

---

# RECOMMENDED NEXT ACTIONS

1. Confirm the preferred direction.
2. Create or update the relevant mission/backlog item.
3. Assign implementation, documentation, and validation work to the appropriate specialist path.

---

# MISSION STATUS

Completed
"""


def run_collaboration(user_text: str, routing: dict, commander_context: str) -> str:
    profiles = load_specialist_profiles()
    selected_specialists = select_collaboration_specialists(
        user_text=user_text,
        assigned_specialists=routing["assigned_specialists"],
    )
    selected_specialists = [
        specialist
        for specialist in selected_specialists
        if specialist in profiles
    ]

    if not selected_specialists:
        selected_specialists = ["Chief of Staff"]

    routing = {
        **routing,
        "assigned_specialists": selected_specialists,
    }
    specialist_responses = {}

    for specialist_name in selected_specialists:
        profile = profiles[specialist_name]
        specialist_profile = read_markdown(profile["source"])
        specialist_responses[specialist_name] = get_specialist_response(
            specialist_name=specialist_name,
            specialist_profile=specialist_profile,
            commander_context=commander_context,
            user_text=user_text,
            routing=routing,
        )

    return build_collaboration_response(
        user_text=user_text,
        routing=routing,
        specialist_responses=specialist_responses,
        commander_context=commander_context,
    )
