"""Commander TJR request router — P3-002 Confidence-Based Routing.

Replaces the original keyword-only routing with a scored, multi-signal
approach. Each specialist accumulates confidence from matching signals
across their domain. The highest-scoring specialists are selected.

All original priority routing (GitHub, mission, knowledge, collaboration)
is preserved and takes precedence over the scored fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from specialist_registry import match_specialists_to_request
from github_awareness import is_github_awareness_request
from mission_registry import is_mission_registry_request
from repository_awareness import is_repository_awareness_request
from knowledge_retrieval import is_knowledge_retrieval_request, identify_knowledge_domain
from mission_executor import is_mission_execution_request


# ---------------------------------------------------------------------------
# Confidence scoring model
# ---------------------------------------------------------------------------

@dataclass
class SpecialistScore:
    specialist: str
    score: int = 0
    signals_matched: list[str] = field(default_factory=list)

    def add(self, signal: str, weight: int) -> None:
        self.score += weight
        self.signals_matched.append(signal)


# Signal tables: (signal_text, weight)
# Higher weight = stronger evidence for this specialist
_SIGNALS: dict[str, list[tuple[str, int]]] = {
    "Chief of Staff": [
        # Strategic / decision framing (highest weight)
        ("should we prioritise", 25),
        ("should we invest", 25),
        ("should uss tjr", 20),
        ("should we proceed", 20),
        ("should we defer", 20),
        ("strategic", 20),
        ("bottleneck", 20),
        ("current priority", 20),
        ("what is the current", 15),
        ("what should we focus", 15),
        # Mission / planning domain
        ("priority", 15),
        ("roadmap", 15),
        ("plan", 12),
        ("sequence", 12),
        ("mission", 12),
        ("sprint", 12),
        ("backlog", 12),
        ("governance", 10),
        # Ownership / governance — boosted above architecture weight (20) so governance questions win
        ("who owns", 25),
        ("who approves", 25),
        ("who decides", 25),
        ("who should own", 25),
        ("who should approve", 25),
        ("who should", 15),
        ("ownership", 15),
        ("approval authority", 20),
    ],
    "Chief Engineer": [
        # USS TJR specific architectural concerns
        ("voice core", 20),
        ("slack runtime", 18),
        ("supabase runtime", 18),
        ("commander runtime", 18),
        # Architecture / design framing
        ("where should this", 20),
        ("where does this", 20),
        ("how should this service", 20),
        ("how should this component", 20),
        # Domain signals
        ("architecture", 20),
        ("system design", 18),
        ("infrastructure", 15),
        ("supabase", 15),
        ("database", 12),
        ("api", 12),
        ("integration", 12),
        ("security", 12),
        ("deployment", 12),
        ("technical", 12),
        ("repository", 10),
        ("runtime", 10),
        ("service", 10),
        ("component", 10),
        ("schema", 10),
        ("migration", 10),
    ],
    "Coder Agent": [
        ("implement", 18),
        ("implementation", 15),
        ("code", 15),
        ("bug", 15),
        ("fix", 12),
        ("build", 12),
        ("feature", 12),
        ("refactor", 12),
        ("function", 10),
        ("script", 10),
        ("module", 10),
        ("test coverage", 12),
    ],
    "Knowledge Officer": [
        ("source of truth", 20),
        ("knowledge", 15),
        ("documentation", 15),
        ("document", 12),
        ("notion", 12),
        ("memory", 12),
        ("registry", 12),
        ("archive", 12),
        ("information architecture", 15),
        ("structure", 10),
        ("folder", 10),
    ],
    "QA & Test Officer": [
        ("test", 15),
        ("qa", 18),
        ("quality", 15),
        ("validate", 15),
        ("validation", 15),
        ("acceptance criteria", 18),
        ("regression", 15),
        ("defect", 15),
        ("release", 12),
    ],
    "Research Officer": [
        ("research", 18),
        ("evidence", 15),
        ("source", 12),
        ("literature", 12),
        ("study", 12),
        ("analysis", 10),
        ("trend", 12),
        ("intelligence", 12),
        ("compare", 10),
    ],
    "Medical Officer": [
        ("health", 18),
        ("medical", 18),
        ("pain", 18),
        ("chronic pain", 25),
        ("recovery", 15),
        ("appointment", 18),
        ("wellbeing", 15),
        ("wellness", 15),
        ("symptom", 18),
        ("medication", 18),
        ("exercise", 12),
        ("sleep", 12),
        ("fatigue", 12),
    ],
    "UX Design Officer": [
        ("ux", 18),
        ("user experience", 20),
        ("usability", 18),
        ("accessibility", 15),
        ("workflow", 15),
        ("dashboard", 15),
        ("interface", 12),
        ("friction", 12),
        ("interaction", 10),
        ("navigation", 10),
    ],
}

_MIN_CONFIDENCE = 10
_MAX_SPECIALISTS = 4


def score_specialists(text: str) -> list[SpecialistScore]:
    """Score all specialists against a request. Returns ranked list above threshold."""
    lowered = text.lower()
    scores = {name: SpecialistScore(name) for name in _SIGNALS}
    for specialist, signals in _SIGNALS.items():
        for signal, weight in signals:
            if signal in lowered:
                scores[specialist].add(signal, weight)
    ranked = sorted(scores.values(), key=lambda s: s.score, reverse=True)
    return [s for s in ranked if s.score >= _MIN_CONFIDENCE]


def select_specialists(text: str, max_count: int = _MAX_SPECIALISTS) -> list[str]:
    """Select the best specialists using confidence scoring."""
    ranked = score_specialists(text)
    selected = [s.specialist for s in ranked[:max_count]]

    # Ensure Chief of Staff for genuine strategic/prioritisation questions
    # Deliberately narrow — "should we implement" is NOT strategic, "should we prioritise" IS
    strategic_markers = [
        "should we prioritise", "should we prioritize", "should we invest",
        "should we defer", "should we proceed with", "should uss tjr",
        "strategic priority", "strategic decision", "roadmap priority",
        "what is the bottleneck", "current bottleneck",
    ]
    if any(m in text.lower() for m in strategic_markers) and "Chief of Staff" not in selected:
        selected = ["Chief of Staff"] + selected[:max_count - 1]

    return selected or ["Chief of Staff"]


def _domain(specialists: list[str]) -> str:
    if "Medical Officer" in specialists:
        return "Health & Wellbeing"
    if "Chief Engineer" in specialists and "Chief of Staff" in specialists:
        return "Command / Engineering"
    if "Chief Engineer" in specialists:
        return "Engineering"
    if "Chief of Staff" in specialists:
        return "Command"
    if "Knowledge Officer" in specialists:
        return "Knowledge"
    if "UX Design Officer" in specialists:
        return "Design"
    if "QA & Test Officer" in specialists:
        return "Quality"
    return "Command"


def _priority(specialists: list[str], text: str) -> str:
    lowered = text.lower()
    if any(w in lowered for w in ["urgent", "critical", "asap", "p0", "blocked", "emergency"]):
        return "P0 – Critical"
    if any(w in lowered for w in ["priority", "important", "must", "p1"]):
        return "P1 – High"
    return "P3 – Normal"


def _build(domain: str, specialists: list[str], user_text: str) -> dict[str, Any]:
    return {
        "mission_domain": domain,
        "assigned_specialists": specialists,
        "priority": _priority(specialists, user_text),
        "status": "Active",
    }


# ---------------------------------------------------------------------------
# Public routing entry point
# ---------------------------------------------------------------------------

def route_request(user_text: str) -> dict[str, Any]:
    """Route a Commander request. Priority-ordered with confidence fallback."""
    text = user_text.lower()

    # 1. GitHub issue generation
    issue_triggers = [
        "github issue", "create issue", "draft issue", "issue for",
        "backlog item", "acceptance criteria", "codex task",
    ]
    if any(p in text for p in issue_triggers):
        specs = ["Chief of Staff", "Chief Engineer", "Coder Agent", "Knowledge Officer"]
        if any(w in text for w in ["test", "qa", "validate", "quality", "acceptance"]):
            specs.append("QA & Test Officer")
        return _build("Engineering", specs, user_text)

    # 2. GitHub repository awareness
    if is_github_awareness_request(user_text):
        return _build("Engineering", ["Chief Engineer", "Knowledge Officer", "Chief of Staff"], user_text)

    # 3. Mission execution
    if is_mission_execution_request(user_text):
        return _build("Mission Execution", ["Chief of Staff", "Knowledge Officer"], user_text)

    # 4. Mission registry
    if is_mission_registry_request(user_text):
        return _build("Command", ["Chief of Staff", "Knowledge Officer"], user_text)

    # 5. Repository awareness
    if is_repository_awareness_request(user_text):
        return _build("Knowledge / Engineering", ["Knowledge Officer", "Chief Engineer"], user_text)

    # 6. Knowledge retrieval
    if is_knowledge_retrieval_request(user_text):
        kd = identify_knowledge_domain(user_text)
        specs = ["Knowledge Officer"]
        if kd in ("architecture", "runtime", "capabilities"):
            specs.append("Chief Engineer")
        if kd in ("missions", "procedures", "governance", "directives"):
            specs.append("Chief of Staff")
        return _build(f"Knowledge / {kd.title()}", specs, user_text)

    # 7. Mission history (use whole-phrase matching to avoid substring collisions)
    history_triggers = [
        "active missions", "recent missions", "mission history", "completed missions",
        "mission status", "what missions", "show missions",
        "mission logs", "mission summary", "today's work", "todays work", "weekly summary",
    ]
    # "show mission" and "mission log" need word-boundary protection
    _history_match = any(p in text for p in history_triggers) or \
        "show mission " in text or \
        text.startswith("show mission") or \
        (" mission log " in text) or \
        text.endswith(" mission log")
    if _history_match:
        return _build("Knowledge", ["Knowledge Officer"], user_text)

    # 8. Confidence-scored routing (P3-002)
    specialists = select_specialists(user_text)
    if not specialists or specialists == ["Chief of Staff"]:
        matched = [p["title"] for p in match_specialists_to_request(user_text)]
        if matched:
            specialists = matched[:_MAX_SPECIALISTS]
    if not specialists:
        specialists = ["Chief of Staff"]

    return _build(_domain(specialists), specialists, user_text)
