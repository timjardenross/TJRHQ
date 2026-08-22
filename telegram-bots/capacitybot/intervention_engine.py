"""Capacity Bot — Intervention Engine (V02 WP03).

Shared ranking engine behind /capacity Q9 (WP06), /helpme (WP04), and
/guide (WP08) — one recommendation system, not three (spec §4: "Do not
build three independent recommendation systems").

Deterministic only — no LLM dependency (spec §14: "Do not introduce an LLM
dependency for V02. Start deterministic."). Ranks by:
  1. help_state match (when the caller has one — /helpme only)
  2. capacity compatibility (hard filter, spec §10 — never optimise for
     productivity in red)
  3. stimulation-direction compatibility
  4. pain compatibility (hard filter when incompatible)
  5. executive-effort penalty in orange/red
  6. personal success weighting from capacity_intervention_events, with a
     minimum-sample floor so a single lucky/unlucky trial can't dominate
     (spec §15/§31 — never claim certainty from a small sample)
  7. a fresh penalty against an intervention that just failed twice in a row
"""

from __future__ import annotations

import logging
from collections import Counter

log = logging.getLogger(__name__)

TABLE = "capacity_interventions"
EVENTS_TABLE = "capacity_intervention_events"

# Below this many completed (better/same/worse) attempts, personal-outcome
# weighting is skipped entirely — not enough signal to trust (spec §31).
MIN_SAMPLE_FOR_WEIGHTING = 3

_OUTCOME_WEIGHT = {"better": 1, "same": 0, "worse": -1}


async def _fetch_candidates(db, capacity_state: str | None) -> list[dict]:
    if not db:
        return []
    try:
        query = db.table(TABLE).select("*").eq("enabled", True)
        if capacity_state:
            query = query.contains("capacity_allowed", [capacity_state])
        res = query.execute()
        return res.data or []
    except Exception as exc:
        log.error("capacity_interventions fetch failed: %s", exc)
        return []


async def _fetch_personal_outcomes(db, intervention_ids: list[str]) -> dict[str, list[str]]:
    """intervention_id -> list of outcomes, most recent first. Empty dict on
    any failure — the engine must still rank without this (spec §25)."""
    if not db or not intervention_ids:
        return {}
    try:
        res = (
            db.table(EVENTS_TABLE)
            .select("intervention_id,outcome,started_at")
            .in_("intervention_id", intervention_ids)
            .not_.is_("outcome", "null")
            .order("started_at", desc=True)
            .limit(500)
            .execute()
        )
        by_id: dict[str, list[str]] = {}
        for row in res.data or []:
            by_id.setdefault(row["intervention_id"], []).append(row["outcome"])
        return by_id
    except Exception as exc:
        log.warning("capacity_intervention_events fetch failed (ranking continues unweighted): %s", exc)
        return {}


def _score(
    row: dict,
    *,
    help_state: str | None,
    stimulation_state: str | None,
    pain_state: str | None,
    capacity_state: str | None,
    executive_function: str | None,
    outcomes: list[str] | None,
) -> float | None:
    """Returns None if the candidate must be excluded outright (a hard
    safety filter failed), else a score — higher ranks first."""
    score = 0.0

    target_states = row.get("target_states") or []
    if help_state:
        score += 10.0 if help_state in target_states else 0.0
    else:
        score += 5.0  # no state signal to match (Q9/guide path) — flat base

    stim_effect = row.get("stimulation_effect")
    if stimulation_state is not None:
        if stimulation_state == "low" and stim_effect == "increase":
            score += 3.0
        elif stimulation_state == "high" and stim_effect == "decrease":
            score += 3.0
        elif stim_effect == "neutral":
            score += 1.0
        elif stimulation_state == "low" and stim_effect == "decrease":
            score -= 3.0
        elif stimulation_state == "high" and stim_effect == "increase":
            score -= 3.0

    if pain_state in ("elevated", "high") and not row.get("pain_compatible", True):
        return None  # hard exclude — spec §26, never push through pain incompatibly
    if pain_state in ("elevated", "high") and row.get("pain_compatible"):
        score += 1.0

    if capacity_state in ("orange", "red"):
        effort = row.get("executive_effort", "low")
        if effort == "high":
            score -= 5.0
        elif effort == "moderate":
            score -= 2.0

    if executive_function == "very_difficult" and row.get("executive_effort") in ("moderate", "high"):
        score -= 3.0

    if outcomes:
        completed = [o for o in outcomes if o in _OUTCOME_WEIGHT]
        if len(completed) >= MIN_SAMPLE_FOR_WEIGHTING:
            score += sum(_OUTCOME_WEIGHT[o] for o in completed) * 2.0
        # a fresh 2-in-a-row failure is worth acting on even below the
        # sample floor — a struggling user shouldn't be re-offered
        # something that just failed twice.
        if completed[:2] == ["worse", "worse"]:
            score -= 4.0

    return score


async def rank_interventions(
    db,
    *,
    help_state: str | None = None,
    capacity_state: str | None = None,
    stimulation_state: str | None = None,
    pain_state: str | None = None,
    executive_function: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Returns up to `limit` candidate rows from capacity_interventions,
    highest-scored first, safety-filtered by capacity/pain compatibility.
    Every caller (Q9, /helpme, /guide) goes through this one function."""
    candidates = await _fetch_candidates(db, capacity_state)
    if not candidates:
        return []

    outcomes_by_id = await _fetch_personal_outcomes(db, [c["intervention_id"] for c in candidates])

    scored: list[tuple[float, dict]] = []
    for row in candidates:
        s = _score(
            row,
            help_state=help_state,
            stimulation_state=stimulation_state,
            pain_state=pain_state,
            capacity_state=capacity_state,
            executive_function=executive_function,
            outcomes=outcomes_by_id.get(row["intervention_id"]),
        )
        if s is not None:
            scored.append((s, row))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in scored[:limit]]


async def get_intervention(db, intervention_id: str) -> dict | None:
    if not db:
        return None
    try:
        res = db.table(TABLE).select("*").eq("intervention_id", intervention_id).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:
        log.error("capacity_interventions lookup failed: %s", exc)
        return None


async def create_event(
    db,
    *,
    source: str,
    intervention_id: str,
    help_state: str | None = None,
    checkin_id=None,
    capacity_before: str | None = None,
    stimulation_before: str | None = None,
    pain_before: str | None = None,
    pain_score_before: int | None = None,
    regulation_before: str | None = None,
    executive_before: str | None = None,
    compensation_before: str | None = None,
    context_loads: list[str] | None = None,
    reassessment_due_at=None,
) -> tuple[bool, dict | None, str | None]:
    """Log an accepted intervention — spec §11's intervention_event."""
    if not db:
        return False, None, "Supabase unavailable (check SUPABASE_KEY)"
    payload = {
        "source": source,
        "intervention_id": intervention_id,
        "help_state": help_state,
        "checkin_id": checkin_id,
        "capacity_before": capacity_before,
        "stimulation_before": stimulation_before,
        "pain_before": pain_before,
        "pain_score_before": pain_score_before,
        "regulation_before": regulation_before,
        "executive_before": executive_before,
        "compensation_before": compensation_before,
        "context_loads": context_loads or [],
    }
    if reassessment_due_at is not None:
        payload["reassessment_due_at"] = reassessment_due_at
    try:
        res = db.table(EVENTS_TABLE).insert(payload).execute()
        row = (res.data or [None])[0]
        return True, row, None
    except Exception as exc:
        log.error("capacity_intervention_events insert failed: %s | payload=%s", exc, payload)
        return False, None, str(exc)


async def complete_reassessment(
    db,
    event_id,
    *,
    outcome: str,
    capacity_after: str | None = None,
    would_use_again: str | None = None,
    optional_note: str | None = None,
) -> tuple[bool, str | None]:
    """Write the Better/Same/Worse reassessment result (spec §12)."""
    if not db:
        return False, "Supabase unavailable (check SUPABASE_KEY)"
    payload = {
        "outcome": outcome,
        "reassessment_completed_at": "now()",
    }
    if capacity_after is not None:
        payload["capacity_after"] = capacity_after
    if would_use_again is not None:
        payload["would_use_again"] = would_use_again
    if optional_note is not None:
        payload["optional_note"] = optional_note
    try:
        db.table(EVENTS_TABLE).update(payload).eq("id", event_id).execute()
        return True, None
    except Exception as exc:
        log.error("capacity_intervention_events reassessment update failed: %s", exc)
        return False, str(exc)


async def personal_effectiveness_summary(db, min_sample: int = MIN_SAMPLE_FOR_WEIGHTING) -> list[dict]:
    """Per-intervention {intervention_id, title, attempts, better, same,
    worse, not_completed} — the raw counts WP07's /actions upgrade and
    WP10's /capacity_patterns integration both read from. Never returns a
    computed percentage itself (spec §15/§31: counts first, phrasing like
    "has often helped" belongs to the caller, not this module)."""
    if not db:
        return []
    try:
        events = (
            db.table(EVENTS_TABLE)
            .select("intervention_id,outcome")
            .execute()
        ).data or []
        catalogue = {
            row["intervention_id"]: row["title"]
            for row in (db.table(TABLE).select("intervention_id,title").execute()).data or []
        }
    except Exception as exc:
        log.error("personal_effectiveness_summary fetch failed: %s", exc)
        return []

    by_id: dict[str, Counter] = {}
    for e in events:
        iid = e.get("intervention_id")
        outcome = e.get("outcome") or "not_completed"
        by_id.setdefault(iid, Counter())[outcome] += 1

    out = []
    for iid, counts in by_id.items():
        attempts = sum(counts.values())
        if attempts < 1:
            continue
        out.append({
            "intervention_id": iid,
            "title": catalogue.get(iid, iid),
            "attempts": attempts,
            "better": counts.get("better", 0),
            "same": counts.get("same", 0),
            "worse": counts.get("worse", 0),
            "not_completed": counts.get("not_completed", 0),
            "meets_sample_threshold": attempts >= min_sample,
        })
    out.sort(key=lambda r: r["attempts"], reverse=True)
    return out
