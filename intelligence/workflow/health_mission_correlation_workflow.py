"""
Issue 17: Wire health_mission_correlation.py as a scheduled job.

Pure statistics (Pearson correlation, deterministic), no LLM required.
Computes correlation between health state (pain, energy, sleep, CPAP, mood)
and mission activity. Results are persisted and displayed on Home dashboard
or Intelligence dashboard.

Scheduled: Daily (after health data collection completes).
No dependencies: Can ship independently of Issues 14-16.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)


def persist_health_mission_correlations(
    results: dict, synthesis: Optional[dict] = None, store=None,
    supabase_url: Optional[str] = None, supabase_key: Optional[str] = None,
) -> bool:
    """
    Persist health-mission correlation results to a new table
    (intelligence_health_correlations).

    Args:
        results: Output from core.intelligence.health_mission_correlation.compute_health_mission_correlations()
        synthesis: Issue 18 output from correlation_synthesis.synthesize_correlation_insights(),
            or None if synthesis wasn't run.
        store: Persistence layer (optional, uses direct Supabase if None)
        supabase_url: Supabase URL (reads from env if None)
        supabase_key: Supabase key (reads from env if None)

    Returns:
        True if persisted, False on error (non-blocking)
    """
    import os
    import urllib.request
    import urllib.error

    if not supabase_url:
        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not supabase_key:
        supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not supabase_url or not supabase_key:
        log.warning("Supabase not configured; skipping persistence")
        return False

    def _headers():
        return {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
        }

    payload = {
        "computed_at": datetime.utcnow().isoformat() + "Z",
        "status": results.get("status"),
        "n_health_entries": results.get("n_health_entries"),
        "n_mission_days": results.get("n_mission_days"),
        "correlations": results.get("correlations", {}),
        "findings": results.get("findings", []),
        "pain_productivity_answer": results.get("pain_productivity_answer"),
        "synthesis": synthesis,
    }

    try:
        url = f"{supabase_url}/rest/v1/intelligence_health_correlations"
        headers = _headers()
        headers["Prefer"] = "return=minimal"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 201
    except Exception as exc:
        log.error(f"Failed to persist health-mission correlations: {exc}")
        return False


def run_health_mission_correlation_job() -> dict:
    """
    Issue 17 scheduled job: Compute and persist health-mission correlations.

    Called by scheduler daily (after health data is collected).
    Returns job status + computed results.
    """
    from core.intelligence.health_mission_correlation import compute_health_mission_correlations

    log.info("Running Issue 17 health-mission correlation job...")
    try:
        results = compute_health_mission_correlations(days=90)
        log.info(f"Computed correlations: status={results.get('status')}, n_pairs={results.get('n_paired')}")

        # Issue 18: turn the raw r-values into grounded narrative insights.
        # synthesize_correlation_insights() already no-ops (status='skipped')
        # when results.status == 'insufficient_data', so it's safe to call
        # unconditionally rather than duplicating that guard here.
        synthesis = None
        try:
            from intelligence.brief.correlation_synthesis import synthesize_correlation_insights
            synthesis = synthesize_correlation_insights(results)
            log.info(f"Correlation synthesis: status={synthesis.get('status')}")
        except Exception as exc:
            log.warning(f"Correlation synthesis failed (non-blocking): {exc}")

        # Persist results (+ synthesis if it ran)
        persisted = persist_health_mission_correlations(results, synthesis=synthesis)
        if persisted:
            log.info("Correlations persisted to intelligence_health_correlations table")
        else:
            log.warning("Failed to persist (non-blocking; results still returned)")

        return {
            "status": "success",
            "message": f"Computed correlations for {results.get('n_paired')} paired health-mission days",
            "results": results,
            "synthesis": synthesis,
            "persisted": persisted,
        }
    except Exception as exc:
        log.error(f"Health-mission correlation job failed: {exc}")
        return {
            "status": "failed",
            "error": str(exc),
            "persisted": False,
        }


def get_latest_correlations(supabase_url: Optional[str] = None, supabase_key: Optional[str] = None) -> Optional[dict]:
    """Fetch the latest persisted health-mission correlations."""
    import os
    import urllib.request

    if not supabase_url:
        supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not supabase_key:
        supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not supabase_url or not supabase_key:
        return None

    def _headers():
        return {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
        }

    try:
        # Fetch the most recent correlation result
        url = f"{supabase_url}/rest/v1/intelligence_health_correlations?order=computed_at.desc&limit=1"
        req = urllib.request.Request(url, headers=_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data[0] if data else None
    except Exception as exc:
        log.debug(f"Failed to fetch latest correlations: {exc}")
        return None
