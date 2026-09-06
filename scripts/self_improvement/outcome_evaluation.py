"""
HQ Evolution V2 outcome-evaluation engine (spec sections 10-37): the
post-approval loop that asks "did this change actually deliver the
benefit it was approved for?" — as distinct from "did the implementation
land?" (which auto_remediation.py / Missions already answer).

This module is evidence-only. It has no authority: it never touches
PolicyEngine, automation_eligibility, Mission-only classification, or any
permission field, and it never calls OpportunityStore.update() itself —
the caller (evolution_orchestrator.py) reads the dict this module returns
and decides what, if anything, to persist. Every function here is pure
with respect to state (it only reads files/network, read-only and
bounded) and never raises — the same discipline as relevance.py and
state_validation.py: a bug in this engine, or evidence that simply isn't
there, must degrade to an honest "inconclusive"/"not_yet_ready" result,
never crash the overnight cycle and never fabricate a favourable verdict.

Core principle (section 10, restated): "implementation success is not the
same as improvement success." Missing evidence, an unreachable Model
Router, a concurrent same-class change, or any other doubt must never
become "improved" — the safe default is always "inconclusive" (or
"not_yet_ready" while the observation window is still open).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import evidence_sources
import outcome_schema

log = logging.getLogger("outcome_evaluation")

# Section 33: lifecycle states that count as "this change_class has other
# work actively in flight" for concurrent-change / attribution-risk
# detection. Deliberately excludes "proposed"/"discovered"/"approved" —
# those haven't touched anything yet — and "rejected"/"watching"/
# "resolved_before_research", which never will.
_CONCURRENT_LIFECYCLE_STATES = ("implementing", "verifying", "learned")


def check_implementation_status(opportunity: dict[str, Any], repo_root: Path, data_root: Path) -> dict[str, Any]:
    """Section 11-14: has this opportunity actually been implemented yet,
    and by what signal? Never raises — any file/network error degrades to
    implemented=False with an explanatory detail, since "we don't know"
    must never be read as "yes"."""
    outcome = opportunity.get("outcome") or {}

    if outcome.get("implementation_source") == "manual":
        # A human already asserted this via a dashboard.py decision — we
        # are only reading that assertion back, not re-deriving it.
        return {
            "implemented": True,
            "source": "manual",
            "verified_at": outcome.get("implementation_verified_at"),
            "detail": "Manually marked implemented via dashboard decision.",
        }

    mission_id = opportunity.get("mission_id")
    if mission_id:
        try:
            status = evidence_sources.mission_status(mission_id)
        except Exception as exc:  # pragma: no cover - evidence_sources never raises, but stay defensive
            return {"implemented": False, "source": None, "verified_at": None,
                     "detail": f"Mission status check failed: {exc}"}
        if status.get("available") and status.get("status") in evidence_sources.MISSION_IMPLEMENTED_STATUSES:
            return {
                "implemented": True,
                "source": "mission",
                "verified_at": status.get("updated_at"),
                "detail": f"Mission {mission_id} status={status.get('status')!r}.",
            }
        reason = status.get("reason") if not status.get("available") else f"Mission status={status.get('status')!r} (not yet implemented)"
        return {"implemented": False, "source": None, "verified_at": None,
                 "detail": f"Mission {mission_id} not yet implemented: {reason}"}

    source_finding_id = opportunity.get("source_finding_id")
    if source_finding_id:
        results_path = data_root / "review" / "remediation_results.jsonl"
        if not results_path.exists():
            return {"implemented": False, "source": None, "verified_at": None,
                     "detail": f"No remediation_results.jsonl at {results_path} yet."}
        try:
            rows: list[dict[str, Any]] = []
            with open(results_path) as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError as exc:
            return {"implemented": False, "source": None, "verified_at": None,
                     "detail": f"Could not read remediation_results.jsonl: {exc}"}

        # migration.py qualifies source_finding_id as "{run_id}:{finding_id}";
        # internal_discovery.finding_to_candidate sets it as a bare
        # finding_id. Try an exact match first (covers the bare form and
        # any future exact-qualified logging), then fall back to matching
        # on the suffix after the LAST ":" (covers the qualified form
        # against a remediation log that only ever knew the bare id).
        suffix = source_finding_id.rsplit(":", 1)[-1]
        matches = [r for r in rows if r.get("finding_id") == source_finding_id]
        if not matches:
            matches = [r for r in rows if r.get("finding_id") == suffix]

        if not matches:
            return {"implemented": False, "source": None, "verified_at": None,
                     "detail": f"No remediation_results.jsonl entry for finding {source_finding_id!r} yet."}

        last = matches[-1]
        if last.get("success"):
            return {
                "implemented": True,
                "source": "remediation",
                "verified_at": last.get("timestamp"),
                "detail": f"Remediation succeeded: {last.get('message', '')}",
            }
        return {"implemented": False, "source": None, "verified_at": None,
                 "detail": f"Last remediation attempt failed: {last.get('message', '')}"}

    return {"implemented": False, "source": None, "verified_at": None,
             "detail": "No implementation signal yet (no mission_id, no source_finding_id, not manually marked)."}


def is_observation_window_satisfied(opportunity: dict[str, Any], cycles_elapsed: Optional[int] = None) -> tuple[bool, str]:
    """Section 9: is the observation window (set once, at contract-build
    time) satisfied yet? Never raises. `cycles_elapsed` is supplied by the
    caller (evolution_orchestrator.py), which is the only place that knows
    how many overnight cycles have actually run since observation started."""
    contract = opportunity.get("outcome_contract") or {}
    window = contract.get("observation_window") or {}
    started_at = contract.get("observation_started_at")

    if not started_at:
        return False, "Observation has not started yet"

    window_type = window.get("type")
    count = window.get("count")

    if window_type == "immediate":
        return True, "Immediate verification — no waiting period required"

    if window_type in ("cycles", "events"):
        if cycles_elapsed is None:
            return False, "Cycle count not provided"
        try:
            return cycles_elapsed >= count, f"{cycles_elapsed}/{count} cycles elapsed"
        except TypeError:
            return False, "Cycle count not provided"

    if window_type == "days":
        try:
            started = datetime.fromisoformat(started_at)
            now = datetime.now(timezone.utc)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed_days = (now - started).total_seconds() / 86400.0
            return elapsed_days >= count, f"{elapsed_days:.1f}/{count} days elapsed"
        except (ValueError, TypeError) as exc:
            return False, f"Could not parse observation_started_at={started_at!r}: {exc}"

    return False, f"Unknown observation_window type: {window_type!r}"


def detect_concurrent_changes(opportunity: dict[str, Any], store: Any, window_start_iso: str) -> Optional[str]:
    """Section 33: attribution risk. If another opportunity of the SAME
    change_class was implementing/verifying/landed ("learned") during this
    opportunity's observation window, any measured change could be theirs,
    not this one's — say so rather than crediting/blaming this change.
    Never raises; bounded to a single pass over the current opportunity
    set (already small — one row per opportunity_id)."""
    try:
        this_id = opportunity.get("opportunity_id")
        this_class = opportunity.get("change_class")
        if not this_class or not window_start_iso:
            return None

        try:
            window_start = datetime.fromisoformat(window_start_iso)
        except (ValueError, TypeError):
            window_start = None

        others = []
        for rec in store.all_current():
            if rec.get("opportunity_id") == this_id:
                continue
            if rec.get("change_class") != this_class:
                continue
            if rec.get("lifecycle_state") not in _CONCURRENT_LIFECYCLE_STATES:
                continue
            updated_at = rec.get("updated_at")
            if not updated_at:
                continue
            if window_start is not None:
                try:
                    if datetime.fromisoformat(updated_at) < window_start:
                        continue
                except (ValueError, TypeError):
                    # Can't parse it — be conservative and count it rather
                    # than silently drop a possible confound.
                    pass
            else:
                # No parseable window start — fall back to lexicographic
                # ISO-8601 comparison, which is valid only when both
                # strings share the same UTC "Z"/offset formatting; still
                # safer than skipping the check entirely.
                if updated_at < window_start_iso:
                    continue
            others.append(rec.get("opportunity_id", "?"))

        if not others:
            return None

        ids = ", ".join(others)
        return (f"{len(others)} other {this_class!r} change(s) landed during this observation "
                f"window ({ids}) — attribution is uncertain.")
    except Exception as exc:  # never let attribution-risk detection crash evaluation
        log.warning(f"detect_concurrent_changes failed, treating as no known risk: {exc}")
        return None


def collect_outcome_evidence(opportunity: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Section 12-13: re-read the SAME measurement_hint the baseline was
    captured with, for an apples-to-apples comparison. Never raises."""
    hint = opportunity.get("measurement_hint")
    contract = opportunity.get("outcome_contract") or {}

    if not hint:
        return {
            "current_measurement": {
                "available": False,
                "reason": "No measurement_hint on this opportunity — cannot re-read the same baseline metric.",
            },
            "sources_checked": [],
            "sources_unavailable": list(contract.get("evidence_sources", [])),
        }

    try:
        reading = evidence_sources.read_measurement(hint, repo_root)
    except Exception as exc:  # evidence_sources never raises, but stay defensive
        reading = {"available": False, "reason": f"read_measurement raised: {exc}"}

    return {
        "current_measurement": reading,
        "sources_checked": [f"measurement_hint type={hint.get('type')!r} (same hint used for the baseline)"],
        "sources_unavailable": [] if reading.get("available") else list(contract.get("evidence_sources", [])),
    }


def evaluate_deterministic(
    contract: dict[str, Any],
    current_evidence: dict[str, Any],
    material_change_threshold: float = 0.20,
) -> Optional[dict[str, Any]]:
    """Section 8/10: numeric baseline vs. numeric current measurement.
    Returns None (never a fabricated verdict) whenever the comparison
    can't honestly be made — the caller falls through to model synthesis
    or an inconclusive verdict in that case. Never raises."""
    measurement_type = contract.get("measurement_type")
    if measurement_type not in ("quantitative", "deterministic"):
        return None

    baseline = contract.get("baseline") or {}
    if not baseline.get("available"):
        return None

    current_measurement = current_evidence.get("current_measurement") or {}
    if not current_measurement.get("available"):
        return None

    baseline_value = baseline.get("value")
    current_value = current_measurement.get("value")

    if not isinstance(baseline_value, (int, float)) or isinstance(baseline_value, bool):
        # e.g. a provenance-derived deterministic baseline like
        # "call_log_size_mb=50.0" — not a number we can subtract.
        return None
    if not isinstance(current_value, (int, float)) or isinstance(current_value, bool):
        return None

    try:
        if baseline_value == 0:
            if current_value == 0:
                outcome_result = "no_material_change"
                relative_change = 0.0
            else:
                outcome_result = "regressed"
                relative_change = float("inf") if current_value > 0 else float("-inf")
        else:
            relative_change = (current_value - baseline_value) / baseline_value
            if relative_change <= -material_change_threshold:
                outcome_result = "improved"
            elif relative_change >= material_change_threshold:
                outcome_result = "regressed"
            else:
                outcome_result = "no_material_change"

        change_str = f"{relative_change:+.0%}" if relative_change not in (float("inf"), float("-inf")) else "grew from 0"
        return {
            "outcome_result": outcome_result,
            "evidence_summary": f"Baseline was {baseline_value}, now {current_value} ({change_str} change).",
            "confidence": "high",
            "what_worked": "",
            "what_did_not": "",
            "unexpected_effects": [],
            "future_implication": "",
            "method": "deterministic",
        }
    except (TypeError, ZeroDivisionError, ArithmeticError) as exc:
        log.warning(f"evaluate_deterministic arithmetic failed, deferring to caller: {exc}")
        return None


def _safe_fallback(reason: str, impl: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    result = outcome_schema.honest_fallback_outcome_evaluation(reason)
    result["attribution_risk"] = None
    result["evaluated_at"] = datetime.now(timezone.utc).isoformat()
    result["evidence_detail"] = {}
    if impl is not None:
        result["implementation_status"] = impl
    return result


def evaluate_outcome(
    opportunity: dict[str, Any],
    repo_root: Path,
    data_root: Path,
    store: Any,
    router: Optional[Any] = None,
    cycles_elapsed: Optional[int] = None,
) -> dict[str, Any]:
    """The main entry point (sections 10-37). Orchestrates implementation
    verification, observation-window gating, concurrent-change detection,
    evidence collection, and deterministic-then-model evaluation.

    NOTE on step (b)/`observation_started_at`: this function does not
    itself start the observation window. The expectation (spec section 9)
    is that the caller (evolution_orchestrator.py) sets
    outcome_contract.observation_started_at the first time
    check_implementation_status() reports implemented=True, and persists
    that via OpportunityStore.update() BEFORE calling evaluate_outcome()
    again on a later cycle. This function only reads that field; if it's
    still unset when this is called, that's treated as "the caller hasn't
    started the window yet" and evaluation is skipped rather than assumed.

    Returns one of three shapes:
      - {"skip": True, "reason": ..., "implementation_status": {...}} —
        nothing to evaluate yet (not implemented, or window not started).
        The caller should leave lifecycle_state alone.
      - {"skip": False, "outcome_result": "not_yet_ready", ...} — a real,
        calm, non-urgent result (section 42): the window is open but not
        yet elapsed. The caller may record this, but lifecycle_state
        should stay "verifying", never advance to "learned".
      - a full evaluation dict (outcome_result in improved/no_material_
        change/regressed/inconclusive) with confidence/evidence/method/
        attribution_risk/evaluated_at/evidence_detail/implementation_status
        — the caller may advance lifecycle_state to "learned".

    Never raises: any unexpected exception is caught and degraded to a
    safe "inconclusive" result, since a bug in this engine must never
    crash the overnight cycle.
    """
    try:
        impl = check_implementation_status(opportunity, repo_root, data_root)
        if not impl.get("implemented"):
            return {"skip": True, "reason": "not yet implemented", "implementation_status": impl}

        contract = opportunity.get("outcome_contract") or {}
        if not contract.get("observation_started_at"):
            return {"skip": True, "reason": "observation window not started", "implementation_status": impl}

        ready, window_reason = is_observation_window_satisfied(opportunity, cycles_elapsed)
        if not ready:
            return {
                "skip": False,
                "outcome_result": "not_yet_ready",
                "evidence_summary": window_reason,
                "confidence": None,
                "implementation_status": impl,
            }

        observation_started_at = contract.get("observation_started_at")
        attribution_risk = detect_concurrent_changes(opportunity, store, observation_started_at)
        current_evidence = collect_outcome_evidence(opportunity, repo_root)
        det = evaluate_deterministic(contract, current_evidence)

        if attribution_risk is not None:
            # Section 33: never let a confounding concurrent change be
            # read as evidence of this change's own effect — force
            # inconclusive regardless of what the deterministic/model path
            # found, but keep that finding visible for transparency.
            if det is not None:
                base_summary = det.get("evidence_summary", "")
                method = det.get("method", "deterministic")
            else:
                current_measurement = current_evidence.get("current_measurement") or {}
                base_summary = (
                    f"Current measurement: {current_measurement}"
                    if current_measurement.get("available")
                    else "No current measurement evidence available."
                )
                method = "deterministic"
            result = {
                "outcome_result": "inconclusive",
                "evidence_summary": f"{attribution_risk} {base_summary}".strip(),
                "confidence": "low",
                "what_worked": "",
                "what_did_not": "",
                "unexpected_effects": [],
                "future_implication": "",
                "method": method,
            }
        elif det is not None:
            result = det
        else:
            measurement_type = contract.get("measurement_type")
            current_measurement = current_evidence.get("current_measurement") or {}
            evidence_missing_for_quantitative = (
                measurement_type in ("quantitative", "deterministic")
                and not current_measurement.get("available")
            )
            investigation = opportunity.get("investigation") or {}
            # A qualitative/mixed candidate is only worth a model call when
            # there is genuine POST-IMPLEMENTATION evidence to interpret —
            # `current_measurement.available` is the only signal this
            # function has for "something new was actually observed".
            # `investigation` alone is PRE-implementation reasoning (it was
            # written before the change happened); replaying it back to the
            # model with no new evidence would let the model assert
            # "improved" from nothing but its own earlier optimism, which
            # is exactly the missing-evidence-becomes-success failure mode
            # section 10 forbids. No cross-workbench evidence source is
            # wired for qualitative measurement yet (deferred — see
            # docs/self-improvement/HQ-EVOLUTION.md's V2 audit table), so
            # today this path is honestly "inconclusive" for those classes
            # until a real evidence reader exists; it is NOT a regression,
            # since nothing currently supplies genuine qualitative evidence
            # for the model to interpret anyway.
            has_new_evidence = bool(current_measurement.get("available"))

            if evidence_missing_for_quantitative or not has_new_evidence:
                if evidence_missing_for_quantitative:
                    reason = current_measurement.get("reason", "Current measurement unavailable")
                elif measurement_type in ("qualitative", "mixed", "unknown"):
                    reason = ("No post-implementation evidence source is wired for this measurement "
                              "type yet — evaluating from pre-implementation investigation reasoning "
                              "alone would risk treating the original optimism as its own confirmation.")
                else:
                    reason = "No qualitative investigation content and no quantitative evidence to evaluate."
                result = {
                    "outcome_result": "inconclusive",
                    "evidence_summary": f"Evidence unavailable: {reason}",
                    "confidence": "low",
                    "what_worked": "",
                    "what_did_not": "",
                    "unexpected_effects": [],
                    "future_implication": "",
                    "method": "deterministic",
                }
            else:
                evidence_bundle = {
                    "outcome_contract": contract,
                    "current_evidence": current_evidence,
                    "investigation": investigation,
                    "prior_outcome": opportunity.get("outcome", {}),
                }
                result = None
                if router is not None:
                    try:
                        if router.health_check():
                            router_result = router.evaluate_outcome(evidence_bundle)
                            if router_result.get("success") and router_result.get("evaluation"):
                                result = outcome_schema.validate_outcome_evaluation(router_result["evaluation"])
                                result["method"] = "model_synthesis"
                    except Exception as exc:
                        log.warning(f"Model outcome synthesis failed, falling back to honest template: {exc}")
                        result = None
                if result is None:
                    result = outcome_schema.honest_fallback_outcome_evaluation(
                        "Model Router unavailable or synthesis failed — no fabricated verdict."
                    )

        result["attribution_risk"] = attribution_risk
        result["evaluated_at"] = datetime.now(timezone.utc).isoformat()
        result["evidence_detail"] = {
            "current_evidence": current_evidence,
            "baseline": contract.get("baseline"),
        }
        result["implementation_status"] = impl
        return result

    except Exception as exc:
        log.error(f"evaluate_outcome failed unexpectedly, degrading to inconclusive: {exc}")
        return {
            "outcome_result": "inconclusive",
            "confidence": "low",
            "evidence_summary": f"Evaluation failed: {exc}",
            "what_worked": "",
            "what_did_not": "",
            "unexpected_effects": [],
            "future_implication": "",
            "method": "deterministic",
            "attribution_risk": None,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "evidence_detail": {},
            "implementation_status": None,
        }
