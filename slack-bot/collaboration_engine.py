from datetime import datetime

from specialist_registry import load_specialist_profiles

ENABLE_SPECIALIST_COLLABORATION = True

COLLABORATION_TRIGGERS = [
    "assessment",
    "assess",
    "review",
    "recommendation",
    "recommend",
    "roadmap",
    "strategy",
    "proposal",
    "framework",
    "major strategic decision",
    "governance decision",
]

MISSION_TYPE_RULES = [
    ("Health & Wellness Review", ["chronic pain", "health", "medical", "wellness", "coaching", "recovery"]),
    ("Architecture Review", ["architecture", "technical architecture", "system architecture"]),
    ("Technical Design", ["technical design", "design", "implementation design", "voice core"]),
    ("Knowledge Review", ["repository structure", "knowledge", "documentation", "source of truth", "information architecture"]),
    ("Strategic Planning", ["strategy", "strategic", "roadmap", "major strategic decision", "priority"]),
    ("Roadmap Review", ["roadmap"]),
    ("Research Review", ["research", "evidence", "source review"]),
    ("Governance Review", ["governance", "standard", "policy", "decision rights"]),
    ("Operational Review", ["operational", "operations", "rhythm", "process"]),
]

TEAM_BY_MISSION_TYPE = {
    "Architecture Review": ["Chief Engineer", "QA & Test Officer", "Knowledge Officer"],
    "Technical Design": ["Chief Engineer", "QA & Test Officer", "Knowledge Officer"],
    "Knowledge Review": ["Knowledge Officer", "Chief of Staff"],
    "Strategic Planning": ["Chief of Staff", "Operations Officer"],
    "Roadmap Review": ["Chief of Staff", "Operations Officer"],
    "Health & Wellness Review": ["Medical Officer", "Research Officer"],
    "Research Review": ["Research Officer", "Knowledge Officer"],
    "Governance Review": ["Chief of Staff", "Knowledge Officer"],
    "Operational Review": ["Chief of Staff", "Operations Officer", "Knowledge Officer"],
    "General Mission": ["Chief of Staff", "Knowledge Officer"],
}

SPECIALIST_LENSES = {
    "Chief of Staff": "strategic alignment, priority, sequencing, escalation and decision ownership",
    "Chief Engineer": "architecture, technical dependencies, security, maintainability and integration risk",
    "Coder Agent": "implementation path, likely files, build complexity and development risk",
    "Knowledge Officer": "source-of-truth discipline, documentation structure, registry impact and knowledge reuse",
    "QA & Test Officer": "testability, acceptance criteria, validation plan and regression risk",
    "Research Officer": "evidence quality, assumptions, source validation and unanswered research questions",
    "Medical Officer": "health boundaries, wellbeing impact, recovery safety and non-clinical support framing",
    "Operations Officer": "operational cadence, handoffs, execution rhythm and follow-through",
}

SPECIALIST_RECOMMENDATIONS = {
    "Chief of Staff": "Proceed only after the decision owner, priority and next mission are explicit.",
    "Chief Engineer": "Prefer a small, reversible design step before committing to broader architecture changes.",
    "Coder Agent": "Convert the chosen direction into a scoped implementation task with acceptance criteria.",
    "Knowledge Officer": "Update the relevant source-of-truth document and keep repository placement explicit.",
    "QA & Test Officer": "Define validation checks before implementation begins.",
    "Research Officer": "Separate known facts from assumptions and capture source gaps.",
    "Medical Officer": "Keep guidance supportive and non-clinical, with escalation to qualified care where needed.",
    "Operations Officer": "Turn the recommendation into a clear cadence, owner and follow-up checkpoint.",
}

SPECIALIST_RISKS = {
    "Chief of Staff": "Unclear ownership or priority could create busy work instead of mission progress.",
    "Chief Engineer": "Architecture decisions made too early could increase coupling or future migration cost.",
    "Coder Agent": "Implementation may sprawl if the first build slice is not tightly scoped.",
    "Knowledge Officer": "Knowledge may fragment if source documents are not updated alongside the decision.",
    "QA & Test Officer": "Missing acceptance tests could hide regressions.",
    "Research Officer": "Weak evidence or uncaptured assumptions could make the recommendation brittle.",
    "Medical Officer": "Health-related advice must not drift into diagnosis or treatment instructions.",
    "Operations Officer": "Good intent may stall without a repeatable operating rhythm.",
}


def is_secret_request(user_text: str) -> bool:
    text = user_text.lower()
    return any(term in text for term in [".env", "api key", "token", "secret", "credential", ".venv"])


def classify_mission_type(user_text: str) -> str:
    text = user_text.lower()
    for mission_type, keywords in MISSION_TYPE_RULES:
        if any(keyword in text for keyword in keywords):
            return mission_type
    return "General Mission"


def select_specialists(mission_type: str) -> list:
    profiles = load_specialist_profiles()
    desired_team = TEAM_BY_MISSION_TYPE.get(mission_type, TEAM_BY_MISSION_TYPE["General Mission"])
    available_team = [name for name in desired_team if name in profiles]

    if available_team:
        return available_team

    fallback = [name for name in ["Chief of Staff", "Knowledge Officer"] if name in profiles]
    return fallback or list(profiles.keys())[:1]


def assign_mission_owner(team: list) -> str:
    if not team:
        return "Chief of Staff"
    return team[0]


def display_specialist_name(name: str) -> str:
    if name == "QA & Test Officer":
        return "QA Officer (QA & Test Officer)"
    return name


def should_use_collaboration(user_text: str, assigned_specialists: list = None) -> bool:
    if not ENABLE_SPECIALIST_COLLABORATION:
        return False
    if is_secret_request(user_text):
        return False

    text = user_text.lower()
    has_trigger = any(trigger in text for trigger in COLLABORATION_TRIGGERS)
    has_multiple_specialists = len(set(assigned_specialists or [])) > 1
    return has_trigger or has_multiple_specialists


def generate_specialist_perspective(specialist: dict, request: str, context: dict = None) -> dict:
    title = specialist["title"]
    lens = SPECIALIST_LENSES.get(title, specialist.get("mission") or "their defined USS TJR domain")
    recommendation = SPECIALIST_RECOMMENDATIONS.get(title, "Proceed with a small, reviewable next step.")
    risk = SPECIALIST_RISKS.get(title, "The specialist profile is limited, so perspective confidence is reduced.")

    return {
        "specialist": title,
        "perspective": (
            f"{display_specialist_name(title)} reviews this through {lens}. "
            f"For this request, the key concern is keeping the work scoped, grounded and owned."
        ),
        "recommendation": recommendation,
        "risk": risk,
        "source": specialist.get("source", "Unknown source"),
    }


def synthesise_recommendation(perspectives: list) -> str:
    specialist_names = [display_specialist_name(item["specialist"]) for item in perspectives]
    if not specialist_names:
        return "Route to Chief of Staff for triage before proceeding."

    return (
        f"Proceed with a small, explicitly owned review led by {specialist_names[0]}, "
        f"using {', '.join(specialist_names[1:]) or 'Commander TJR'} for supporting checks. "
        "Capture the decision, risks and validation criteria before implementation or broader rollout."
    )


def collect_risks(perspectives: list, request: str) -> list:
    risks = []
    for item in perspectives:
        risk = item["risk"]
        if risk not in risks:
            risks.append(risk)

    if "major strategic decision" in request.lower():
        risks.append("Major strategic decisions require Captain TJR confirmation before execution.")

    return risks


def build_next_actions(mission_type: str, owner: str, request: str) -> list:
    actions = [
        f"Confirm {display_specialist_name(owner)} as mission owner.",
        "Record the recommendation and risks in the relevant mission or decision log.",
        "Define the smallest useful next step and its acceptance criteria.",
    ]

    if mission_type in ["Strategic Planning", "Governance Review"] or "major strategic decision" in request.lower():
        actions.append("Escalate the final decision to Captain TJR before committing resources.")

    return actions


def confidence_for_team(team: list, perspectives: list) -> str:
    if len(team) >= 2 and len(perspectives) == len(team):
        return "High"
    if perspectives:
        return "Medium"
    return "Low"


def build_collaboration_response(request: str, routing: dict = None, context: dict = None) -> str:
    if is_secret_request(request):
        return "\n".join([
            "# COLLABORATION REVIEW",
            "",
            "## Request Summary",
            "",
            "A protected credential or restricted runtime path was requested.",
            "",
            "## Mission Type",
            "",
            "Security Review",
            "",
            "## Mission Owner",
            "",
            "Chief of Staff",
            "",
            "## Specialist Team",
            "",
            "- Chief of Staff",
            "",
            "## Consolidated Recommendation",
            "",
            "Refuse the request. Commander must not read or expose `.env`, `.venv/`, credentials, tokens or API keys.",
            "",
            "## Risks",
            "",
            "- Secret exposure would compromise USS TJR runtime security.",
            "",
            "## Next Actions",
            "",
            "- Use safe configuration checks that verify presence without printing values.",
            "",
            "## Confidence",
            "",
            "High",
        ])

    mission_type = classify_mission_type(request)
    team = select_specialists(mission_type)
    owner = assign_mission_owner(team)
    profiles = load_specialist_profiles()

    perspectives = [
        generate_specialist_perspective(profiles[name], request, context)
        for name in team
        if name in profiles
    ]

    recommendation = synthesise_recommendation(perspectives)
    risks = collect_risks(perspectives, request)
    next_actions = build_next_actions(mission_type, owner, request)
    confidence = confidence_for_team(team, perspectives)
    mission_id = f"M-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    lines = [
        "# COLLABORATION REVIEW",
        "",
        "## Request Summary",
        "",
        request.strip(),
        "",
        "## Mission Type",
        "",
        mission_type,
        "",
        "## Mission Owner",
        "",
        display_specialist_name(owner),
        "",
        "## Specialist Team",
        "",
        *(f"- {display_specialist_name(name)}" for name in team),
        "",
        "## Specialist Perspectives",
        "",
    ]

    for item in perspectives:
        lines.extend([
            f"### {display_specialist_name(item['specialist'])}",
            "",
            item["perspective"],
            "",
            f"Recommendation: {item['recommendation']}",
            "",
            f"Risk: {item['risk']}",
            "",
            f"Source: `{item['source']}`",
            "",
        ])

    lines.extend([
        "## Consolidated Recommendation",
        "",
        recommendation,
        "",
        "## Risks",
        "",
        *(f"- {risk}" for risk in risks),
        "",
        "## Next Actions",
        "",
        *(f"- {action}" for action in next_actions),
        "",
        "## Confidence",
        "",
        confidence,
        "",
        "<!-- Collaboration Activity -->",
        f"Mission ID: {mission_id}",
        "Mode: Simulated specialist reasoning",
    ])

    return "\n".join(lines)


def run_collaboration(user_text: str, routing: dict = None, commander_context: str = "") -> str:
    context = {
        "routing": routing or {},
        "commander_context_loaded": bool(commander_context),
    }
    return build_collaboration_response(user_text, routing=routing, context=context)
