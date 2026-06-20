"""Content Opportunity Engine + Intelligence Repository (COMMS-001 WP1/WP3).

Mines the ship's existing Command Memory — missions, decisions, lessons learned,
capabilities, ADRs, research, resilience briefs, and SPC-001 strategic objectives
— and surfaces *publishable* opportunities, each mapped to a thought-leadership
pillar (WP2), a suggested format, a classification, and a relevance score.

WP1 (the repository) is the live inventory this engine produces — no separate
store. Pure scoring/classification core; only ``gather_opportunities`` touches the
database, and it degrades gracefully (yields nothing when Supabase is absent).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
if str(_BOT) not in sys.path:
    sys.path.insert(0, str(_BOT))
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from lib.comms import pillars
except Exception:  # pragma: no cover
    from slack_bot.lib.comms import pillars  # type: ignore

# Classification buckets (mission WP1).
PUBLISHABLE = "publishable"
INTERNAL_ONLY = "internal_only"
FUTURE_OPPORTUNITY = "future_opportunity"

# Markers that should keep an asset internal (never auto-surfaced as publishable).
# Deliberately narrow: genuine operational-security terms only — generic words like
# "incident"/"security" are legitimate resilience *content*, not a reason to suppress.
_SENSITIVE = ("credential", "password", "secret", "rls", "vulnerab",
              "exposed", "api key", "private key", "access token")

# Per-source-kind base impact (how strong a content asset this kind tends to be).
_BASE_IMPACT = {
    "mission": 0.55, "decision": 0.45, "lesson": 0.6, "capability": 0.5,
    "research": 0.65, "ADR": 0.4, "resilience": 0.5, "objective": 0.45,
}

# Default content format per source kind (WP4 formats).
_DEFAULT_FORMAT = {
    "mission": "case_study", "decision": "leadership_lesson", "lesson": "lessons_learned",
    "capability": "behind_the_scenes", "research": "insight_article",
    "ADR": "framework_explanation", "resilience": "industry_commentary",
    "objective": "executive_insight",
}


@dataclass
class ContentOpportunity:
    source_kind: str
    source_ref: str
    title: str
    excerpt: str
    pillar_key: str
    pillar_name: str
    strategic_domain: str
    suggested_format: str
    classification: str
    score: float

    @property
    def is_publishable(self) -> bool:
        return self.classification == PUBLISHABLE


# ── Pure classification + scoring ─────────────────────────────────────────────

def classify(text: str, pillar_score: int) -> str:
    """Pure: bucket an asset as publishable / internal-only / future-opportunity."""
    hay = (text or "").lower()
    if any(m in hay for m in _SENSITIVE):
        return INTERNAL_ONLY
    if pillar_score == 0:
        return FUTURE_OPPORTUNITY
    return PUBLISHABLE


def score(source_kind: str, pillar_score: int, *, quality: float | None = None) -> float:
    """Pure relevance score in ~[0,1]: base impact + pillar fit + outcome quality."""
    base = _BASE_IMPACT.get(source_kind, 0.4)
    fit = min(0.3, 0.1 * pillar_score)
    qual = 0.0 if quality is None else max(-0.1, min(0.15, (quality - 3) * 0.05))
    return round(min(1.0, base + fit + qual), 3)


def build_opportunity(source_kind: str, *, ref: str, title: str, body: str,
                      quality: float | None = None) -> ContentOpportunity:
    """Pure: assemble one opportunity from a source's title/body text."""
    text = f"{title} {body}".strip()
    pillar, pscore = pillars.classify_pillar(text)
    excerpt = " ".join((body or title or "").split())[:200]
    return ContentOpportunity(
        source_kind=source_kind,
        source_ref=ref,
        title=(title or "Untitled").strip()[:160],
        excerpt=excerpt,
        pillar_key=pillar.key,
        pillar_name=pillar.name,
        strategic_domain=pillar.strategic_domain,
        suggested_format=_DEFAULT_FORMAT.get(source_kind, "linkedin_post"),
        classification=classify(text, pscore),
        score=score(source_kind, pscore, quality=quality),
    )


# ── Supabase access (graceful) ────────────────────────────────────────────────

def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:  # pragma: no cover
        log.warning("[comms.opportunities] Supabase unavailable: %s", exc)
        return None


def _q(c, table, select, limit):
    return list((c.raw_client.table(table).select(select).limit(limit).execute()).data or [])


def gather_opportunities(*, limit_per_source: int = 25, publishable_only: bool = True) -> list[ContentOpportunity]:
    """Derive content opportunities live from Command Memory. Empty when offline.

    Reuses the same Command Memory tables the Knowledge Officer reads — no new
    store. Each source contributes its strongest assets, scored and pillar-mapped.
    """
    c = _client()
    if c is None:
        return []
    out: list[ContentOpportunity] = []

    def add(kind, ref, title, body, quality=None):
        try:
            out.append(build_opportunity(kind, ref=str(ref or ""), title=str(title or ""),
                                         body=str(body or ""), quality=quality))
        except Exception:  # pragma: no cover
            pass

    # Missions → case studies / behind-the-scenes.
    try:
        for r in _q(c, "missions", "mission_id,title,description,status,outcome_rating", limit_per_source):
            add("mission", r.get("mission_id"), r.get("title"), r.get("description"),
                quality=r.get("outcome_rating"))
    except Exception:
        pass
    # Lessons learned → lessons posts.
    try:
        for r in _q(c, "lessons_learned", "lesson_id,title,lesson_text,future_guidance", limit_per_source):
            add("lesson", r.get("lesson_id"), r.get("title"),
                f"{r.get('lesson_text','')} {r.get('future_guidance','')}")
    except Exception:
        pass
    # Decisions → leadership lessons.
    try:
        for r in _q(c, "decisions", "id,decision_type,reasoning,outcome,outcome_quality", limit_per_source):
            add("decision", r.get("id"), r.get("decision_type"),
                f"{r.get('reasoning','')} {r.get('outcome','')}", quality=r.get("outcome_quality"))
    except Exception:
        pass
    # Capabilities → behind-the-scenes builds.
    try:
        for r in _q(c, "capabilities", "id,name,purpose", limit_per_source):
            add("capability", r.get("id"), r.get("name"), r.get("purpose"))
    except Exception:
        pass
    # Research → insight articles.
    try:
        for r in _q(c, "research_memory", "mission_id,original_question,consolidated_findings,recommendation", limit_per_source):
            add("research", r.get("mission_id"), r.get("original_question"),
                f"{r.get('consolidated_findings','')} {r.get('recommendation','')}")
    except Exception:
        pass
    # ADRs → framework explanations.
    try:
        for r in _q(c, "architecture_records", "id,title,problem_statement,decision_summary", limit_per_source):
            add("ADR", r.get("id"), r.get("title"),
                f"{r.get('problem_statement','')} {r.get('decision_summary','')}")
    except Exception:
        pass
    # Resilience briefs → industry commentary.
    try:
        for r in _q(c, "intelligence_briefs", "brief_id,executive_snapshot,bottom_line", limit_per_source):
            add("resilience", r.get("brief_id"), "Operational resilience briefing",
                f"{r.get('executive_snapshot','')} {r.get('bottom_line','')}")
    except Exception:
        pass
    # Strategic objectives → executive insight (SPC-001 tie-in).
    try:
        for r in _q(c, "strategic_objectives", "objective_id,title,description,status", limit_per_source):
            if str(r.get("status") or "").lower() == "active":
                add("objective", r.get("objective_id"), r.get("title"), r.get("description"))
    except Exception:
        pass

    if publishable_only:
        out = [o for o in out if o.is_publishable]
    out.sort(key=lambda o: -o.score)
    return out
