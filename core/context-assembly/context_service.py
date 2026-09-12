#!/usr/bin/env python3
"""
Context Assembly Service — WP6 (CLI) + WP-A (HTTP)

CLI entry point for the Context Assembly Foundation.
Called by the JS backend via child_process or run standalone to pre-generate output files.

Usage (CLI):
  python3 context_service.py                    # generate all context outputs to files
  python3 context_service.py captain-brief       # print CaptainBriefContext JSON to stdout
  python3 context_service.py operating-picture   # print CaptainOperatingPictureContext JSON
  python3 context_service.py health              # print HealthContextPackage JSON
  python3 context_service.py blockers            # print List[BlockerContextPackage] JSON
  python3 context_service.py recommendations     # print RecommendationPackage JSON
  python3 context_service.py mission <MSN-ID>    # print MissionContextPackage JSON for one mission

Usage (HTTP service — WP-A):
  python3 context_service.py serve               # start HTTP server on CONTEXT_SERVICE_PORT (5001)
  python3 context_service.py serve --port 5002   # override port
  python3 context_service.py serve --host 0.0.0.0

HTTP endpoints:
  GET /health           — liveness check + corpus counts
  GET /brief/captain    — Captain Brief JSON (health summary, priorities, blockers, decisions)
  GET /brief/number-one — Number One Brief JSON (top-3, blocker, risk, recommendation)
  GET /queue/health-adjusted — Number One's capacity-aware work queue (per-item
                          capacity_note, recommended_focus, plain-English advisory)

Design constraints (WP-A):
  - Stateless: corpus re-read on every request
  - Fail-safe: all endpoints return structured errors, never 500 without body
  - Health data is summary-level only: workload_constraint, data_quality, safety_flags
    (no pain_level, mood, energy, stress — privacy constraint)
  - No database, no persistence, no schema changes
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "core" / "context-assembly"))
sys.path.insert(0, str(REPO_ROOT / "core" / "coordination"))
# 2026-07-10: /brief/full's `core.platform.*` absolute imports need the repo
# root itself on sys.path (the two inserts above only cover this directory's
# own same-level sibling imports) - "core" isn't a hyphenatable package name
# via `python3 -m`, so this script is always run as a plain script, never
# `-m core.context-assembly.context_service`; this insert is what actually
# makes `core.platform.*` resolvable regardless of the process's cwd.
sys.path.insert(0, str(REPO_ROOT))

import config
from assembler import (
    assemble_mission_context,
    assemble_health_context,
    assemble_blockers,
    assemble_decisions_awaiting_input,
    assemble_captain_brief_context,
    assemble_operating_picture,
)
from recommendation_engine import generate_recommendation_package
from models import HealthContextPackage

# Output directory for pre-generated files
CONTEXT_OUTPUT_DIR = config.OUTPUT_DIR / "context"
CONTEXT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_missions() -> list:
    """Load active missions from filesystem corpus or return empty list."""
    try:
        from loaders import load_corpus
        corpus = load_corpus()
        missions = []
        for mid, m in corpus.get("missions", {}).items():
            m_dict = {
                "mission_id": mid,
                "title": m.get("title", ""),
                "status": m.get("status", "ACTIVE"),
                "priority": m.get("priority", "P3"),
                "domain": m.get("domain", ""),
                "due_date": m.get("due_date"),
                "blockers": m.get("blockers", []),
                "dependencies": m.get("dependencies", []),
                "next_action": m.get("next_action"),
                "assigned_role": m.get("owner"),
            }
            missions.append(m_dict)
        return missions
    except Exception as e:
        _err(f"Could not load missions corpus: {e}")
        return []


def _load_corpus():
    """Load the full corpus for mission context assembly."""
    try:
        from loaders import load_corpus
        return load_corpus()
    except Exception as e:
        _err(f"Could not load corpus: {e}")
        return {"missions": {}, "decisions": {}, "adrs": {}, "capabilities": {}}


def _load_live_missions_for_number_one() -> list:
    """_load_missions() overlaid with live Supabase status/priority — the
    actual system of record for mission lifecycle (per core/command-centre/
    backend/api/missions.js's own comment: "mission-index.txt and
    missions.db are NOT authoritative here. All reads go through
    supabaseGet() -> PostgREST.").

    2026-09-08: found while extending Number One's brief — the only sync
    between Supabase and the file corpus (mission-registry-sync.timer, daily
    06:45) only appends brand-new mission IDs to a flat text index; it never
    updates an existing mission's status. So Missions/Active/*.md can
    silently drift from what Supabase actually says a mission's current
    status/priority is, and Number One's escalation/follow-up detection
    would be reasoning over stale data without this.

    Supabase's missions table has no blockers/dependencies/next_action/
    assigned_role columns at all — those richer fields (which Number One's
    escalation rules do use) only exist in the file corpus, where present.
    So this overlays live status/priority onto the file corpus by
    mission_id (Supabase wins for those two fields specifically) rather
    than replacing the file corpus outright, and adds any Supabase mission
    with no file-corpus record using just its Supabase fields (blockers/
    dependencies/assigned_role empty for those — the same information
    scarcity Number One already tolerates for a bare engineering handoff).
    Falls back to the plain file corpus on any Supabase read failure.
    """
    file_missions = _load_missions()
    by_id = {m["mission_id"]: dict(m) for m in file_missions}
    try:
        sys.path.insert(0, str(REPO_ROOT / "core" / "health"))
        from supabase_client import supabase_get  # noqa: PLC0415
        rows = supabase_get("missions?select=mission_id,status,priority,updated_at,closed_at,pr_url")
    except Exception as exc:
        _err(f"Could not load live Supabase mission status — using file corpus only: {exc}")
        return file_missions

    for row in rows:
        mid = row.get("mission_id")
        if not mid:
            continue
        pr_url = row.get("pr_url")
        if mid in by_id:
            if row.get("status"):
                by_id[mid]["status"] = row["status"]
            if row.get("priority"):
                by_id[mid]["priority"] = row["priority"]
            if pr_url:
                by_id[mid].setdefault("metadata", {})["pr_url"] = pr_url
        else:
            by_id[mid] = {
                "mission_id": mid,
                "title": mid,
                "status": row.get("status") or "ACTIVE",
                "priority": row.get("priority") or "P3",
                "domain": "",
                "due_date": None,
                "metadata": {"pr_url": pr_url} if pr_url else {},
                "blockers": [],
                "dependencies": [],
                "next_action": None,
                "assigned_role": None,
            }
    return list(by_id.values())


# ---------------------------------------------------------------------------
# Assembly functions
# ---------------------------------------------------------------------------

def get_health() -> dict:
    pkg = assemble_health_context()
    return pkg.to_dict()


def get_recommendations(missions: list = None, health: HealthContextPackage = None) -> dict:
    if missions is None:
        missions = _load_missions()
    if health is None:
        try:
            health = assemble_health_context()
        except Exception:
            health = None
    pkg = generate_recommendation_package(missions, health)
    return pkg.to_dict()


def get_blockers(missions: list = None) -> list:
    if missions is None:
        missions = _load_missions()
    pkgs = assemble_blockers(missions)
    return [p.to_dict() for p in pkgs]


def get_captain_brief(missions: list = None, recommendations: list = None) -> dict:
    if missions is None:
        missions = _load_missions()
    if recommendations is None:
        try:
            health = assemble_health_context()
            from recommendation_engine import rank_missions
            recommendations = rank_missions(missions, health)
        except Exception:
            recommendations = []
    brief = assemble_captain_brief_context(
        missions=missions,
        recommendations=recommendations,
        source="fresh",
    )
    return brief.to_dict()


def get_operating_picture(missions: list = None, recommendations: list = None) -> dict:
    if missions is None:
        missions = _load_missions()
    if recommendations is None:
        try:
            health = assemble_health_context()
            from recommendation_engine import rank_missions
            recommendations = rank_missions(missions, health)
        except Exception:
            recommendations = []
    cop = assemble_operating_picture(
        missions=missions,
        recommendations=recommendations,
        source="fresh",
    )
    return cop.to_dict()


def get_mission_context(mission_id: str) -> dict | None:
    corpus = _load_corpus()
    pkg = assemble_mission_context(mission_id, corpus)
    if pkg is None:
        return None
    return pkg.to_dict()


# ---------------------------------------------------------------------------
# File-based output (for JS backend file-read pattern)
# ---------------------------------------------------------------------------

def generate_all_outputs():
    """
    Pre-generate all context JSON files to CONTEXT_OUTPUT_DIR.
    Run this on a schedule or trigger to keep outputs fresh.
    """
    missions = _load_missions()

    try:
        health = assemble_health_context()
        from recommendation_engine import rank_missions
        recs = rank_missions(missions, health)
    except Exception as e:
        _err(f"Health/recs failed (non-fatal): {e}")
        health = None
        recs = []

    outputs = {
        "health.json": get_health() if health else {"data_quality": "missing", "assembled_at": datetime.utcnow().isoformat() + "Z"},
        "recommendations.json": get_recommendations(missions, health),
        "blockers.json": get_blockers(missions),
        "captain-brief.json": get_captain_brief(missions, recs),
        "operating-picture.json": get_operating_picture(missions, recs),
    }

    for filename, data in outputs.items():
        path = CONTEXT_OUTPUT_DIR / filename
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        _out(f"[context-service] Wrote {path}")

    _out(f"[context-service] All context outputs generated → {CONTEXT_OUTPUT_DIR}")


# ---------------------------------------------------------------------------
# WP-A: HTTP service (Flask)
# ---------------------------------------------------------------------------

def _http_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_flask_app():
    """
    Build and return the Flask app. Separated from module level so the
    import is deferred — CLI usage never pays the Flask import cost.
    """
    from flask import Flask, jsonify, request
    from flask_cors import CORS

    http_app = Flask(__name__)
    CORS(http_app)

    # 2026-07-10: this service is about to be reachable from the public
    # internet (via Caddy, see deploy/context-service.service) for the
    # first time - previously it only ever ran on localhost, where an
    # open endpoint was harmless. CONTEXT_SERVICE_SECRET is optional so
    # local dev (where the var is deliberately unset) keeps working
    # unauthenticated - but once it IS configured (real deployment), every
    # route except /health fails closed on a missing/wrong secret, matching
    # this whole platform's "no exceptions" governance stance rather than
    # leaving real Captain data on an unauthenticated public endpoint.
    @http_app.before_request
    def _require_secret():
        if request.path == "/health":
            return None
        expected = os.environ.get("CONTEXT_SERVICE_SECRET")
        if not expected:
            return None
        provided = request.headers.get("X-Context-Service-Secret")
        if provided != expected:
            return jsonify({"error": "unauthorized"}), 401
        return None

    @http_app.get("/health")
    def http_health():
        try:
            corpus = _load_corpus()
            return jsonify({
                "status": "healthy",
                "service": "context-assembly",
                "corpus": {
                    "missions": len(corpus["missions"]),
                    "decisions": len(corpus["decisions"]),
                    "adrs": len(corpus["adrs"]),
                    "capabilities": len(corpus["capabilities"]),
                },
                "checked_at": _http_timestamp(),
            })
        except Exception as exc:
            return jsonify({
                "status": "unhealthy",
                "error": str(exc),
                "checked_at": _http_timestamp(),
            }), 500

    @http_app.get("/brief/captain")
    def http_captain_brief():
        try:
            return jsonify(_http_captain_brief())
        except Exception as exc:
            return jsonify({
                "error": "captain_brief_failed",
                "detail": str(exc),
                "assembled_at": _http_timestamp(),
            }), 500

    @http_app.get("/brief/number-one")
    def http_number_one_brief():
        try:
            return jsonify(_http_number_one_brief())
        except Exception as exc:
            return jsonify({
                "error": "number_one_brief_failed",
                "detail": str(exc),
                "assembled_at": _http_timestamp(),
            }), 500

    @http_app.get("/queue/health-adjusted")
    def http_health_adjusted_queue():
        try:
            return jsonify(_http_health_adjusted_queue())
        except Exception as exc:
            return jsonify({
                "error": "health_adjusted_queue_failed",
                "detail": str(exc),
                "assembled_at": _http_timestamp(),
            }), 500

    # ── Real Captain's Brief + Recommendations, over HTTP ──────────────────
    # 2026-07-10: lcars-portal's api/captain-brief and api/recommendations
    # routes previously shelled out to a local python3 CLI
    # (execFile('python3', ['-m', 'core.platform.captain_brief_cli', ...]))
    # - a pattern that cannot work once the Next.js app is deployed to
    # Vercel's Node.js serverless runtime (no python3 available there at
    # all). This service already runs as a real, persistent Flask process
    # somewhere Python genuinely is available - these two routes expose the
    # exact same underlying functions those CLIs called, over HTTP, so the
    # Vercel-hosted routes can reach them with a plain fetch() instead.
    # Reuses the real logic verbatim (same imports, same call shape, same
    # serialization) - no reimplementation, no second copy.

    @http_app.get("/brief/full")
    def http_full_captain_brief():
        try:
            import dataclasses
            from core.platform.captain_brief_orchestrator import assemble_captain_brief_document
            from core.platform.event_bus import poll_events

            limit = int(_request_arg("limit", 200))
            events = poll_events(limit=limit)
            doc = assemble_captain_brief_document(events)
            return jsonify(dataclasses.asdict(doc, dict_factory=_str_default_asdict))
        except Exception as exc:
            return jsonify({
                "error": "full_captain_brief_failed",
                "detail": str(exc),
                "assembled_at": _http_timestamp(),
            }), 500

    @http_app.get("/recommendations/full")
    def http_recommendations_full():
        try:
            return jsonify(get_recommendations())
        except Exception as exc:
            return jsonify({
                "error": "recommendations_failed",
                "detail": str(exc),
                "assembled_at": _http_timestamp(),
            }), 500

    # 2026-08-09: lcars-portal's api/captain-intelligence/generate route
    # still shelled out to `python3 -m core.platform.captain_brief_cli
    # --evolved` (execFile) three weeks after the identical pattern was
    # diagnosed and fixed for /brief/full above (2026-07-10, see that
    # commit) - same root cause, same fix. This endpoint is the evolved-
    # pipeline counterpart to /brief/full: reuses assemble_evolved_captain_
    # brief() verbatim (the same function captain_brief_cli.py --evolved
    # called), no reimplemented logic.
    #
    # POST, not GET, matching the Next.js route's own reasoning: this
    # triggers real HTTP calls to the model router (50-260s observed,
    # MSN-0329 Phase 3) and persists to insight_outcomes on every call
    # (assemble_evolved_captain_brief -> record_insight) - a real side
    # effect, not an idempotent read, so it must stay an explicit action
    # rather than something that could fire on every page load or from a
    # cached/prefetched GET.
    @http_app.post("/brief/evolved")
    def http_evolved_captain_brief():
        try:
            import dataclasses
            from core.platform.captain_brief_evolution import assemble_evolved_captain_brief
            from core.platform.event_bus import poll_events

            limit = int(_request_arg("limit", 200))
            events = poll_events(limit=limit)
            doc = assemble_evolved_captain_brief(events)
            return jsonify(dataclasses.asdict(doc, dict_factory=_str_default_asdict))
        except Exception as exc:
            return jsonify({
                "error": "evolved_captain_brief_failed",
                "detail": str(exc),
                "assembled_at": _http_timestamp(),
            }), 500

    return http_app


def create_app():
    """WSGI entrypoint for gunicorn.

    Thin wrapper around _make_flask_app() so a production WSGI server gets
    the exact same Flask app the CLI's `serve` subcommand builds — gunicorn
    is pointed at this via the app-factory target syntax
    `context_service:create_app()` (see _run_gunicorn() and
    deploy/context-service.service, both of which use this same target).
    """
    return _make_flask_app()


def _request_arg(name: str, default):
    """Reads a query-string arg from the active Flask request - deferred
    import so CLI usage never pays the Flask import cost, matching every
    other function in this HTTP-only section."""
    from flask import request
    val = request.args.get(name)
    return val if val is not None else default


def _str_default_asdict(fields) -> dict:
    """dataclasses.asdict's dict_factory - matches captain_brief_cli.py's
    json.dumps(..., default=str) behaviour (dates/enums render as strings)
    while still returning a real dict for jsonify, not a JSON string."""
    result = {}
    for key, value in fields:
        try:
            json.dumps(value)
            result[key] = value
        except TypeError:
            result[key] = str(value)
    return result


def _http_captain_brief() -> dict:
    """
    Assemble Captain Brief for HTTP endpoint.

    Health is summary-level only: workload_constraint, data_quality, safety_flags.
    No pain_level / mood / energy / stress exposed.
    """
    missions_list = _load_missions()
    corpus = _load_corpus()

    # Health — summary level only
    health_summary: dict = {"workload_constraint": "unknown", "data_quality": "missing", "safety_flags": []}
    try:
        health = assemble_health_context()
        health_summary = {
            "workload_constraint": health.workload_constraint,
            "data_quality": health.data_quality,
            "safety_flags": health.safety_flags,
        }
    except Exception:
        pass

    # Blockers
    blocker_list = []
    try:
        for b in assemble_blockers(missions_list):
            blocker_list.append({
                "mission_id": b.mission_id,
                "mission_title": b.mission_title,
                "escalation_level": b.escalation_level,
                "recommended_action": b.recommended_action,
                "dependent_missions": b.dependent_missions,
            })
    except Exception:
        pass

    # Decisions awaiting input
    pending_decisions = []
    try:
        for d in assemble_decisions_awaiting_input():
            pending_decisions.append({
                "decision_id": d.decision_id,
                "date": d.date,
                "question": (d.question or "")[:200],
                "urgency": d.urgency,
                "awaiting_captain_input": d.awaiting_captain_input,
            })
    except Exception:
        pass

    # Top priorities from corpus packages
    packages = {}
    for mid in corpus["missions"]:
        try:
            pkg = assemble_mission_context(mid, corpus)
            if pkg:
                packages[mid] = pkg
        except Exception:
            pass

    TERMINAL = {"COMPLETED", "CANCELLED", "CLOSED", "ARCHIVED", "COMPLETE"}

    def _score(m):
        p_raw = (m.get("priority") or "P3").upper().replace(" ", "")
        p = p_raw[:2] if p_raw.startswith("P") and len(p_raw) > 1 and p_raw[1].isdigit() else "P3"
        pnum = int(p[1])
        parts = (m.get("status") or "").upper().split()
        s = parts[0] if parts else ""
        return pnum * 10 + {"IN_PROGRESS": 0, "ACTIVE": 0, "BLOCKED": -1}.get(s, 5)

    active = [
        m for m in corpus["missions"].values()
        if ((m.get("status") or "").upper().split() or [""])[ 0] not in TERMINAL
    ]
    priorities = []
    for m in sorted(active, key=_score)[:5]:
        mid = m["id"]
        pkg = packages.get(mid)
        priorities.append({
            "mission_id": mid,
            "title": m.get("title", mid),
            "status": m.get("status", ""),
            "owner": m.get("owner", ""),
            "priority": m.get("priority", ""),
            "completeness_score": pkg.completeness_score if pkg else None,
            "governing_adrs": [r.id for r in pkg.governing_adrs] if pkg else [],
            "depends_on": [r.id for r in pkg.dependencies] if pkg else [],
        })

    # Corpus metrics
    pkg_scores = [p.completeness_score for p in packages.values()]
    avg_completeness = round(sum(pkg_scores) / len(pkg_scores), 2) if pkg_scores else 0.0

    return {
        "assembled_at": _http_timestamp(),
        "source": "context_assembly_service",
        "corpus": {
            "missions": len(corpus["missions"]),
            "decisions": len(corpus["decisions"]),
            "adrs": len(corpus["adrs"]),
            "capabilities": len(corpus["capabilities"]),
            "avg_completeness": avg_completeness,
        },
        "health": health_summary,
        "top_priorities": priorities,
        "blockers": blocker_list,
        "decisions_awaiting_input": pending_decisions,
    }


def _work_queue_item_to_dict(item) -> dict:
    return {
        "mission_id": item.mission_id,
        "priority": item.priority.value,
        "status": item.status.value,
        "title": item.title,
        "assigned_specialist": item.assigned_specialist,
        "next_action": item.next_action,
        "blockers": item.blockers,
        "dependencies": item.dependencies,
        "confidence": item.confidence,
        "confidence_band": item.confidence_band.value if item.confidence_band else None,
        "rationale": item.rationale,
        "engineering_status": item.engineering_status,
    }


def _escalation_to_dict(esc) -> dict:
    return {
        "escalation_type": esc.escalation_type,
        "mission_id": esc.mission_id,
        "level": esc.level.value,
        "reason": esc.reason,
        "data": esc.data,
        "recommendation": esc.recommendation,
        "timestamp": esc.timestamp.isoformat() if esc.timestamp else None,
    }


def _pr_health_escalations(missions: list) -> list[dict]:
    """Check GitHub PR status for every mission/engineering-handoff carrying
    a pr_url (core/coordination/pr_health.py) and generate escalation-shaped
    dicts for what Number One's own rule-based checks can't see at all:
    failing CI, or a reviewer requesting changes. Captain direction
    (2026-09-08): "the role Number One plays is to review and catch things
    I wouldn't pick up on, as I can't review code" — this is that.

    Best-effort in both directions: pr_health.check_pr_health() never raises
    (bad/missing token, network failure, PR not found all just skip that
    one PR), and this function only ever ADDS escalations on top of
    NumberOne's own rule-based ones — it can never suppress or block them.
    """
    sys.path.insert(0, str(REPO_ROOT / "core" / "coordination"))
    from pr_health import check_pr_health  # noqa: PLC0415

    escalations = []
    seen_urls: set[str] = set()
    for m in missions:
        pr_url = (m.get("metadata") or {}).get("pr_url")
        if not pr_url or pr_url in seen_urls:
            continue
        seen_urls.add(pr_url)

        health = check_pr_health(pr_url)
        if not health.get("ok") or health.get("state") != "open":
            continue

        mission_id = m.get("mission_id", "")
        if health.get("ci_conclusion") == "failure":
            escalations.append({
                "escalation_type": "PR_CI_FAILING",
                "mission_id": mission_id,
                "level": "HIGH",
                "reason": f"CI is red on the open PR for {mission_id}",
                "data": {"pr_url": pr_url, "ci_conclusion": health["ci_conclusion"]},
                "recommendation": f"Review the CI failure at {pr_url}",
                "timestamp": None,
            })
        if health.get("review_state") == "CHANGES_REQUESTED":
            escalations.append({
                "escalation_type": "PR_CHANGES_REQUESTED",
                "mission_id": mission_id,
                "level": "MEDIUM",
                "reason": f"A reviewer requested changes on the open PR for {mission_id}",
                "data": {"pr_url": pr_url, "review_state": health["review_state"]},
                "recommendation": f"Address the review feedback at {pr_url}",
                "timestamp": None,
            })
    return escalations


def _capacity_status_for_today() -> str:
    """Today's Green/Amber/Red/Unknown capacity status, from the same live
    Captain's Log + capacity_score.py pipeline that already powers the
    Human Systems Capacity Gate (core/health/capacity_gate.py, D-055) —
    not a new source of truth, just this endpoint's first use of the
    existing one. Never raises: falls back to "Unknown" on any failure
    (no Supabase config, no check-in today, import error), matching
    get_health_adjusted_queue()'s own honest-Unknown handling.
    """
    try:
        sys.path.insert(0, str(REPO_ROOT / "core" / "coordination"))
        from health_context_adapter import build_health_context_live  # noqa: PLC0415

        health = build_health_context_live()
        return health.capacity_status or "Unknown"
    except Exception as exc:
        _err(f"Could not resolve today's capacity status — defaulting to Unknown: {exc}")
        return "Unknown"


def _http_health_adjusted_queue() -> dict:
    """Number One's capacity-aware work queue (get_health_adjusted_queue())
    over HTTP — the same engine call _http_number_one_brief() makes for the
    daily brief, but exposing the queue's own capacity_note/recommended_focus/
    advisory overlay directly rather than folding it into the brief.

    2026-09-08 (USS-TJR-MSN-0054 follow-on): get_health_adjusted_queue() was
    already built and tested-by-nobody in number_one.py with zero live
    callers, same situation NumberOne itself was in before this mission.
    Reuses the exact same mission-loading path as the brief (live Supabase
    overlay + approved engineering handoffs) so the queue and the brief
    never disagree about what "today's missions" means.
    """
    sys.path.insert(0, str(REPO_ROOT / "core" / "coordination"))
    from number_one import NumberOne  # noqa: PLC0415
    from engineering_handoff_reader import load_engineering_handoffs  # noqa: PLC0415

    missions = _load_live_missions_for_number_one()
    try:
        missions = missions + load_engineering_handoffs()
    except Exception as exc:
        _err(f"Could not load engineering handoffs: {exc}")

    capacity_status = _capacity_status_for_today()
    queue = NumberOne().get_health_adjusted_queue(missions, capacity_status)

    return {
        "assembled_at": _http_timestamp(),
        "source": "context_assembly_service",
        "engine": "number_one_coordination_engine",
        **queue,
    }


def _http_number_one_brief() -> dict:
    """Assemble Number One Brief via the real NumberOne coordination engine
    (core/coordination/number_one.py) — work queue, blockers, follow-ups,
    escalations, specialist workload, recommended actions.

    2026-09-08 (USS-TJR-MSN-0054): replaces a hand-rolled scoring function
    that reimplemented a thinner version of the same brief logic from
    scratch. NumberOne was well-built and tested (core/coordination/
    test_number_one.py) but had zero live callers anywhere in the platform
    — this endpoint is the first one. _load_missions() already produces the
    mission-dict shape NumberOne.Mission.from_registry() expects (mission_id,
    title, status, priority, domain, blockers, dependencies, next_action,
    assigned_role), so no new adapter was needed — it was already sitting
    there unused, just never called from this function specifically.

    Uses _load_live_missions_for_number_one() (not the plain _load_missions())
    — the file corpus that feeds every other function in this file has no
    live sync with Supabase status changes, only new-mission-ID appends
    (mission-registry-sync.timer), so it overlays live Supabase status/
    priority onto the file corpus by mission_id. See that function's
    docstring for the full reasoning.

    Also merges in approved engineering handoffs (core/coordination/
    engineering_handoff_reader.py's load_engineering_handoffs()) —
    its own docstring already names "Number One's advisory queue" as the
    intended consumer of its default include_completed=False behaviour, but
    nothing had ever actually called it from here. Read-only, non-blocking:
    returns [] and changes nothing if Missions/Engineering-Handoffs/ doesn't
    exist. Deliberately scoped to this function only (not folded into the
    shared _load_missions(), which 8 other call sites in this file depend
    on for their existing, tested behaviour) — Number One's brief is the one
    consumer that should see `[ENG-HANDOFF]`-prefixed synthetic missions.
    """
    sys.path.insert(0, str(REPO_ROOT / "core" / "coordination"))
    from number_one import NumberOne  # noqa: PLC0415
    from engineering_handoff_reader import load_engineering_handoffs  # noqa: PLC0415

    missions = _load_live_missions_for_number_one()
    try:
        missions = missions + load_engineering_handoffs()
    except Exception as exc:
        _err(f"Could not load engineering handoffs: {exc}")
    brief = NumberOne().get_daily_brief(missions)

    escalations = [_escalation_to_dict(e) for e in brief.escalations]
    try:
        escalations += _pr_health_escalations(missions)
    except Exception as exc:
        _err(f"Could not check PR health: {exc}")

    return {
        "assembled_at": _http_timestamp(),
        "source": "context_assembly_service",
        "engine": "number_one_coordination_engine",
        "generated_at": brief.timestamp.isoformat(),
        "system_health": brief.system_health,
        "total_missions": brief.total_missions,
        "active_count": brief.active_count,
        "blocked_count": brief.blocked_count,
        "proposed_count": brief.proposed_count,
        "top_priorities": [_work_queue_item_to_dict(i) for i in brief.top_priorities],
        "blocked_missions": [_work_queue_item_to_dict(i) for i in brief.blocked_missions],
        "follow_ups": brief.follow_ups,
        "escalations": escalations,
        "specialist_workload": brief.specialist_workload,
        "recommended_actions": brief.recommended_actions,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _out(msg: str):
    print(msg, file=sys.stderr)


def _err(msg: str):
    print(f"[context-service] WARN: {msg}", file=sys.stderr)


def _run_gunicorn(host: str, port: int):
    """Launch gunicorn against this Flask app instead of calling
    flask_app.run() (the Werkzeug dev server).

    Replaces this process (os.execvp — no child process to babysit or
    forget to reap) so `python3 context_service.py serve --host ... --port
    ...` keeps working unchanged for every existing caller (deploy/
    context-service.service, local dev, docs above) while gunicorn's
    production workers actually handle every request from here on.

    --chdir / --pythonpath both point at this script's own directory:
    core/context-assembly isn't a dotted-importable package (the "-" in
    the directory name rules that out, see the sys.path comment near the
    top of this file), so gunicorn needs this directory on sys.path to
    resolve the bare `context_service` module name in the app-factory
    target below. config.py / loaders.py resolve everything via
    Path(__file__), not cwd, so chdir-ing here is safe.

    --worker-class gthread --threads 4 (single worker process) reproduces
    flask_app.run(..., threaded=True)'s "don't let one slow request stall
    every other route" behavior without also running N separate copies of
    this stateless-but-not-cheap-to-import process. --timeout 300 is
    required, not cosmetic: gunicorn's default 30s worker timeout would
    kill /brief/evolved's real LLM calls mid-flight (50-260s observed,
    MSN-0329 Phase 3) as unresponsive.
    """
    script_dir = str(Path(__file__).resolve().parent)
    gunicorn_bin = shutil.which("gunicorn") or os.path.join(os.path.dirname(sys.executable), "gunicorn")
    cmd = [
        gunicorn_bin,
        "--bind", f"{host}:{port}",
        "--chdir", script_dir,
        "--pythonpath", script_dir,
        "--worker-class", "gthread",
        "--workers", "1",
        "--threads", "4",
        "--timeout", "300",
        "context_service:create_app()",
    ]
    _out(f"[context-service] Launching gunicorn: {' '.join(cmd)}")
    os.execvp(cmd[0], cmd)


def main():
    parser = argparse.ArgumentParser(description="Context Assembly Service")
    parser.add_argument("command", nargs="?", default="all",
                        choices=["all", "captain-brief", "operating-picture",
                                 "health", "blockers", "recommendations", "mission",
                                 "serve"],
                        help="Which context to assemble, or 'serve' to start HTTP server")
    parser.add_argument("mission_id", nargs="?", default=None,
                        help="Mission ID for 'mission' command")
    parser.add_argument("--port", type=int, default=None,
                        help="HTTP port for 'serve' command (default: CONTEXT_SERVICE_PORT or 5001)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host for 'serve' command (default: 127.0.0.1)")
    args = parser.parse_args()

    # HTTP server mode (WP-A)
    if args.command == "serve":
        port = args.port or config.CONTEXT_SERVICE_PORT
        print(f"[context-service] Starting HTTP server on http://{args.host}:{port}")
        print(f"[context-service] Endpoints: GET /health  GET /brief/captain  GET /brief/number-one  GET /queue/health-adjusted  GET /brief/full  GET /recommendations/full  POST /brief/evolved")
        _run_gunicorn(args.host, port)
        return

    try:
        if args.command == "all":
            generate_all_outputs()
            return

        result = None
        if args.command == "health":
            result = get_health()
        elif args.command == "recommendations":
            result = get_recommendations()
        elif args.command == "blockers":
            result = get_blockers()
        elif args.command == "captain-brief":
            result = get_captain_brief()
        elif args.command == "operating-picture":
            result = get_operating_picture()
        elif args.command == "mission":
            if not args.mission_id:
                print(json.dumps({"error": "mission_id required"}))
                sys.exit(1)
            result = get_mission_context(args.mission_id)
            if result is None:
                print(json.dumps({"error": f"Mission {args.mission_id} not found"}))
                sys.exit(1)

        print(json.dumps(result, indent=2, default=str))

    except Exception as e:
        print(json.dumps({"error": str(e), "assembled_at": datetime.utcnow().isoformat() + "Z"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
