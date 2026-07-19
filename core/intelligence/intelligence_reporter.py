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

For daily scheduled runs, use run_daily_intelligence() which also persists
key findings as intelligence_events rows in Supabase.

Usage:
    python3 intelligence_reporter.py            # run all reports
    python3 intelligence_reporter.py --dry-run  # compute but don't write
    python3 intelligence_reporter.py --report <name>  # single report
    python3 intelligence_reporter.py --daily    # run all + persist events
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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
        if rows:
            return rows[0]

        # Fall back to today's recovery pulse telemetry when no captains_log_entries
        # row exists — the Captain may have logged via /recovery_pulse instead.
        pulses = supabase_get("recovery_confidence_today?select=*&limit=1")
        if pulses and pulses[0].get("pulses_completed", 0) > 0:
            row = pulses[0]
            return {
                "energy": row.get("latest_energy"),
                "nervous_system": row.get("latest_nervous_system"),
                "body_signals": row.get("latest_body_signals"),
            }
        return None
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

# ---------------------------------------------------------------------------
# Intelligence event extraction (MSN-0200-P1B)
# ---------------------------------------------------------------------------

def _extract_events_from_report(name: str, data: dict) -> list[dict]:
    """
    Convert a domain report's output into a list of intelligence_event dicts.
    Returns [] if data has status=error or no meaningful findings.
    """
    if data.get("status") == "error":
        return []

    today_date = datetime.now(timezone.utc).date().isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    def _make_event(title: str, risk: str) -> dict:
        rank = {"HIGH": 0.8, "MEDIUM": 0.5, "LOW": 0.2}.get(risk, 0.2)
        dedup_src = f"{name}:{title}:{today_date}"
        dedup_hash = hashlib.sha256(dedup_src.encode()).hexdigest()[:48]
        return {
            "raw_title": title,
            "event_type": "domain_insight",
            "geography": "internal",
            "risk_rating": risk,
            "rank_score": rank,
            "collected_at": now_iso,
            "suppressed": False,
            "source_type": "intelligence_reporter",
            "dedup_hash": dedup_hash,
        }

    events: list[dict] = []

    if name == "decision_effectiveness":
        for finding in data.get("findings", []):
            score = finding.get("score", 1.0)
            if score < 0.6:
                risk = "HIGH"
            elif score < 0.8:
                risk = "MEDIUM"
            else:
                risk = "LOW"
            title = finding.get("title") or finding.get("description") or f"Decision score {score:.2f}"
            events.append(_make_event(title, risk))

    elif name == "mission_intelligence":
        blocked = data.get("blocked_missions_count", 0)
        if isinstance(blocked, int) and blocked > 2:
            events.append(_make_event(f"{blocked} missions blocked", "HIGH"))
        elif isinstance(blocked, int) and blocked > 0:
            events.append(_make_event(f"{blocked} mission(s) blocked", "MEDIUM"))

        avg_cycle = data.get("avg_cycle_time_days")
        if isinstance(avg_cycle, (int, float)) and avg_cycle > 14:
            events.append(_make_event(f"Avg mission cycle time {avg_cycle:.1f} days", "MEDIUM"))

    elif name == "health_performance_correlation":
        for finding in data.get("findings", []):
            corr = finding.get("correlation", finding.get("value", 0.0))
            title = finding.get("title") or finding.get("description") or f"Correlation {corr:.2f}"
            if isinstance(corr, (int, float)) and corr < -0.3:
                events.append(_make_event(title, "HIGH"))
            elif isinstance(corr, (int, float)) and -0.3 <= corr < 0:
                events.append(_make_event(title, "MEDIUM"))
            elif isinstance(corr, (int, float)):
                events.append(_make_event(title, "LOW"))

    elif name == "knowledge_utilisation":
        rate = data.get("utilisation_rate", data.get("utilization_rate"))
        if isinstance(rate, (int, float)) and rate < 0.30:
            events.append(_make_event(f"Knowledge utilisation rate {rate*100:.0f}%", "MEDIUM"))

    elif name == "readiness_trend":
        direction = data.get("trend_direction", "")
        if direction == "declining":
            events.append(_make_event("Readiness trend is declining", "HIGH"))
        elif direction == "flat":
            events.append(_make_event("Readiness trend is flat", "MEDIUM"))
        # "improving" → no event needed (LOW, skip noise)

    elif name == "operating_patterns":
        anomalies = data.get("anomalies", [])
        if anomalies:
            events.append(_make_event(f"{len(anomalies)} operating pattern anomaly/anomalies detected", "MEDIUM"))

    return events


def _sb_post_events(events: list[dict], dry_run: bool = False) -> int:
    """
    Insert intelligence_events rows to Supabase, skipping dedup_hash collisions
    from today. Returns count of events actually inserted.
    Uses urllib only — no SDK required.
    """
    if not events:
        return 0

    if dry_run:
        print(f"[DRY RUN] Would insert {len(events)} intelligence_events to Supabase")
        return 0

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key:
        # Fallback: check via supabase_client
        try:
            from supabase_client import is_configured
            if not is_configured():
                print("[reporter] Supabase not configured — skipping event persistence")
                return 0
        except Exception:
            print("[reporter] Supabase not configured — skipping event persistence")
            return 0

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    # Deduplicate against existing rows inserted today
    today = datetime.now(timezone.utc).date().isoformat()
    hashes = [e["dedup_hash"] for e in events]
    hash_list = ",".join(hashes)
    check_url = (
        f"{url}/rest/v1/intelligence_events"
        f"?dedup_hash=in.({urllib.parse.quote(hash_list)})"
        f"&collected_at=gte.{today}T00:00:00Z"
        f"&select=dedup_hash"
    )

    existing_hashes: set[str] = set()
    try:
        req = urllib.request.Request(check_url, headers={**headers, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read())
            existing_hashes = {r["dedup_hash"] for r in rows}
    except Exception as e:
        print(f"[reporter] Warning: could not check existing events (will attempt insert anyway): {e}")

    new_events = [e for e in events if e["dedup_hash"] not in existing_hashes]
    if not new_events:
        print("[reporter] All intelligence events already persisted today — skipping")
        return 0

    # Core fields only (graceful degradation if table schema is minimal)
    _CORE_FIELDS = {"raw_title", "event_type", "geography", "risk_rating", "rank_score", "collected_at", "suppressed"}
    _FULL_FIELDS = _CORE_FIELDS | {"source_type", "dedup_hash"}

    def _do_insert(payload: list[dict]) -> int:
        post_url = f"{url}/rest/v1/intelligence_events"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            post_url,
            data=body,
            headers={**headers, "Prefer": "return=minimal"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return len(payload)

    # Try with full fields first, fall back to core fields on 400
    full_payload = [{k: v for k, v in e.items() if k in _FULL_FIELDS} for e in new_events]
    try:
        count = _do_insert(full_payload)
        print(f"[reporter] Persisted {count} intelligence_events to Supabase")
        return count
    except urllib.error.HTTPError as e:
        if e.code == 400:
            print(f"[reporter] Full-field insert failed (400) — retrying with core fields only")
            core_payload = [{k: v for k, v in e_.items() if k in _CORE_FIELDS} for e_ in new_events]
            try:
                count = _do_insert(core_payload)
                print(f"[reporter] Persisted {count} intelligence_events (core fields) to Supabase")
                return count
            except Exception as e2:
                print(f"[reporter] Warning: intelligence_events insert failed: {e2}")
                return 0
        else:
            print(f"[reporter] Warning: intelligence_events insert failed (HTTP {e.code}): {e}")
            return 0
    except Exception as e:
        print(f"[reporter] Warning: intelligence_events insert failed: {e}")
        return 0


def run_daily_intelligence(dry_run: bool = False) -> dict[str, Any]:
    """
    Run all 6 intelligence reports AND persist key findings as intelligence_events
    rows in Supabase. This is the entry point for the daily intelligence scheduler.

    Args:
        dry_run: If True, compute and extract events but do not write files or insert rows.

    Returns:
        dict with status, reports_ok, events_persisted, generated_at.
    """
    summary = run_all_reports(dry_run=dry_run, persist_readiness=True)

    # Load each report's data to extract events
    all_events: list[dict] = []
    for key in _REPORTS:
        if dry_run:
            # In dry-run, re-generate to get data (already printed above)
            try:
                _, generator = _REPORTS[key]
                data = generator()
            except Exception:
                data = {}
        else:
            report_path = _OUTPUTS_DIR / f"{key}.json"
            try:
                data = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
            except Exception:
                data = {}
        events = _extract_events_from_report(key, data)
        all_events.extend(events)

    events_persisted = _sb_post_events(all_events, dry_run=dry_run)

    # MSN-0200-P1F Wave 2: External domains are fetched separately by the scheduler
    # at 06:00 AEST (before morning brief) via _external_domains_job() in scheduler.py.
    # To run manually alongside daily intelligence:
    #   from core.intelligence.external_domains import run_all_sources
    #   run_all_sources(dry_run=dry_run)

    return {
        "status": "ok",
        "reports_ok": summary.get("reports_ok", 0),
        "events_extracted": len(all_events),
        "events_persisted": events_persisted,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def run_all_reports(dry_run: bool = False, persist_readiness: bool = True) -> dict[str, Any]:
    """
    Generate all six intelligence reports and write them to outputs/.

    For daily scheduled runs that also persist Supabase intelligence_events,
    call run_daily_intelligence() instead.

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
    parser.add_argument("--dry-run",  action="store_true", help="Compute without writing files or inserting rows")
    parser.add_argument("--report",   type=str, help=f"Single report name: {', '.join(_REPORTS)}")
    parser.add_argument("--no-readiness-persist", action="store_true",
                        help="Skip readiness history persistence")
    parser.add_argument("--daily", action="store_true",
                        help="Run all reports AND persist intelligence_events to Supabase")
    args = parser.parse_args()

    if args.report:
        run_single_report(args.report, dry_run=args.dry_run)
    elif args.daily:
        result = run_daily_intelligence(dry_run=args.dry_run)
        print(f"Daily intelligence complete — {result['events_persisted']} events persisted")
    else:
        run_all_reports(
            dry_run=args.dry_run,
            persist_readiness=not args.no_readiness_persist,
        )


if __name__ == "__main__":
    main()
