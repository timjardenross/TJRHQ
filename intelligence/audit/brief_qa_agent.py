"""
Automated QA agent — the "agent recommends, human decides" pre-screen
for intelligence_briefs sitting in IN_REVIEW.

This composes with the governed QA state machine that already exists
(intelligence/workflow/service.py + governance/workflow_gate.py, migration
0084) rather than building parallel infrastructure: it only ever writes
through qa_pass(..., actor='system', ...) — consolidated 2026-07-18 from
the original 3-gate ladder (data_qa/factual_qa/analytical_qa) into one
step. This agent can pass or fail that single QA gate automatically; a
'RED' brief always fails regardless of score, so it still gets human eyes
via the Captain re-running qa_pass with actor='intelligence_lead'.

Reuses intelligence/audit/brief_coherence.py's checks 1-4 (executive_snapshot/
emerging_themes/forward_watch/cps230_implications grounding) via
brief_coherence_checks() rather than re-deriving them. Does NOT reuse that
module's check 5 (overall_risk_justified): it compares overall_risk against
the scale ["HIGH","CRITICAL","LOW","MEDIUM"], but the live column only ever
holds RED/AMBER/GREEN/UNKNOWN (confirmed against production data, 2026-07-18)
- every real brief fails that check regardless of actual event composition.
_risk_accuracy_score() below reimplements the same intent against the real
scale instead.

Any brief with overall_risk == 'RED' always fails data_qa regardless of
score, mirroring the escalation-candidate rule this agent's originating
design doc asked for - a red-flagged brief always gets human eyes, no matter
how well-formed its narrative is.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from intelligence.audit.brief_coherence import brief_coherence_checks
from intelligence.workflow import service
from intelligence.workflow.repository import RepositoryError

log = logging.getLogger(__name__)

PASS_THRESHOLD = 85
# Generous vs. intelligence_events' own 4h signal-freshness window (route.ts) -
# briefs are periodic (fortnightly by default, intelligence/scheduler.py), not
# live signals, so "stale" here means "sat unreviewed a long time", not "old data".
MAX_REVIEW_AGE_DAYS = 7

_RISK_SCALE = {"GREEN": 0, "AMBER": 1, "RED": 2}


def _parse_ts(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None


def _to_coherence_sample(brief: dict) -> dict:
    """Shape a raw intelligence_briefs row into the dict brief_coherence_checks()
    expects (it was written against brief_sample()'s REST-query output, which
    truncates narrative strings and keeps only the first 3 top_events)."""
    top_events = brief.get("top_events") or []
    if isinstance(top_events, str):
        top_events = []  # malformed jsonb - treat as absent, don't crash the agent

    def _s(val: Any) -> str:
        return str(val) if val is not None else ""

    return {
        "brief_id": brief.get("brief_id"),
        "overall_risk": brief.get("overall_risk"),
        "top_events": [
            {
                "event_id": e.get("event_id"),
                "title": _s(e.get("title"))[:80],
                "risk_rating": e.get("risk_rating"),
                "source_name": e.get("source_name"),
            }
            for e in top_events[:3]
        ],
        "narrative": {
            "executive_snapshot": _s(brief.get("executive_snapshot"))[:200] + "...",
            "emerging_themes": _s(brief.get("emerging_themes"))[:150] + "...",
            "forward_watch": _s(brief.get("forward_watch"))[:150] + "...",
            "bottom_line": _s(brief.get("bottom_line"))[:200] + "...",
        },
        "cps230_implications": _s(brief.get("cps230_implications"))[:200] + "...",
    }


def _completeness_score(brief: dict) -> tuple[int, list[str]]:
    required = ["executive_snapshot", "bottom_line", "overall_risk", "confidence", "top_events"]
    notes = []
    present = 0
    for field in required:
        val = brief.get(field)
        ok = val not in (None, "", [], {})
        if ok:
            present += 1
        else:
            notes.append(f"missing or empty: {field}")
    return int((present / len(required)) * 100), notes


def _risk_accuracy_score(brief: dict, sample: dict) -> tuple[int, list[str]]:
    """Real-scale replacement for brief_coherence_checks()'s check 5 - see
    module docstring for why that check can't be reused as-is."""
    overall_risk = (brief.get("overall_risk") or "UNKNOWN").upper()
    if overall_risk not in _RISK_SCALE:
        return 50, [f"overall_risk '{overall_risk}' is not RED/AMBER/GREEN - can't cross-check"]

    top_events = sample["top_events"]
    if not top_events:
        return 100, []  # nothing to contradict overall_risk

    event_ratings = [e.get("risk_rating") for e in top_events if e.get("risk_rating")]
    if not event_ratings:
        return 70, ["top_events present but none carry a risk_rating"]

    highest_event_risk = max(
        (_RISK_SCALE.get(str(r).upper(), 0) for r in event_ratings), default=0
    )
    brief_risk = _RISK_SCALE[overall_risk]

    # A brief may rate itself higher than its loudest event (conservative,
    # fine) but rating itself lower than a RED/HIGH-equivalent event present
    # in its own top_events is the real mismatch this check exists to catch.
    if brief_risk < highest_event_risk:
        return 40, [f"overall_risk={overall_risk} but top_events includes a higher-risk item"]
    return 100, []


def _freshness_score(brief: dict, now: Optional[datetime] = None) -> tuple[int, list[str]]:
    """2026-08-13 fix: floor was 0, which is a trap — at 0.20 weight and an
    85 pass threshold, a freshness_score of 0 caps overall_score at 80 no
    matter how perfect completeness/coherence/risk are, so any brief that
    ever went unreviewed past ~17 days (7 grace + 10 decay) became
    mathematically unpassable forever, got no more overdue with each
    failed re-score, and stayed IN_REVIEW permanently. Confirmed live:
    0 passed / 25 failed every nightly run for 8+ straight nights, nothing
    published since 2026-06-20. Floor raised to 30 (contributes >=6 of the
    20 weighted points) so a brief that's otherwise flawless can still
    clear 85 no matter how stale; a merely-good brief still gets pushed
    below threshold by real staleness, preserving the urgency signal."""
    now = now or datetime.now(timezone.utc)
    generated_at = _parse_ts(brief.get("generated_at"))
    if generated_at is None:
        return 50, ["generated_at missing or unparsable"]
    age_days = (now - generated_at).total_seconds() / 86_400
    if age_days <= MAX_REVIEW_AGE_DAYS:
        return 100, []
    overdue = age_days - MAX_REVIEW_AGE_DAYS
    return max(30, int(100 - overdue * 10)), [f"sat unreviewed {age_days:.1f} days (limit {MAX_REVIEW_AGE_DAYS})"]


def score_brief(brief: dict, now: Optional[datetime] = None) -> dict:
    """Run the automated data_qa checklist against one real intelligence_briefs
    row. Pure function - no repo/network access, so it's directly unit-testable
    against fixture dicts."""
    sample = _to_coherence_sample(brief)
    coherence = brief_coherence_checks(sample)  # checks 1-4, reused as-is

    completeness_score, completeness_notes = _completeness_score(brief)
    risk_score, risk_notes = _risk_accuracy_score(brief, sample)
    freshness_score, freshness_notes = _freshness_score(brief, now)

    # brief_coherence_checks() returns 5 sub-checks; only the first 4 are
    # reused here (see module docstring) - its 5th, overall_risk_justified,
    # uses the broken HIGH/CRITICAL/LOW/MEDIUM scale and must NOT leak into
    # this average (_risk_accuracy_score above replaces it). Name the 4
    # explicitly rather than averaging every value in the dict, or a live
    # brief's coherence_score silently gets contaminated by the same bug
    # this module exists to work around.
    _REUSED_COHERENCE_CHECKS = (
        "snapshot_reflects_events", "themes_grounded_in_data",
        "forward_watch_justified", "cps230_anchored_to_domain",
    )
    coherence_subchecks = [coherence["checks"][k] for k in _REUSED_COHERENCE_CHECKS
                           if coherence["checks"].get(k) is not None]
    coherence_score = int(100 * sum(coherence_subchecks) / len(coherence_subchecks)) if coherence_subchecks else 100
    coherence_notes = [n for n in coherence["notes"] if "Overall risk" not in n]

    overall_score = int(
        completeness_score * 0.25
        + coherence_score * 0.30
        + risk_score * 0.25
        + freshness_score * 0.20
    )

    is_red = (brief.get("overall_risk") or "").upper() == "RED"
    passed = overall_score >= PASS_THRESHOLD and not is_red

    notes = list(completeness_notes) + list(coherence_notes) + list(risk_notes) + list(freshness_notes)
    if is_red:
        notes.append("overall_risk=RED - always routed to human review regardless of score")

    return {
        "brief_id": brief.get("brief_id"),
        "completeness_score": completeness_score,
        "coherence_score": coherence_score,
        "risk_accuracy_score": risk_score,
        "freshness_score": freshness_score,
        "overall_score": overall_score,
        "passed": passed,
        "recommendation": "Approve" if passed else ("Escalate" if is_red else "Review"),
        "notes": notes,
    }


def run_data_qa_agent(repo, brief_id: str, dry_run: bool = True, actor: str = "system") -> dict:
    """Score one brief and, unless dry_run, record the result via the real
    qa_pass() gate - never a bespoke write path."""
    brief = repo.get_brief(brief_id)
    if brief is None:
        raise RepositoryError(f"no brief {brief_id}")

    result = score_brief(brief)
    result["dry_run"] = dry_run

    if not dry_run:
        gate_status = "passed" if result["passed"] else "failed"
        service.qa_pass(
            repo, actor, brief_id, gate_status,
            details={k: v for k, v in result.items() if k not in ("brief_id", "dry_run")},
        )
        result["gate_status"] = gate_status

    return result


def run_nightly(repo, dry_run: bool = True, actor: str = "system") -> list[dict]:
    """Score every brief currently sitting in IN_REVIEW - the real default
    state (confirmed live, 2026-07-18), not the 'pending_qc' value an earlier
    draft of this agent assumed."""
    briefs = repo.list_briefs(approval_status="IN_REVIEW")
    results = []
    for brief in briefs:
        try:
            results.append(run_data_qa_agent(repo, brief["brief_id"], dry_run=dry_run, actor=actor))
        except Exception as exc:  # one bad brief must not stop the batch
            log.error("brief_qa_agent: failed scoring %s: %s", brief.get("brief_id"), exc)
            results.append({"brief_id": brief.get("brief_id"), "error": str(exc)})
    return results


def _main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief-id", help="Score a single brief instead of the full IN_REVIEW batch")
    parser.add_argument("--live", action="store_true",
                        help="Actually call qa_pass (default is dry-run: score and print only)")
    args = parser.parse_args(argv)

    from intelligence.workflow.repository import SupabaseRepository
    repo = SupabaseRepository()
    dry_run = not args.live

    if args.brief_id:
        result = run_data_qa_agent(repo, args.brief_id, dry_run=dry_run)
        print(json.dumps(result, indent=2))
    else:
        results = run_nightly(repo, dry_run=dry_run)
        print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
