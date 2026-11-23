"""Editorial intelligence layer for the weekly brief (COMMS editorial uplift).

Pure, deterministic and offline. Sits *on top of* the existing opportunity
engine and pillars — it adds no store and edits no pillar. It provides:

* three editorial streams mapped over the existing pillars,
* a 100-point editorial score (audience 30 / alignment 25 / evidence 20 /
  originality 15 / timeliness 10) with an evidence floor,
* duplicate detection against already drafted/published titles,
* a publishability screen (confidential / architecture terms),
* claim labelling ([F] fact / [A] analysis / [H] hypothesis).

Everything is behind ``COMMS_EDITORIAL_V2`` (default off). Nothing here
publishes anything; Captain-as-publisher is unchanged.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from lib.comms import pillars

FLAG = "COMMS_EDITORIAL_V2"


def enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in ("1", "true", "yes", "on")


# ── Streams (mapping layer over the existing pillars) ─────────────────────────

S1, S2, S3 = "resilience", "ai_governance", "wellness"
STREAM_NAMES = {
    S1: "Operational Resilience & Systemic Risk",
    S2: "AI, Governance & Leadership",
    S3: "Wellness, Neuroscience & Sustainable Performance",
}
STREAM_ORDER = (S1, S2, S3)

PILLAR_STREAM = {
    "operational_resilience": S1, "business_continuity": S1,
    "ai_augmented_leadership": S2, "decision_quality_governance": S2,
    "human_performance": S3, "wellness_sustainable_performance": S3,
}  # personal_operating_systems / future_of_work are deliberately unstreamed.

AREA_STREAM = {  # Notion Research Library "Research Area"
    "Operational Resilience": S1,
    "National & Critical Infrastructure Resilience": S1,
    "Technology & AI": S2,
    "Health Pain & Neuroscience": S3,
}

WEIGHTS = {"audience": 30, "alignment": 25, "evidence": 20, "originality": 15, "timeliness": 10}
assert sum(WEIGHTS.values()) == 100

MIN_TOTAL = 65
MIN_EVIDENCE = 8
READY_EVIDENCE = 14
DUPLICATE_SIMILARITY = 0.7


def _wb(kw: str, hay: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", hay) is not None


def fit_hits(text: str, pillar_key: str) -> int:
    """Word-boundary keyword hits for one pillar (does not use pillars.classify_pillar)."""
    p = pillars.PILLARS_BY_KEY[pillar_key]
    hay = (text or "").lower()
    return sum(1 for kw in p.keywords if _wb(kw, hay))


def classify_stream(text: str, *, area: str | None = None) -> tuple[str | None, str | None, int]:
    """(stream, pillar_key, hits). Notion area wins; else best word-boundary pillar match."""
    best_p, best_h = None, 0
    for key in PILLAR_STREAM:
        h = fit_hits(text, key)
        if h > best_h:
            best_p, best_h = key, h
    if area and area in AREA_STREAM:
        return AREA_STREAM[area], best_p, best_h
    if best_p is None:
        return None, None, 0
    return PILLAR_STREAM[best_p], best_p, best_h


# ── Publishability screen ─────────────────────────────────────────────────────

# Architecture / infrastructure / security terms that must never reach a public draft.
ARCHITECTURE_TERMS = (
    "supabase", "systemd", "vercel", "telegram", "postgrest", "service role",
    "api key", "access token", "private key", "credential", "password", "secret",
    "row level security", "rls policy", "journalctl", "cron job", "pgqueuer",
    "apscheduler", "lcars", "command memory", "model-router", "mission brief",
)
_HOST_RE = re.compile(
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b[\w-]+\.(?:internal|local|corp|lan)\b", re.IGNORECASE)


def confidential_terms() -> tuple[str, ...]:
    """Architecture terms plus employer terms from COMMS_CONFIDENTIAL_TERMS (comma list)."""
    extra = tuple(t.strip().lower() for t in os.getenv("COMMS_CONFIDENTIAL_TERMS", "").split(",")
                  if t.strip())
    return ARCHITECTURE_TERMS + extra


def screen(text: str) -> list[str]:
    """Return the confidential/architecture terms found in text (empty = clean)."""
    hay = (text or "").lower()
    hits = [t for t in confidential_terms() if _wb(t, hay)]
    if _HOST_RE.search(hay):
        hits.append("hostname/ip")
    return hits


# Vocabulary that marks an insight as internal implementation rather than transferable.
_INTERNAL_VOCAB = (
    "endeavour", "starship", "officer", "mission", "pipeline", "scheduler", "bot",
    "migration", "schema", "repo", "commit", "deploy", "workbench", "specialist",
    "capability", "command layer", "orchestrator", "xo", "adr",
)


def internal_density(text: str) -> int:
    hay = (text or "").lower()
    return sum(1 for t in _INTERNAL_VOCAB if _wb(t, hay))


# ── Scoring ───────────────────────────────────────────────────────────────────

# Evidence grade → base points (0–12). Grades are set by the source adapter.
GRADE_POINTS = {
    "independent": 12,         # regulator, peer-reviewed, independent audit (verified)
    "internal_evidence": 7,    # real recorded outcome/lesson/decision
    "unverified_library": 5,   # Research Library page not yet re-verified
    "signal": 4,               # external signal, headline-level only
}
_STATUS_BONUS = {"Completed Research": 2, "Evidence Review": 1, "Active Research": 0,
                 "Research Backlog": -2}

_STOP = frozenset(["the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with", "is", "are", "be", "as", "at", "by", "from", "that", "this", "it", "how", "why", "what", "when", "your", "you", "we", "our", "not", "more", "than", "into", "over"])


def tokens(text: str) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
                     if len(w) > 2 and w not in _STOP)


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def max_similarity(title: str, existing: list[str]) -> float:
    return max((similarity(title, e) for e in existing), default=0.0)


def _age_days(as_of: str | None, now: datetime) -> float | None:
    if not as_of:
        return None
    try:
        s = as_of.strip()
        s = s[:-1] + "+00:00" if s.endswith("Z") else s
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return max(0.0, (now - d).total_seconds() / 86400)
    except ValueError:
        return None


# External evidence is graded by source kind, and counted per distinct publisher family so
# syndicated or repeated headlines cannot inflate it. (Mirrors intelligence/weekly_evidence.py;
# test_source_grading_agrees_with_weekly_evidence keeps the two aligned when both are present.)
_SRC_KIND_TERMS = (
    ("aggregator", ("google news",)),
    ("primary", ("cisa", "cisco security", "google cloud security", "aemo", "acsc", "cyber.gov.au",
                 "nist", "apra", "asic", "rba ", "fda", "cdc", "who ")),
    ("mainstream", ("bloomberg", "abc news", "bbc", "financial times", "guardian", "reuters",
                    "associated press", "the age", "financial review", "new york times")),
    ("specialist", ("arn", "sans ", "financial newswire", "industrial cyber", "the register", "itnews")),
    ("content", ("psychology today", "inc.", "fast company", "mckinsey", "harvard business")),
)
EVIDENCE_REF_POINTS = {"primary": 4.0, "peer_reviewed": 4.0, "mainstream": 2.0, "specialist": 1.0,
                       "aggregator": 0.5, "content": 0.0, "unknown": 1.0}
NEWS_ONLY_EVIDENCE_CAP = 10      # no primary / peer-reviewed source => evidence cannot exceed this
STRONG_EVIDENCE_MIN_FAMILIES = 2  # evidence >= READY_EVIDENCE needs >=1 primary AND >=2 publishers


def grade_signal_source(source_name: str) -> str:
    n = f" {(source_name or '').lower()} "
    for kind, terms in _SRC_KIND_TERMS:
        if any(t in n for t in terms):
            return kind
    return "unknown"


@dataclass
class EditorialInfo:
    """Per-opportunity editorial inputs, filled by the source adapter."""
    stream: str | None = None
    evidence_grade: str | None = None
    research_status: str | None = None
    claim_type: str = "A"                       # F / A / H
    as_of: str | None = None                    # ISO date of newest evidence
    external_refs: list[str] = field(default_factory=list)
    # [{"ref","kind","family"}] parallel detail for external_refs added by graded signals
    external_sources: list[dict] = field(default_factory=list)
    internal_refs: list[str] = field(default_factory=list)


@dataclass
class EditorialScore:
    stream: str | None
    audience: int
    alignment: int
    evidence: int
    originality: int
    timeliness: int
    total: int
    readiness: str
    gaps: list[str]
    duplicate: bool
    blocked_terms: list[str]

    @property
    def eligible(self) -> bool:
        return (self.stream is not None and not self.duplicate and not self.blocked_terms
                and self.total >= MIN_TOTAL and self.evidence >= MIN_EVIDENCE)

    def as_dict(self) -> dict:
        return {"stream": self.stream, "total": self.total, "audience": self.audience,
                "alignment": self.alignment, "evidence": self.evidence,
                "originality": self.originality, "timeliness": self.timeliness,
                "readiness": self.readiness, "gaps": self.gaps}


def score_candidate(title: str, body: str, info: EditorialInfo, *, source_kind: str,
                    existing_titles: list[str] | None = None,
                    now: datetime | None = None) -> EditorialScore:
    now = now or datetime.now(timezone.utc)
    text = f"{title} {body}"
    stream = info.stream
    _s, _p, hits = classify_stream(text)
    if stream is None:
        stream = _s
    blocked = screen(text)
    density = internal_density(text)
    gaps: list[str] = []

    # Audience relevance (30): in-stream fit + transferability + external corroboration.
    if stream is None:
        audience = alignment = 0
    else:
        audience = 12 + min(6, 2 * hits) + max(0, 8 - 3 * density) + (4 if info.external_refs else 0)
        audience = min(WEIGHTS["audience"], audience)
        alignment = min(WEIGHTS["alignment"],
                        15 + min(6, 2 * hits) + (4 if source_kind in
                        ("library", "research", "decision", "lesson", "outcome") else 0))
    if density >= 3:
        gaps.append("insight is described in internal-implementation terms; restate for an external audience")

    # Evidence quality (20).
    ev = GRADE_POINTS.get(info.evidence_grade or "", 3)
    fams: dict[str, str] = {}
    for src in info.external_sources:                      # best kind per distinct publisher family
        cur = fams.get(src["family"])
        if cur is None or EVIDENCE_REF_POINTS.get(src["kind"], 1.0) > EVIDENCE_REF_POINTS.get(cur, 1.0):
            fams[src["family"]] = src["kind"]
    if info.external_sources:
        ev += min(6, sum(EVIDENCE_REF_POINTS.get(k, 1.0) for k in fams.values()))
    else:                                                  # legacy/Library refs without grading
        ev += min(6, 3 * len(info.external_refs))
    ev += _STATUS_BONUS.get(info.research_status or "", 0)
    has_primary = any(k in ("primary", "peer_reviewed") for k in fams.values())
    age = _age_days(info.as_of, now)
    if age is not None and age <= 30:
        ev += 2
    if info.external_sources and not has_primary:
        ev = min(ev, NEWS_ONLY_EVIDENCE_CAP)               # headlines corroborate; they do not substantiate
    if ev >= READY_EVIDENCE and not (has_primary and len(fams) >= STRONG_EVIDENCE_MIN_FAMILIES):
        ev = READY_EVIDENCE - 1
    evidence = round(max(0, min(WEIGHTS["evidence"], ev)))
    if not info.external_refs:
        gaps.append("no independent external source cited")
    if info.evidence_grade in ("unverified_library", "signal", None):
        gaps.append("primary sources not yet re-verified")
    if age is not None and age > 90:
        gaps.append("evidence cut-off is older than 90 days")

    # Originality (15): distance from drafted/published titles.
    sim = max_similarity(title, existing_titles or [])
    originality = round(WEIGHTS["originality"] * (1 - sim))

    # Timeliness (10).
    if age is None:
        timeliness = 4
        gaps.append("no dated trigger identified")
    elif age <= 7:
        timeliness = 10
    elif age <= 30:
        timeliness = 8
    elif age <= 90:
        timeliness = 5
    elif age <= 180:
        timeliness = 3
    else:
        timeliness = 1

    total = audience + alignment + evidence + originality + timeliness
    if evidence >= READY_EVIDENCE and not gaps:
        readiness = "Ready for drafting"
    elif evidence >= MIN_EVIDENCE:
        readiness = "Needs verification"
    else:
        readiness = "Needs research"
    return EditorialScore(stream, audience, alignment, evidence, originality, timeliness, total,
                          readiness, gaps, sim >= DUPLICATE_SIMILARITY, blocked)


# ── Selection ─────────────────────────────────────────────────────────────────

def select_per_stream(scored: list[tuple[int, object, EditorialScore]]) -> dict[str, tuple[int, object, EditorialScore] | None]:
    """Best eligible item per stream, or None. Never forces a weak recommendation."""
    out: dict[str, tuple | None] = {s: None for s in STREAM_ORDER}
    for idx, o, sc in scored:
        if not sc.eligible:
            continue
        cur = out[sc.stream]
        if cur is None or sc.total > cur[2].total:
            out[sc.stream] = (idx, o, sc)
    return out


def shared_theme(a: str, b: str, minimum: int = 2) -> list[str]:
    common = sorted(tokens(a) & tokens(b))
    return common if len(common) >= minimum else []


def claim_label(info: EditorialInfo | None) -> str:
    ct = info.claim_type if info else "A"
    if ct == "F" and not (info and info.evidence_grade == "independent"):
        ct = "A"  # a fact label needs independently verified evidence
    return {"F": "[F]", "H": "[H]"}.get(ct, "[A]")
