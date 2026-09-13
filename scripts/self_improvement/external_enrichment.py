#!/usr/bin/env python3
"""
HQ Evolution — external-candidate fit enrichment.

external_discovery.discover() sets every candidate's `fit` and
`evidence_strength` to hardcoded constants ("moderate"/"moderate") —
deliberately, since only public GitHub search metadata is available at
that stage (its own comment: "public metadata only at discovery stage").
But relevance.py's RelevanceGate.score_candidate() weighs exactly those
two fields at 0.35 and 0.30 of the total score (65% combined) — so for
every external candidate, whether it clears the relevance gate is really
decided almost entirely by GitHub stars (`value`) and license/archived
status (`complexity`), never by whether the repo's actual content
addresses the watchlist topic's gap_hypothesis. A genuinely well-fitting
repo with modest stars can fail the gate before anything ever reads its
README; a heavily-starred but poorly-fitting one sails through on stars
alone.

This module closes that gap WITHOUT touching the gate itself: for a
small, bounded number of top-ranked candidates per cycle, it fetches the
repo's real README and asks the Model Router
(router_client.ModelRouterClient.assess_external_candidate — LLM
judgment, never permission, same non-negotiable rule as the pre-existing
investigate_opportunity) to propose real fit/evidence_strength values,
replacing the hardcoded constants on that candidate's dict in place.
Candidates not selected for enrichment (bounded per cycle) keep their
original discover()-set values unchanged. relevance.py's
RelevanceGate.score_candidate()/evaluate() are never modified, bypassed,
or given a second, LLM-controlled decision path — this only ever upgrades
the deterministic formula's own input data.

Bounded and fail-open, matching external_discovery.py's own posture:
  - enriches at most `max_external_enrichments_per_cycle` candidates
    (default 3) per cycle, ranked highest-first (by `score_fn`, or a
    simple value/complexity heuristic if the caller doesn't pass the
    real RelevanceGate scorer) — scarce enrichment budget goes to the
    most plausible candidates first, not an arbitrary subset
  - a README fetch failure, an unreachable Model Router, or an
    unparseable/invalid model response leaves that candidate's fields
    exactly as discover() set them — never a crash, never a partial or
    guessed value
  - `router=None` (Model Router unreachable this cycle) skips enrichment
    entirely and returns every candidate unchanged — this is genuinely
    optional enrichment, never a required dependency of an otherwise-
    healthy cycle, same rule external_discovery.py states for itself

CLI: none — called from evolution_orchestrator.py, right after
external_discovery.discover(). See tests/test_external_enrichment.py.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Callable

log = logging.getLogger("external_enrichment")

GITHUB_API_BASE = "https://api.github.com"
USER_AGENT = "tjrhq-hq-evolution-discovery/1.0 (+internal research bot; bounded, read-only)"

_VALID_FIT = {"weak", "moderate", "strong"}
_VALID_EVIDENCE = {"weak", "moderate", "strong", "conclusive"}


def _repo_full_name_from_source(source_url: str) -> str | None:
    """'https://github.com/owner/repo' -> 'owner/repo'. None if `source`
    isn't a recognisable GitHub repo URL — candidate['source'] is always a
    GitHub html_url from discover(), but this never trusts that blindly."""
    if not source_url:
        return None
    parts = source_url.rstrip("/").split("github.com/")
    if len(parts) != 2:
        return None
    segments = parts[1].split("/")
    if len(segments) < 2 or not segments[0] or not segments[1]:
        return None
    return f"{segments[0]}/{segments[1]}"


def _fetch_readme_excerpt(source_url: str, *, max_chars: int, timeout: int) -> str | None:
    """Best-effort README fetch via the GitHub API's raw-content endpoint.
    Returns None (never raises) on any failure — same graceful-degrade
    posture as external_discovery.py's own _get_json."""
    full_name = _repo_full_name_from_source(source_url)
    if not full_name:
        return None

    url = f"{GITHUB_API_BASE}/repos/{full_name}/readme"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github.raw+json",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - url built from the fixed GITHUB_API_BASE constant plus an owner/repo pair parsed from the candidate's own discover()-set GitHub source URL, not free-form user input - reviewed 2026-09-13
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        log.warning(f"README fetch failed for {full_name}: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 - README-fetch surface is unpredictable (encoding, redirects, truncation); already logged, must never abort enrichment
        log.warning(f"Unexpected error fetching README for {full_name}: {exc}")
        return None

    return raw[:max_chars] if raw else None


def _gap_hypothesis_from_provenance(candidate: dict[str, Any]) -> str | None:
    """external_discovery._repo_to_candidate() records the watchlist
    topic's gap_hypothesis inside provenance[0]['detail'] (a JSON string)
    — pulls it back out for the assessment prompt, defensively."""
    for prov in candidate.get("provenance", []):
        detail = prov.get("detail")
        if not isinstance(detail, str):
            continue
        try:
            hypothesis = json.loads(detail).get("watchlist_gap_hypothesis")
        except json.JSONDecodeError:
            continue
        if hypothesis:
            return hypothesis
    return None


def _apply_assessment(candidate: dict[str, Any], assessment: dict[str, Any]) -> bool:
    """Validates and applies one assessment dict onto `candidate` in
    place. Returns True if applied. On any invalid/missing field, the
    candidate is left completely unchanged (never a partial write) and
    this returns False."""
    fit = str(assessment.get("fit", "")).strip().lower()
    evidence_strength = str(assessment.get("evidence_strength", "")).strip().lower()
    if fit not in _VALID_FIT or evidence_strength not in _VALID_EVIDENCE:
        return False

    candidate["fit"] = fit
    candidate["evidence_strength"] = evidence_strength
    confidence = assessment.get("confidence")
    if isinstance(confidence, (int, float)) and 0.0 <= confidence <= 1.0:
        candidate["confidence"] = float(confidence)
    rationale = str(assessment.get("rationale", "")).strip()
    if rationale:
        candidate["readme_assessed_rationale"] = rationale
    candidate["readme_assessed"] = True
    return True


def _default_rank(candidate: dict[str, Any]) -> tuple[int, int]:
    """Used only when the caller doesn't pass the real RelevanceGate
    scorer — a coarse value/complexity heuristic so enrichment still goes
    to the more plausible candidates first rather than list order."""
    value_rank = {"medium": 1, "low": 0}.get(candidate.get("value"), 0)
    complexity_rank = {"low": 2, "moderate": 1, "high": 0}.get(candidate.get("complexity"), 1)
    return (value_rank, complexity_rank)


def enrich(
    candidates: list[dict[str, Any]],
    evolution_config: dict[str, Any],
    router: Any | None,
    *,
    score_fn: Callable[[dict[str, Any]], Any] | None = None,
) -> list[dict[str, Any]]:
    """Enriches up to `max_external_enrichments_per_cycle` of `candidates`
    in place (mutates and returns the same list, always — even when
    `router` is None or every enrichment attempt fails), ranked
    highest-first by `score_fn` (pass the caller's real
    RelevanceGate.score_candidate for the most faithful ranking; falls
    back to a coarse heuristic otherwise, since this module deliberately
    doesn't import relevance.py to stay decoupled and independently
    testable).
    """
    if not candidates or router is None:
        return candidates

    max_enrichments = evolution_config.get("max_external_enrichments_per_cycle", 3)
    if max_enrichments <= 0:
        return candidates
    readme_max_chars = evolution_config.get("external_readme_max_chars", 4000)
    readme_timeout = evolution_config.get("external_readme_timeout_seconds", 8)

    rank = score_fn or _default_rank
    ranked = sorted(candidates, key=rank, reverse=True)

    for candidate in ranked[:max_enrichments]:
        readme = _fetch_readme_excerpt(candidate.get("source", ""), max_chars=readme_max_chars, timeout=readme_timeout)
        gap_hypothesis = _gap_hypothesis_from_provenance(candidate)

        try:
            result = router.assess_external_candidate(candidate, readme, gap_hypothesis)
        except Exception as exc:  # noqa: BLE001 - a router call failing must never abort the rest of enrichment or the cycle; already logged
            log.warning(f"assess_external_candidate failed for {candidate.get('title')}: {exc}")
            continue

        if not result.get("success"):
            log.info(f"External fit assessment unavailable for {candidate.get('title')}: {result.get('error')}")
            continue

        if not _apply_assessment(candidate, result.get("assessment") or {}):
            log.warning(
                f"External fit assessment for {candidate.get('title')} was empty/invalid "
                "— keeping metadata-only fit/evidence_strength"
            )

    return candidates
