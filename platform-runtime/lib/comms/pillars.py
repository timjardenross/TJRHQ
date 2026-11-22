"""Thought Leadership Themes — strategic content pillars (COMMS-001 WP2).

Eight pillars, each with its audience, key messages, strategic value, and the
SPC-001 strategic domain it advances. Pure data + a whole-word keyword classifier so every
content opportunity aligns to a theme. No store, no network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache


@dataclass(frozen=True)
class Pillar:
    key: str
    name: str
    audience: str
    key_message: str
    strategic_value: str
    strategic_domain: str               # SPC-001 domain this pillar advances
    keywords: tuple[str, ...] = field(default_factory=tuple)


# The eight pillars (WP2). strategic_domain ties each back to MSN-SPC-001 so the
# weekly brief can show which long-term objective the content advances.
PILLARS: tuple[Pillar, ...] = (
    Pillar(
        key="operational_resilience",
        name="Operational Resilience",
        audience="Risk, continuity & operations leaders",
        key_message="Resilience is designed, not hoped for.",
        strategic_value="Positions the Captain as a resilience authority.",
        strategic_domain="Career & Professional Impact",
        keywords=(
            "resilience", "risk", "outage", "incident", "recovery", "continuity",
            "disruption", "ori", "threat", "exposure",
            # expanded
            "cyber", "cyberattack", "cyber attack", "cybersecurity", "cyber security",
            "vulnerability", "breach", "ransomware", "failover", "redundancy",
            "apra", "cirmp", "critical infrastructure", "crisis", "cascade",
            "single point of failure", "vendor risk", "supply chain", "high availability",
            "disaster", "backup", "stress test", "systemic risk", "operational risk",
            "third party risk", "service disruption", "system failure", "restoration",
            "tabletop", "playbook", "runbook", "drill", "exercise", "simulation",
        ),
    ),
    Pillar(
        key="business_continuity",
        name="Business Continuity",
        audience="Continuity & operational-risk practitioners",
        key_message="Continuity is a capability you build before you need it.",
        strategic_value="Demonstrates regulatory and continuity depth (e.g. CPS 230).",
        strategic_domain="Career & Professional Impact",
        keywords=(
            "continuity", "bcp", "cps230", "cps 230", "regulator", "compliance",
            "recovery time", "rto", "rpo", "dependency",
            # expanded
            "business impact", "bia", "disaster recovery", "continuity planning",
            "crisis management", "emergency response", "business disruption",
            "service resumption", "workaround", "alternate site", "succession",
            "plan testing", "rehearsal", "prudential", "apra", "regulatory",
            "maximum tolerable downtime", "mtd", "critical function",
            "recovery point objective", "recovery time objective", "backup site",
        ),
    ),
    Pillar(
        key="human_performance",
        name="Human Performance",
        audience="Leaders & high performers",
        key_message="Capacity is the real constraint — protect it first.",
        strategic_value="Bridges performance and wellbeing credibly.",
        strategic_domain="Health & Human Systems",
        keywords=(
            "performance", "capacity", "energy", "focus", "burnout", "load",
            "nervous system", "regulation", "recovery", "sustainable",
            # expanded
            "high performance", "mental performance", "cognitive load", "decision fatigue",
            "peak performance", "flow state", "pressure", "stress management",
            "concentration", "deep work", "deliberate practice", "grit",
            "mental toughness", "performance psychology", "performance coaching",
            "mental fitness", "cognitive function", "executive function",
            "under pressure", "high achiever", "elite performance", "athlete mindset",
            "cognitive performance", "brain performance", "sustained performance",
        ),
    ),
    Pillar(
        key="wellness_sustainable_performance",
        name="Wellness & Sustainable Performance",
        audience="Coaching audience & wellbeing-minded professionals",
        key_message="Sustainable performance beats heroic sprints.",
        strategic_value="Feeds the coaching enterprise and personal brand.",
        strategic_domain="Coaching Enterprise",
        keywords=(
            "wellness", "wellbeing", "sleep", "movement", "nutrition", "stress",
            "coaching", "habit", "rest", "balance",
            # expanded — breadth to match HBR, Gallup, Greater Good, Mindful.org, etc.
            "mental health", "mindfulness", "meditation", "self-care", "well-being",
            "work-life", "work life", "boundaries", "flourishing", "vitality",
            "energy management", "burnout prevention", "longevity", "healthy habits",
            "occupational health", "employee wellbeing", "workplace wellness",
            "emotional wellbeing", "positive psychology", "gratitude", "purpose",
            "meaning", "fulfillment", "psychological safety", "self-compassion",
            "compassion fatigue", "overwork", "exhaustion", "mindset",
            "lifestyle", "resilience", "sustainable high performance",
            "emotional intelligence", "eq", "inner game", "recovery science",
            "restorative", "regeneration", "recharge", "thriving", "flourish",
            "mental fitness", "wellbeing at work", "happiness at work",
            "engagement", "workplace mental health", "psychological wellbeing",
        ),
    ),
    Pillar(
        key="ai_augmented_leadership",
        name="AI-Augmented Leadership",
        audience="Senior leaders adopting AI",
        key_message="AI augments judgement; it doesn't replace accountability.",
        strategic_value="Establishes forward-looking AI leadership credibility.",
        strategic_domain="Career & Professional Impact",
        keywords=(
            "ai", "agent", "llm", "automation", "augmented", "copilot", "model",
            "intelligence", "assistant", "human-in-the-loop",
            # expanded
            "artificial intelligence", "machine learning", "generative ai", "genai",
            "gpt", "chatgpt", "large language model", "neural network", "deep learning",
            "ai adoption", "ai strategy", "ai ethics", "ai governance",
            "digital transformation", "technology leadership", "data-driven",
            "ai-powered", "responsible ai", "ai tool", "agentic",
            "foundation model", "prompt", "rag", "retrieval-augmented",
        ),
    ),
    Pillar(
        key="personal_operating_systems",
        name="Personal Operating Systems",
        audience="Builders, founders & systems thinkers",
        key_message="Run your life like a well-governed system.",
        strategic_value="Showcases the Endeavour build as a signature innovation.",
        strategic_domain="Starship Endeavour",
        keywords=(
            "operating system", "personal os", "endeavour", "starship", "system",
            "command", "officer", "governance", "capability", "workflow",
            # expanded
            "personal productivity", "life design", "planning system", "time management",
            "personal management", "task management", "personal effectiveness",
            "routines", "rituals", "goal setting", "quarterly review", "weekly review",
            "knowledge management", "productivity system", "life optimization",
            "personal strategy", "personal leadership", "self-leadership",
            "self-management", "second brain", "pkm", "personal knowledge",
            "intentional", "deliberate", "systems thinking", "life architecture",
        ),
    ),
    Pillar(
        key="future_of_work",
        name="Future of Work",
        audience="Executives & the broader professional audience",
        key_message="The work is changing; the operating model should too.",
        strategic_value="Broadens reach into mainstream professional conversation.",
        strategic_domain="Career & Professional Impact",
        keywords=(
            "future of work", "remote", "productivity", "team", "operating model",
            "org", "talent", "automation", "role",
            # expanded
            "hybrid work", "distributed team", "flexible work", "workforce",
            "employee experience", "culture", "collaboration", "async",
            "asynchronous", "digital workplace", "workforce strategy",
            "talent management", "retention", "onboarding", "leadership development",
            "organizational change", "org design", "agile", "ways of working",
            "future skills", "upskilling", "reskilling", "workforce planning",
            "new ways of working", "work design", "job design", "work model",
        ),
    ),
    Pillar(
        key="decision_quality_governance",
        name="Decision Quality & Governance",
        audience="Leaders, boards & decision-makers",
        key_message="Better decisions come from better systems, not more willpower.",
        strategic_value="Positions the Captain on judgement and governance.",
        strategic_domain="Starship Endeavour",
        keywords=(
            "decision", "governance", "judgement", "judgment", "trade-off",
            "prioritisation", "prioritization", "approval", "authority", "review",
            # expanded
            "decision making", "decision-making", "strategic decision", "board",
            "risk appetite", "accountability", "mandate", "delegated authority",
            "escalation", "committee", "steering", "oversight", "due diligence",
            "framework", "policy", "control", "assurance", "audit", "risk governance",
            "corporate governance", "board governance", "decision framework",
            "mental models", "cognitive bias", "heuristics", "rationality",
            "evidence-based", "critical thinking", "analytical", "sense-making",
        ),
    ),
)

PILLARS_BY_KEY = {p.key: p for p in PILLARS}

# Classifier methodology versions. A change to how keywords match shifts pillar assignments and
# scores, so it is versioned: any trend that spans a change must flag the discontinuity, and
# stored pillar tags are NOT rewritten (history keeps the version that produced it).
CLASSIFIER_VERSION = "pillars-kw-v2-wordboundary"
LEGACY_CLASSIFIER_VERSION = "pillars-kw-v1-substring"

# A sensible default when nothing matches strongly.
DEFAULT_PILLAR = PILLARS_BY_KEY["personal_operating_systems"]


def _tokens(text: str) -> str:
    return (text or "").lower()


@cache
def _kw_re(kw: str) -> re.Pattern[str]:
    # Whole-word match with an optional plural suffix, so "risk" matches "risks"
    # but "ai" no longer matches inside "said"/"maintain". Must stay identical to
    # keywordRegex() in lcars-portal/src/lib/contentScoring.ts.
    return re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?:s|es)?(?![a-z0-9])")


def classify_pillar(text: str) -> tuple[Pillar, int]:
    """Pure: best-matching pillar for a piece of text + the match score.

    Score is the count of distinct pillar keywords present, matched as whole
    words (multi-word keywords as whole phrases, optional plural suffix).
    Ties resolve to pillar declaration order.
    """
    hay = _tokens(text)
    best = DEFAULT_PILLAR
    best_score = 0
    for p in PILLARS:
        score = sum(1 for kw in p.keywords if _kw_re(kw).search(hay))
        if score > best_score:
            best, best_score = p, score
    return best, best_score


def classify_pillar_v1_substring(text: str) -> tuple[Pillar, int]:
    """The PREVIOUS matcher (plain substring), retained only so the two versions can be compared
    offline. Not used by any runtime path. Known defect: short keywords ('ai', 'eq', 'org',
    'ori') match inside ordinary words."""
    hay = _tokens(text)
    best = DEFAULT_PILLAR
    best_score = 0
    for p in PILLARS:
        score = sum(1 for kw in p.keywords if kw in hay)
        if score > best_score:
            best, best_score = p, score
    return best, best_score


def compare_versions(texts: list[str]) -> dict:
    """Offline impact of the v1 -> v2 change on a corpus: how many pillar assignments and scores
    change, and the changed cases. Pure; reads nothing."""
    changed, score_down, score_up, to_default = [], 0, 0, 0
    for t in texts:
        (p1, s1), (p2, s2) = classify_pillar_v1_substring(t), classify_pillar(t)
        if p1.key != p2.key or s1 != s2:
            changed.append({"text": t[:90], "v1": (p1.key, s1), "v2": (p2.key, s2)})
        score_down += s2 < s1
        score_up += s2 > s1
        to_default += (s2 == 0 and s1 > 0)
    n = len(texts)
    return {"n": n, "changed": len(changed), "pillar_changed": sum(1 for c in changed if c["v1"][0] != c["v2"][0]),
            "score_lower": score_down, "score_higher": score_up, "now_unclassified": to_default,
            "changed_cases": changed}
