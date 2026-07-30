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

    return http_app


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


def _http_number_one_brief() -> dict:
    """Assemble Number One Brief: priorities, blocker, risk, recommendation."""
    corpus = _load_corpus()
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
    ranked = sorted(active, key=_score)[:3]

    top_priorities = []
    for m in ranked:
        mid = m["id"]
        pkg = packages.get(mid)
        entry: dict = {
            "mission_id": mid,
            "title": m.get("title", mid),
            "status": m.get("status", ""),
            "owner": m.get("owner", ""),
            "priority": m.get("priority", ""),
            "confidence": "HIGH" if pkg and pkg.completeness_score >= 0.7 else "MEDIUM",
        }
        if pkg:
            entry["governed_by"] = [{"id": r.id, "title": r.title} for r in pkg.governing_adrs]
            entry["triggered_by"] = [{"id": r.id, "title": r.title} for r in pkg.triggering_decisions]
            entry["depends_on"] = [{"id": r.id, "title": r.title} for r in pkg.dependencies]
        top_priorities.append(entry)

    # Top blocker — first active mission with an explicit depends_on chain still unresolved
    top_blocker = None
    for mid, pkg in packages.items():
        m = corpus["missions"].get(mid, {})
        if (m.get("status") or "").upper().split()[0] in TERMINAL:
            continue
        if pkg.dependencies:
            dep = pkg.dependencies[0]
            dep_m = corpus["missions"].get(dep.id, {})
            top_blocker = {
                "blocked_mission": mid,
                "blocked_title": m.get("title", mid),
                "blocking_mission": dep.id,
                "blocking_title": dep.title,
                "blocking_status": (dep_m.get("status") or "UNKNOWN").upper(),
                "resolution_path": f"Activate {dep.id} to unblock {mid}",
                "confidence": "HIGH",
                "source": f"explicit depends_on in {mid}",
            }
            break

    # Top risk — governance traceability gap
    no_decision = [
        mid for mid, pkg in packages.items()
        if not pkg.triggering_decisions
        and not corpus["missions"].get(mid, {}).get("is_completed")
    ]
    top_risk = {
        "description": (
            f"Governance traceability gap — {len(no_decision)}/{len(packages)} "
            "active missions have no traceable authorising decision."
        ),
        "severity": "medium",
        "mitigation": "New mission template requires triggered_by at creation time.",
        "affected_missions": no_decision,
        "confidence": "HIGH",
    }

    # Recommended next action
    recommendation = None
    if top_blocker:
        blk_id = top_blocker["blocking_mission"]
        blk_m = corpus["missions"].get(blk_id, {})
        recommendation = {
            "action": f"Activate {blk_id}",
            "mission_id": blk_id,
            "title": blk_m.get("title", blk_id),
            "rationale": (
                f"Activating {blk_id} unblocks {top_blocker['blocked_mission']} "
                f"({top_blocker['blocked_title']}), the highest-priority active mission "
                "with an explicit dependency."
            ),
            "confidence": "HIGH",
            "source": "depends_on traversal",
        }
    elif ranked:
        m = ranked[0]
        recommendation = {
            "action": f"Progress {m['id']}",
            "mission_id": m["id"],
            "title": m.get("title", m["id"]),
            "rationale": "Highest-priority active mission with no blocking dependencies.",
            "confidence": "HIGH",
            "source": "priority ranking",
        }

    return {
        "assembled_at": _http_timestamp(),
        "source": "context_assembly_service",
        "top_priorities": top_priorities,
        "top_blocker": top_blocker,
        "top_risk": top_risk,
        "recommended_next_action": recommendation,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _out(msg: str):
    print(msg, file=sys.stderr)


def _err(msg: str):
    print(f"[context-service] WARN: {msg}", file=sys.stderr)


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
        flask_app = _make_flask_app()
        print(f"[context-service] Starting HTTP server on http://{args.host}:{port}")
        print(f"[context-service] Endpoints: GET /health  GET /brief/captain  GET /brief/number-one  GET /brief/full  GET /recommendations/full")
        flask_app.run(host=args.host, port=port, debug=False)
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
