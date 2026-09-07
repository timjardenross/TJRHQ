"""
HQ Evolution learning memory (V2 sections 20-23).

When a new opportunity is discovered, HQ should not investigate it in a
vacuum — it should be able to recall whether something similar has been
tried before, and what happened. This module answers that recall question
deterministically (keyword overlap against opportunity history), with no
model calls and no hidden global score: `find_related_outcomes()` returns a
short list of *individual* prior records, and `format_related_experience()`
turns that list into one qualitative sentence for injection into the
investigation prompt as extra context.

The single invariant this whole module exists to protect (V2 section 21):

    A `rejected` record and a `learned` record are NOT the same kind of
    signal, and must never be merged, averaged, or presented as one.

  - `outcome_result` / `outcome_confidence` / `outcome_summary` /
    `future_implication` come ONLY from `learned` records — they are
    *system evidence*: an observed technical result (improved / regressed /
    no_material_change / inconclusive / not_yet_ready), scored with the
    outcome-evaluation machinery in opportunity_store.py / evidence_sources.py.
  - `rejection_reason` comes ONLY from `rejected` records — it is a *user
    decision*: someone chose not to pursue the idea, for reasons that may
    have nothing to do with whether the underlying technical proposition
    was true (cost, timing, priorities, taste). It is never technical
    evidence that the change "doesn't work", and this module must never
    let it be read that way.
  - `watch_reason` comes ONLY from `watching` records — an idea that is
    simply not yet ripe, neither accepted nor rejected.

Concretely, this file never computes one aggregate confidence/score across
multiple prior items, and it never lets a rejection borrow the vocabulary
("regressed", "confidence: high", etc.) that belongs to observed outcomes.
Each related item is described on its own terms, individually.

Pure stdlib, deterministic, synchronous — no LLM, no network I/O. Callers
(not this module) are responsible for wiring the resulting string into an
investigation prompt.
"""

import re
from typing import Any

# Lifecycle states worth remembering. Anything else (discovered,
# investigating, proposed, approved, implementing, verifying) has no
# settled system-evidence or user-decision signal yet, so it carries
# nothing useful to recall here. "resolved_before_research" IS worth
# remembering — it means HQ already checked this exact watchlist
# hypothesis against real evidence and found it no longer applied; a
# future similar candidate should see that history too, not re-tread it
# from scratch (V2 section 46).
_RELEVANT_STATES = ("learned", "rejected", "watching", "resolved_before_research")

# Small, inline stopword list — just enough to keep near-universal words
# (especially ones common in this codebase's opportunity titles/summaries)
# from padding out "shared word" counts with noise. Deliberately not
# exhaustive; extend if a false-positive match turns up in practice.
_STOPWORDS = frozenset({
    "the", "and", "that", "with", "this", "from", "into", "have", "will",
    "would", "should", "could", "been", "were", "does", "doing", "about",
    "which", "when", "where", "using", "used", "use", "they", "them",
    "their", "than", "then", "also", "each", "such", "some", "more", "most",
    "over", "under", "your", "what", "there", "here", "only", "very",
    "just", "still", "make", "made", "like",
})

# Below this count of shared significant words, two records in the same
# change_class are treated as unrelated — matching on change_class alone
# would be noise (nearly everything in the same class would "match").
_MIN_SHARED_WORDS = 2

# Cap on the formatted summary string (roughly 500 characters, per spec).
_MAX_SUMMARY_CHARS = 500


def _significant_words(*parts: str) -> set[str]:
    """Lowercase, split on non-alphanumeric boundaries, and keep only
    words that are at least 4 characters and not in the stopword list.
    Never raises: non-string parts are coerced to "" rather than erroring."""
    text = " ".join(p if isinstance(p, str) else "" for p in parts)
    words = re.split(r"[^a-z0-9]+", text.lower())
    return {w for w in words if len(w) >= 4 and w not in _STOPWORDS}


def _record_words(rec: dict[str, Any]) -> set[str]:
    return _significant_words(
        rec.get("title") or "",
        rec.get("summary") or "",
        rec.get("why_relevant") or "",
    )


def _first_n_words(text: str, n: int) -> list[str]:
    """First n significant words of a title, in order — used only for the
    near-duplicate-title check, not for the overlap-count check above."""
    words = [w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(w) >= 4 and w not in _STOPWORDS]
    return words[:n]


def find_related_outcomes(candidate: dict[str, Any], store: Any, max_results: int = 3) -> list[dict[str, Any]]:
    """Find prior Evolution opportunities relevant to a new `candidate`.

    Only records in _RELEVANT_STATES with a matching change_class are
    considered. Relevance is a plain integer count of shared significant
    words between candidate and record (title + summary + why_relevant) —
    an intersection size, not a probability or a Jaccard ratio. A record
    qualifies if that count is >= _MIN_SHARED_WORDS, OR (a simpler,
    separate check) if it shares candidate's discovery_source and the
    first 3 significant words of both titles are identical (catches
    near-duplicate titles that might otherwise share few other words).

    Returns up to `max_results` records, sorted by relevance_score
    descending, in the fixed output shape documented in the module's
    caller-facing spec (see class docstring above for the rejection-vs-
    outcome distinction that shape exists to preserve). Never raises —
    any unexpected error yields an empty list rather than surfacing.
    """
    try:
        candidate = candidate if isinstance(candidate, dict) else {}
        candidate_words = _record_words(candidate)
        candidate_change_class = candidate.get("change_class")
        candidate_source = candidate.get("discovery_source")
        candidate_title_prefix = _first_n_words(candidate.get("title") or "", 3)

        scored: list[tuple[int, dict[str, Any]]] = []

        for rec in store.all_current():
            if not isinstance(rec, dict):
                continue
            if rec.get("lifecycle_state") not in _RELEVANT_STATES:
                continue
            if rec.get("change_class") != candidate_change_class:
                continue

            shared = candidate_words & _record_words(rec)
            relevance_score = len(shared)

            qualifies = relevance_score >= _MIN_SHARED_WORDS
            if not qualifies:
                # Secondary, simpler check: near-duplicate titles from the
                # same discovery source, even if few other words overlap.
                same_source = candidate_source is not None and rec.get("discovery_source") == candidate_source
                rec_title_prefix = _first_n_words(rec.get("title") or "", 3)
                same_prefix = bool(candidate_title_prefix) and candidate_title_prefix == rec_title_prefix
                qualifies = same_source and same_prefix

            if qualifies:
                scored.append((relevance_score, rec))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        results: list[dict[str, Any]] = []
        for relevance_score, rec in scored[:max_results]:
            relationship = rec.get("lifecycle_state")
            outcome = rec.get("outcome") or {}
            if not isinstance(outcome, dict):
                outcome = {}
            is_learned = relationship == "learned"
            is_rejected = relationship == "rejected"
            is_watching = relationship == "watching"
            is_resolved_before_research = relationship == "resolved_before_research"

            results.append({
                "opportunity_id": rec.get("opportunity_id"),
                "title": rec.get("title"),
                "change_class": rec.get("change_class"),
                "relationship": relationship,
                "outcome_result": outcome.get("outcome_result") if is_learned else None,
                "outcome_confidence": outcome.get("confidence") if is_learned else None,
                "outcome_summary": outcome.get("evidence_summary") if is_learned else None,
                "rejection_reason": rec.get("rejection_reason") if is_rejected else None,
                "watch_reason": rec.get("watch_reason") if is_watching else None,
                "future_implication": outcome.get("future_implication") if is_learned else None,
                # A THIRD distinct kind of signal — neither system evidence
                # (outcome_result) nor a human decision (rejection_reason):
                # HQ itself already checked this hypothesis against real
                # evidence and found it no longer applied.
                "resolution_note": rec.get("why_relevant") if is_resolved_before_research else None,
                "relevance_score": relevance_score,
            })

        return results
    except Exception:
        # Memory recall is a helpful enrichment, never a hard dependency —
        # any failure here must not block investigation of the candidate.
        return []


def _describe_item(item: dict[str, Any]) -> str:
    """One qualitative clause for a single related item. Deliberately
    keeps 'learned' (system evidence) and 'rejected' (user decision)
    phrased in entirely different vocabulary — see module docstring."""
    opp_id = item.get("opportunity_id") or "unknown"
    relationship = item.get("relationship")

    if relationship == "learned":
        result = item.get("outcome_result") or "an unclear result"
        phrase = {
            "improved": "improved things",
            "no_material_change": "made no material difference",
            "regressed": "caused a regression",
            "inconclusive": "gave an inconclusive result",
            "not_yet_ready": "is still being observed, not yet evaluated",
        }.get(result, f"resulted in: {result}")
        return f"one similar change {phrase} ({opp_id})"

    if relationship == "rejected":
        reason = item.get("rejection_reason") or "no reason recorded"
        return f"a similar idea was rejected previously (reason: {reason}, {opp_id})"

    if relationship == "watching":
        return f"a similar idea is currently being watched, not yet acted on ({opp_id})"

    if relationship == "resolved_before_research":
        return f"a similar hypothesis was already checked and no longer applied ({opp_id})"

    return f"a related item was found ({opp_id})"


def format_related_experience(related: list[dict[str, Any]]) -> str:
    """Render `related` (the output of find_related_outcomes) as one short
    human-readable string for injection into investigation context.

    Never computes or states one aggregate confidence/score across
    multiple items — each item is described individually and
    qualitatively, and a rejection is always phrased as a decision, never
    as technical evidence. Truncates additional items (rather than letting
    the whole string overflow) to stay near _MAX_SUMMARY_CHARS. Returns ""
    if `related` is empty or on any unexpected error.
    """
    try:
        if not related:
            return ""

        clauses = [_describe_item(item) for item in related if isinstance(item, dict)]
        if not clauses:
            return ""

        count = len(clauses)
        prefix = f"HQ has relevant prior experience with {count} similar idea{'s' if count != 1 else ''}: "

        summary = prefix
        included = 0
        for i, clause in enumerate(clauses):
            piece = clause if included == 0 else f"; {clause}"
            if len(summary) + len(piece) + 1 > _MAX_SUMMARY_CHARS and included > 0:
                remaining = count - included
                if remaining > 0:
                    summary += f"; and {remaining} more not shown here"
                break
            summary += piece
            included += 1
        else:
            summary += "."

        return summary
    except Exception:
        return ""
