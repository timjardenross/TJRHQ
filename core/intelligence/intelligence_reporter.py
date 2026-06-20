"""
Intelligence Reporting Layer — WP10
Mission: M-20260613-INTELLIGENCE-MATURITY-PHASE2

Orchestrates all intelligence modules and writes six report JSON files
to outputs/:

  1. decision_effectiveness.json
  2. mission_intelligence.json
  3. health_performance_correlation.json
  4. knowledge_utilisation.json
  5. readiness_trend.json
  6. operating_patterns.json

Also coordinates readiness history persistence (WP5) on every run.

Usage:
    python3 intelligence_reporter.py            # run all reports
    python3 intelligence_reporter.py --dry-run  # compute but don't write
    python3 intelligence_reporter.py --report <name>  # single report
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTPUTS_DIR = _REPO_ROOT / "outputs"
_OUTPUTS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(_REPO_ROOT / "core" / "intelligence"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "coordination"))


# ---------------------------------------------------------------------------
# Safe import helpers
# ---------------------------------------------------------------------------

def _try_import(module_name: str, from_path: str | None = None):
    try:
        if from_path:
            sys.path.insert(0, from_path)
        import importlib
        return importlib.import_module(module_name)
    except ImportError as e:
        print(f"[reporter] Warning: could not import {module_name}: {e}")
        return None


# ---------------------------------------------------------------------------
# Individual report generators
# ---------------------------------------------------------------------------

def _generate_decision_effectiveness() -> dict[str, Any]:
    try:
        from decision_effectiveness import compute_decision_effectiveness
        return compute_decision_effectiveness()
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


def _generate_mission_intelligence() -> dict[str, Any]:
    try:
        from mission_portfolio_analytics import compute_mission_analytics
        return compute_mission_analytics()
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _generate_health_performance_correlation() -> dict[str, Any]:
    try:
        from health_mission_correlation import compute_health_mission_correlations
        from sleep_lag import compute_sleep_lag_from_supabase
    except ImportError as e:
        return {"status": "error", "error": f"Import failed: {e}"}

    try:
        health_corr = compute_health_mission_correlations()
    except Exception as e:
        health_corr = {"status": "error", "error": str(e)}

    try:
        sleep_corr = compute_sleep_lag_from_supabase()
    except Exception as e:
        sleep_corr = {"status": "error", "error": str(e)}

    return {
        "status": "ok",
        "health_mission_correlations": health_corr,
        "sleep_lag_analysis": sleep_corr,
        "findings": (
            health_corr.get("findings", []) + sleep_corr.get("findings", [])
        ),
    }


def _generate_knowledge_utilisation() -> dict[str, Any]:
    try:
        from knowledge_utilisation import compute_knowledge_utilisation
        return compute_knowledge_utilisation()
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _generate_readiness_trend(days: int = 30) -> dict[str, Any]:
    try:
        from readiness_history import generate_readiness_trend_report
        return generate_readiness_trend_report(days)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _generate_operating_patterns() -> dict[str, Any]:
    try:
        from operating_patterns import compute_operating_patterns_from_sources
        return compute_operating_patterns_from_sources()
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Readiness snapshot persistence (WP5)
# ---------------------------------------------------------------------------

def _persist_readiness_snapshot_if_available() -> bool:
    readiness_path = _OUTPUTS_DIR / "readiness.json"
    if not readiness_path.exists():
        return False
    try:
        readiness_dict = json.loads(readiness_path.read_text())
        if readiness_dict.get("unavailable"):
            return False

        # Try to get today's health entry for richer snapshot
        health_entry = _fetch_todays_health_entry()

        from readiness_history import persist_readiness_snapshot
        return persist_readiness_snapshot(readiness_dict, health_entry)
    except Exception as e:
        print(f"[reporter] Readiness snapshot persistence failed (non-fatal): {e}")
        return False


def _fetch_todays_health_entry() -> dict[str, Any] | None:
    try:
        from supabase_client import supabase_get, is_configured
        if not is_configured():
            return None
        from datetime import date
        today = date.today().isoformat()
        rows = supabase_get(f"captains_log_entries?log_date=eq.{today}&limit=1")
        return rows[0] if rows else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def _write_report(name: str, data: dict[str, Any], dry_run: bool = False) -> bool:
    data["_generated_at"] = datetime.utcnow().isoformat() + "Z"
    data["_report"] = name

    if dry_run:
        print(f"[DRY RUN] Would write {name}.json — status: {data.get('status', '?')}")
        return True

    output_path = _OUTPUTS_DIR / f"{name}.json"
    try:
        output_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        status = data.get("status", "?")
        print(f"✅ {name}.json written (status={status})")
        return True
    except Exception as e:
        print(f"❌ Failed to write {name}.json: {e}")
        return False


# ---------------------------------------------------------------------------
# Report registry
# ---------------------------------------------------------------------------

_REPORTS: dict[str, tuple[str, Any]] = {
    "decision_effectiveness":       ("Decision Effectiveness",          _generate_decision_effectiveness),
    "mission_intelligence":         ("Mission Intelligence",            _generate_mission_intelligence),
    "health_performance_correlation": ("Health & Performance Correlation", _generate_health_performance_correlation),
    "knowledge_utilisation":        ("Knowledge Utilisation",           _generate_knowledge_utilisation),
    "readiness_trend":              ("Readiness Trend",                 _generate_readiness_trend),
    "operating_patterns":           ("Operating Patterns",              _generate_operating_patterns),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_all_reports(dry_run: bool = False, persist_readiness: bool = True) -> dict[str, Any]:
    """
    Generate all six intelligence reports and write them to outputs/.

    Args:
        dry_run:           If True, compute but do not write files.
        persist_readiness: If True, also persist readiness history snapshot.

    Returns:
        Summary dict with per-report status.
    """
    print(f"\n{'='*60}")
    print("INTELLIGENCE REPORTER — Starship Endeavour")
    print(f"{'='*60}\n")

    results = {}
    ok_count = 0

    for key, (label, generator) in _REPORTS.items():
        print(f"  [{label}]", end=" ", flush=True)
        try:
            data = generator()
            wrote = _write_report(key, data, dry_run)
            status = data.get("status", "unknown")
            results[key] = {"status": status, "wrote": wrote}
            if status not in ("error",) and wrote:
                ok_count += 1
        except Exception as e:
            print(f"❌ Unhandled error: {e}")
            results[key] = {"status": "error", "error": str(e)}

    # Readiness history persistence
    if persist_readiness and not dry_run:
        persisted = _persist_readiness_snapshot_if_available()
        results["readiness_snapshot_persisted"] = persisted
        if persisted:
            print("✅ Readiness snapshot persisted to logs/readiness/")

    print(f"\n{'='*60}")
    print(f"Completed: {ok_count}/{len(_REPORTS)} reports generated")
    print(f"{'='*60}\n")

    return {
        "status": "ok",
        "reports_ok": ok_count,
        "reports_total": len(_REPORTS),
        "results": results,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def run_single_report(name: str, dry_run: bool = False) -> dict[str, Any]:
    """Generate and write a single named report."""
    if name not in _REPORTS:
        available = ", ".join(_REPORTS.keys())
        return {"status": "error", "error": f"Unknown report: {name}. Available: {available}"}

    label, generator = _REPORTS[name]
    print(f"Generating: {label}")
    data = generator()
    _write_report(name, data, dry_run)
    return data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Intelligence Reporter — Starship Endeavour")
    parser.add_argument("--dry-run",  action="store_true", help="Compute without writing files")
    parser.add_argument("--report",   type=str, help=f"Single report name: {', '.join(_REPORTS)}")
    parser.add_argument("--no-readiness-persist", action="store_true",
                        help="Skip readiness history persistence")
    args = parser.parse_args()

    if args.report:
        run_single_report(args.report, dry_run=args.dry_run)
    else:
        run_all_reports(
            dry_run=args.dry_run,
            persist_readiness=not args.no_readiness_persist,
        )


if __name__ == "__main__":
    main()
