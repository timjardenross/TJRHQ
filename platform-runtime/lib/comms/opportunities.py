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

from lib.comms import editorial, pillars, research_library

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
    # MSN-0078: real, evidence-backed outcomes are strong content assets.
    "outcome": 0.62,
    # Editorial uplift: Notion Research Library rows.
    "library": 0.6,
}

# Default content format per source kind (WP4 formats).
_DEFAULT_FORMAT = {
    "mission": "case_study", "decision": "leadership_lesson", "lesson": "lessons_learned",
    "capability": "behind_the_scenes", "research": "insight_article",
    "ADR": "framework_explanation", "resilience": "industry_commentary",
    "objective": "executive_insight", "outcome": "lessons_learned",
    "library": "article_draft",
}

# MSN-0078 WP4: outcome content_classification → suggested COMMS format.
# (operational_resilience→work/LinkedIn/leadership; leadership→leadership note/
#  LinkedIn; coaching/wellness/personal_story→reflective lessons; etc.)
_OUTCOME_CLASS_FORMAT = {
    "linkedin": "linkedin_post",
    "leadership": "executive_insight",
    "operational_resilience": "industry_commentary",
    "coaching": "lessons_learned",
    "wellness": "lessons_learned",
    "personal_learning": "lessons_learned",
    "personal_story": "lessons_learned",
    "internal_work": "executive_insight",
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
    # MSN-0079: the underlying outcome content_classification (sensitivity routing).
    # None for the 8 Command-Memory sources; set for outcome-sourced opportunities.
    content_classification: str | None = None
    # Editorial uplift (COMMS_EDITORIAL_V2): inputs + computed score. None when off.
    info: "editorial.EditorialInfo | None" = None
    escore: "editorial.EditorialScore | None" = None

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


# ── Outcome → opportunity mapping (MSN-0078 bridge; pure) ─────────────────────

def outcome_opportunities(candidates: list[dict]) -> list[ContentOpportunity]:
    """Pure: map outcome_records content candidates → ContentOpportunity.

    Each candidate is a dict from outcome_capture.get_content_candidates(): it has
    already been filtered (medium/high content_potential; not_for_publication and
    internal/personal_story excluded by default). The reusable insight is the
    publishable nugget; content_classification picks a suggested format.
    """
    out: list[ContentOpportunity] = []
    for r in candidates or []:
        body = (r.get("reusable_insight") or r.get("outcome_summary") or "").strip()
        ref = str(r.get("source_id") or r.get("outcome_id") or "")
        opp = build_opportunity("outcome", ref=ref, title=str(r.get("title") or ""), body=body)
        cls = r.get("content_classification")
        fmt = _OUTCOME_CLASS_FORMAT.get(cls or "")
        if fmt:
            opp.suggested_format = fmt
        opp.content_classification = cls
        out.append(opp)
    return out


# ── Editorial uplift (COMMS_EDITORIAL_V2; pure) ───────────────────────────────

_INTERNAL_GRADE_KINDS = ("outcome", "lesson", "decision")


def library_opportunities(rows: list[dict]) -> list[ContentOpportunity]:
    """Pure: Research Library rows → opportunities (graded unverified until re-verified)."""
    out: list[ContentOpportunity] = []
    for r in rows or []:
        o = build_opportunity("library", ref=str(r.get("url") or r.get("id") or ""),
                              title=str(r.get("name") or ""), body=str(r.get("summary") or ""))
        stream, _p, _h = editorial.classify_stream(f"{o.title} {r.get('summary') or ''}",
                                                   area=r.get("area") or None)
        refs = [r["source"]] if str(r.get("source") or "").startswith("http") and "claude.ai" not in str(r.get("source")) and "chatgpt.com" not in str(r.get("source")) else []
        o.info = editorial.EditorialInfo(
            stream=stream, evidence_grade="unverified_library",
            research_status=r.get("status") or None, as_of=r.get("cut_off") or None,
            external_refs=refs, internal_refs=[f"library:{o.source_ref}"])
        out.append(o)
    return out


def attach_signals(opps: list[ContentOpportunity], signals: list[dict]) -> None:
    """Pure: attach external content_signals as corroboration/timeliness (>=2 shared terms)."""
    for o in opps:
        if o.info is None:
            continue
        matched = [s for s in signals or []
                   if len(editorial.shared_theme(f"{o.title} {o.excerpt}",
                                                 f"{s.get('suggested_angle') or ''} {s.get('source_name') or ''}")) >= 2]
        for s in matched[:3]:
            o.info.external_refs.append(f"signal:{s.get('event_id_text')} ({s.get('source_name')})")
        dates = [str(s.get("scored_at")) for s in matched if s.get("scored_at")]
        if dates and (o.info.as_of is None or max(dates) > o.info.as_of):
            o.info.as_of = max(dates)


def apply_editorial(opps: list[ContentOpportunity], *, existing_titles: list[str],
                    signals: list[dict] | None = None, now=None) -> list[ContentOpportunity]:
    """Pure: score every opportunity, drop duplicates, demote confidential, rank."""
    for o in opps:
        if o.info is None:
            o.info = editorial.EditorialInfo(
                evidence_grade="internal_evidence" if o.source_kind in _INTERNAL_GRADE_KINDS else None,
                internal_refs=[f"{o.source_kind}:{o.source_ref}"])
    attach_signals(opps, signals or [])
    kept: list[ContentOpportunity] = []
    for o in opps:
        o.escore = editorial.score_candidate(o.title, o.excerpt, o.info, source_kind=o.source_kind,
                                             existing_titles=existing_titles, now=now)
        if o.escore.duplicate:
            continue
        if o.escore.blocked_terms:
            o.classification = INTERNAL_ONLY
        kept.append(o)
    kept.sort(key=lambda o: (-int(o.escore.eligible), -o.escore.total, -o.score))
    return kept


def _finalize(out: list[ContentOpportunity], publishable_only: bool) -> list[ContentOpportunity]:
    if editorial.enabled():
        out = out + library_opportunities(_gather_library())
        out = apply_editorial(out, existing_titles=_existing_titles(), signals=_gather_signals())
        if publishable_only:
            out = [o for o in out if o.is_publishable]
        return out
    if publishable_only:
        out = [o for o in out if o.is_publishable]
    out.sort(key=lambda o: -o.score)
    return out


def _gather_library() -> list[dict]:
    try:
        return research_library.fetch_rows()
    except Exception as exc:  # pragma: no cover  # noqa: BLE001 - best-effort library read
        log.debug("[comms.opportunities] library unavailable: %s", exc)
        return []


def _existing_titles() -> list[str]:
    try:
        from lib.comms import portfolio
        return portfolio.fetch_titles(("draft", "review", "approved", "ready_to_publish", "published"))
    except Exception as exc:  # pragma: no cover  # noqa: BLE001 - best-effort dedupe read
        log.debug("[comms.opportunities] existing titles unavailable: %s", exc)
        return []


def _gather_signals(limit: int = 50) -> list[dict]:
    """External content_signals (read-only, graceful). [] when offline."""
    c = _client()
    if c is None:
        return []
    try:
        res = (c.raw_client.table("content_signals")
               .select("event_id_text,source_name,pillar_key,suggested_angle,scored_at,rank_score")
               .eq("suppressed", False).order("scored_at", desc=True).limit(limit).execute())
        return list(res.data or [])
    except Exception as exc:  # pragma: no cover  # noqa: BLE001 - best-effort signals read
        log.debug("[comms.opportunities] signals unavailable: %s", exc)
        return []


# ── Supabase access (graceful) ────────────────────────────────────────────────

def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:  # pragma: no cover  # noqa: BLE001 - best-effort Supabase client init, already logged
        log.warning("[comms.opportunities] Supabase unavailable: %s", exc)
        return None


def _q(c, table, select, limit):
    return list((c.raw_client.table(table).select(select).limit(limit).execute()).data or [])


def gather_opportunities(*, limit_per_source: int = 25, publishable_only: bool = True) -> list[ContentOpportunity]:
    """Derive content opportunities live from Command Memory. Empty when offline.

    Reuses the same Command Memory tables the Knowledge Officer reads — no new
    store. Each source contributes its strongest assets, scored and pillar-mapped.
    """
    out: list[ContentOpportunity] = []

    # Outcomes → real, evidence-backed content (MSN-0078 bridge, read-only).
    # Independent of the Command Memory client: outcome_capture has its own graceful
    # client and already excludes not_for_publication and internal/personal_story.
    try:
        out += outcome_opportunities(_gather_outcome_candidates(limit_per_source))
    except Exception as _exc:  # pragma: no cover  # noqa: BLE001 - best-effort outcome-derived opportunities step, already logged
        log.debug("[lib.comms.opportunities] best-effort step failed, continuing: %s", _exc)

    c = _client()
    if c is None:
        # No Command Memory client — return outcome-derived opportunities only.
        return _finalize(out, publishable_only)

    def add(kind, ref, title, body, quality=None):
        try:
            out.append(build_opportunity(kind, ref=str(ref or ""), title=str(title or ""),
                                         body=str(body or ""), quality=quality))
        except Exception as _exc:  # pragma: no cover  # noqa: BLE001 - best-effort opportunity build, already logged
            log.debug("[lib.comms.opportunities] best-effort step failed, continuing: %s", _exc)

    # Missions → case studies / behind-the-scenes.
    try:
        for r in _q(c, "missions", "mission_id,title,description,status,outcome_rating", limit_per_source):
            add("mission", r.get("mission_id"), r.get("title"), r.get("description"),
                quality=r.get("outcome_rating"))
    except Exception as _exc:  # noqa: BLE001 - best-effort missions source, already logged
        log.debug("[lib.comms.opportunities] best-effort step failed, continuing: %s", _exc)
    # Lessons learned → lessons posts.
    try:
        for r in _q(c, "lessons_learned", "lesson_id,title,lesson_text,future_guidance", limit_per_source):
            add("lesson", r.get("lesson_id"), r.get("title"),
                f"{r.get('lesson_text','')} {r.get('future_guidance','')}")
    except Exception as _exc:  # noqa: BLE001 - best-effort lessons-learned source, already logged
        log.debug("[lib.comms.opportunities] best-effort step failed, continuing: %s", _exc)
    # Decisions → leadership lessons.
    try:
        for r in _q(c, "decisions", "id,decision_type,reasoning,outcome,outcome_quality", limit_per_source):
            add("decision", r.get("id"), r.get("decision_type"),
                f"{r.get('reasoning','')} {r.get('outcome','')}", quality=r.get("outcome_quality"))
    except Exception as _exc:  # noqa: BLE001 - best-effort decisions source, already logged
        log.debug("[lib.comms.opportunities] best-effort step failed, continuing: %s", _exc)
    # Capabilities → behind-the-scenes builds.
    try:
        for r in _q(c, "capabilities", "id,name,purpose", limit_per_source):
            add("capability", r.get("id"), r.get("name"), r.get("purpose"))
    except Exception as _exc:  # noqa: BLE001 - best-effort capabilities source, already logged
        log.debug("[lib.comms.opportunities] best-effort step failed, continuing: %s", _exc)
    # Research → insight articles.
    try:
        for r in _q(c, "research_memory", "mission_id,original_question,consolidated_findings,recommendation", limit_per_source):
            add("research", r.get("mission_id"), r.get("original_question"),
                f"{r.get('consolidated_findings','')} {r.get('recommendation','')}")
    except Exception as _exc:  # noqa: BLE001 - best-effort research source, already logged
        log.debug("[lib.comms.opportunities] best-effort step failed, continuing: %s", _exc)
    # ADRs → framework explanations.
    try:
        for r in _q(c, "architecture_records", "id,title,problem_statement,decision_summary", limit_per_source):
            add("ADR", r.get("id"), r.get("title"),
                f"{r.get('problem_statement','')} {r.get('decision_summary','')}")
    except Exception as _exc:  # noqa: BLE001 - best-effort ADRs source, already logged
        log.debug("[lib.comms.opportunities] best-effort step failed, continuing: %s", _exc)
    # Resilience briefs → industry commentary.
    try:
        for r in _q(c, "intelligence_briefs", "brief_id,executive_snapshot,bottom_line", limit_per_source):
            add("resilience", r.get("brief_id"), "Operational resilience briefing",
                f"{r.get('executive_snapshot','')} {r.get('bottom_line','')}")
    except Exception as _exc:  # noqa: BLE001 - best-effort resilience briefs source, already logged
        log.debug("[lib.comms.opportunities] best-effort step failed, continuing: %s", _exc)
    # Strategic objectives → executive insight (SPC-001 tie-in).
    try:
        for r in _q(c, "strategic_objectives", "objective_id,title,description,status", limit_per_source):
            if str(r.get("status") or "").lower() == "active":
                add("objective", r.get("objective_id"), r.get("title"), r.get("description"))
    except Exception as _exc:  # noqa: BLE001 - best-effort objectives source, already logged
        log.debug("[lib.comms.opportunities] best-effort step failed, continuing: %s", _exc)

    return _finalize(out, publishable_only)


def _gather_outcome_candidates(limit: int) -> list[dict]:
    """Fetch content-worthy outcome candidates (read-only, graceful). [] when offline."""
    try:
        import sys
        kp = str(_REPO_ROOT / "core" / "knowledge")
        if kp not in sys.path:
            sys.path.insert(0, kp)
        from outcome_capture import get_content_candidates  # type: ignore
        return get_content_candidates(limit=limit)
    except Exception as exc:  # pragma: no cover  # noqa: BLE001 - best-effort outcome candidates fetch, already logged
        log.debug("[comms.opportunities] outcome candidates unavailable: %s", exc)
        return []
