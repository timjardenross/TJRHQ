"""
API-level governance surface (Phase A §2.1) — transport-agnostic.

The USS-TJR intelligence platform has no standalone HTTP server (it is Python
modules + scheduler + Supabase, consumed by the LCARS portal API routes and the
bots). Rather than stand up a parallel server (which CLAUDE.md forbids), the
governance "endpoints" are expressed as a pure dispatcher:

    dispatch(repo, action, role, payload) -> (status_code, body)

Any transport — an LCARS Next.js route proxying to a tiny Python worker, a bot
command, a CLI, or the optional Flask blueprint below — maps one request to one
dispatch() call. Enforcement lives in one place (the workflow service), so every
surface gets identical RBAC + lifecycle + audit behaviour.

HTTP status mapping:
    AuthorizationError -> 403   NotFoundError -> 404
    GovernanceError    -> 400   (validation / illegal transition / bad input)
    unknown action     -> 404   unexpected error -> 500
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from intelligence.governance.workflow_gate import (
    AuthorizationError,
    GovernanceError,
    NotFoundError,
)
from intelligence.workflow import service

log = logging.getLogger(__name__)

ROLE_HEADER = "X-User-Role"


def _h_verify(repo, role, p):
    return service.verify_event(repo, role, p["event_id"], p["confidence_level"],
                                p.get("verified_against"))


def _h_select(repo, role, p):
    return service.select_events(repo, role, p["brief_id"], p["event_ids"])


def _h_curate(repo, role, p):
    return service.curate_watchlist(repo, role, p["brief_id"], p["items"])


def _h_qa_gate(repo, role, p):
    return service.set_qa_gate(repo, role, p["brief_id"], p["gate"], p.get("status", "passed"))


def _h_mark_qa_ready(repo, role, p):
    return service.mark_qa_ready(repo, role, p["brief_id"])


def _h_publish(repo, role, p):
    return service.publish_brief(repo, role, p["brief_id"], p.get("published_at"))


def _h_lesson(repo, role, p):
    return service.record_lesson(repo, role, p["brief_id"], p["lesson_text"],
                                 p.get("category", "other"))


# action name -> (handler, required payload keys)
ACTIONS: dict[str, tuple[Callable, tuple[str, ...]]] = {
    "signal.verify":         (_h_verify, ("event_id", "confidence_level")),
    "signal.select":         (_h_select, ("brief_id", "event_ids")),
    "brief.curate_watchlist": (_h_curate, ("brief_id", "items")),
    "brief.qa_gate":         (_h_qa_gate, ("brief_id", "gate")),
    "brief.mark_qa_ready":   (_h_mark_qa_ready, ("brief_id",)),
    "brief.publish":         (_h_publish, ("brief_id",)),
    "brief.record_lesson":   (_h_lesson, ("brief_id", "lesson_text")),
}


def dispatch(repo, action: str, role: str, payload: dict) -> tuple[int, dict]:
    """Route one governed action. Returns (http_status, body)."""
    entry = ACTIONS.get(action)
    if entry is None:
        return 404, {"error": f"unknown action '{action}'"}
    handler, required = entry

    if not role:
        return 403, {"error": "missing role"}
    missing = [k for k in required if k not in (payload or {})]
    if missing:
        return 400, {"error": f"missing fields: {', '.join(missing)}"}

    try:
        result = handler(repo, role, payload or {})
        return 200, {"ok": True, "result": result}
    except AuthorizationError as exc:
        return 403, {"error": str(exc)}
    except NotFoundError as exc:
        return 404, {"error": str(exc)}
    except GovernanceError as exc:
        return 400, {"error": str(exc)}
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("dispatch(%s) unexpected error", action)
        return 500, {"error": "internal error", "detail": str(exc)}


def extract_role(headers: Any) -> str:
    """Read the actor role from a headers mapping (case-insensitive-ish)."""
    if not headers:
        return ""
    try:
        return (headers.get(ROLE_HEADER) or headers.get(ROLE_HEADER.lower()) or "").strip()
    except AttributeError:
        return ""


def make_blueprint(repo_factory: Callable[[], Any]):
    """Optional Flask blueprint mounting one route per action. Import-guarded so
    the workflow package never hard-depends on Flask. `repo_factory` returns a
    WorkflowRepository per request (e.g. SupabaseRepository)."""
    from flask import Blueprint, jsonify, request  # noqa: F401 (optional dep)

    bp = Blueprint("intelligence_governance", __name__)

    def _make_view(action: str):
        def _view():
            role = extract_role(request.headers)
            payload = request.get_json(silent=True) or {}
            status, body = dispatch(repo_factory(), action, role, payload)
            return jsonify(body), status
        _view.__name__ = f"view_{action.replace('.', '_')}"
        return _view

    for action in ACTIONS:
        path = "/intelligence/" + action.replace(".", "/")
        bp.add_url_rule(path, endpoint=action, view_func=_make_view(action), methods=["POST"])
    return bp
