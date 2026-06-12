"""WP8 — /captain-brief and /operating-picture Slack slash commands.

Retrieves assembled context from the Context Assembly service (WP6) and
formats it for Slack. No LLM synthesis here — the brief is pre-assembled by
the Python Context Assembly Foundation (WP1–6).

Data source priority:
  1. Command Centre HTTP API  (localhost:5050, Express — WP6, uses TTL cache)
  2. context_service.py CLI   (subprocess fallback, bypasses Express)
  3. Degraded placeholder     (both unavailable)

Public API:
    fetch_and_format_captain_brief() -> list[dict]    Block Kit blocks
    fetch_and_format_operating_picture() -> list[dict] Block Kit blocks
    handle_captain_brief(text, user_id, channel_id) -> str   mrkdwn string
    handle_operating_picture(text, user_id, channel_id) -> str mrkdwn string
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTEXT_SERVICE_PY = _REPO_ROOT / "core" / "context-assembly" / "context_service.py"
_PYTHON = sys.executable

# WP6 Express backend — configurable for staging
_API_BASE = os.environ.get("COMMAND_CENTRE_API", "http://localhost:5050")
_TIMEOUT = int(os.environ.get("CONTEXT_SERVICE_TIMEOUT", "8"))

_ENDPOINT = {
    "captain-brief":    f"{_API_BASE}/api/v1/context/captain-brief",
    "operating-picture": f"{_API_BASE}/api/v1/context/operating-picture",
}


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _fetch(context_name: str) -> dict[str, Any] | None:
    """Fetch context: WP6 Express API → context_service.py CLI → None."""

    # 1. Try the Express API (fastest — uses TTL cache from WP6)
    url = _ENDPOINT.get(context_name)
    if url:
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                envelope = json.loads(resp.read())
                data = envelope.get("data") or envelope
                source = (envelope.get("metadata") or {}).get("source", "api")
                log.info("[captain-brief] API hit: %s (source=%s)", context_name, source)
                return data
        except Exception as exc:
            log.warning("[captain-brief] API unavailable for %s (%s) — CLI fallback", context_name, exc)

    # 2. Fall back to spawning context_service.py directly
    if _CONTEXT_SERVICE_PY.exists():
        try:
            result = subprocess.run(
                [_PYTHON, str(_CONTEXT_SERVICE_PY), context_name],
                capture_output=True,
                text=True,
                timeout=20,
                cwd=str(_REPO_ROOT),
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                log.info("[captain-brief] CLI fallback succeeded: %s", context_name)
                return data
            log.warning("[captain-brief] CLI non-zero for %s: %s", context_name, result.stderr[:200])
        except Exception as exc:
            log.warning("[captain-brief] CLI failed for %s: %s", context_name, exc)

    return None


# ---------------------------------------------------------------------------
# Block Kit helpers
# ---------------------------------------------------------------------------

def _divider() -> dict:
    return {"type": "divider"}

def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

def _header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}

def _context_block(*texts: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": t} for t in texts]}


# ---------------------------------------------------------------------------
# Captain Brief — Block Kit formatter
# ---------------------------------------------------------------------------

def _format_brief_blocks(brief: dict[str, Any]) -> list[dict]:
    blocks: list[dict] = []
    date = brief.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assembled_at = brief.get("assembled_at", "")
    source = brief.get("source") or "unknown"

    # Header
    blocks.append(_header(f"⚓ Captain's Daily Brief — {date}"))
    blocks.append(_context_block(
        f"Assembled: {assembled_at or date}",
        f"Source: {source}",
        "Context Assembly Foundation — WP1–8",
    ))
    blocks.append(_divider())

    # Health
    health = brief.get("health")
    if health and health.get("data_quality") != "missing":
        ss = health.get("status_summary") or {}
        parts = []
        if ss.get("pain_level"):  parts.append(f"Pain: *{ss['pain_level']}*")
        if ss.get("energy"):      parts.append(f"Energy: *{ss['energy']}*")
        if ss.get("mood"):        parts.append(f"Mood: *{ss['mood']}*")
        wc = health.get("workload_constraint")
        if wc and wc != "normal":
            parts.append(f"Workload: *{wc.upper()}* :warning:")
        safety = health.get("safety_flags") or []
        health_text = "🏥 *Health* — " + ("  ·  ".join(parts) if parts else "_No data_")
        if safety:
            health_text += f"\n⚠️ Safety flags: {', '.join(safety)}"
        blocks.append(_section(health_text))
        blocks.append(_divider())

    # Top priorities
    priorities = brief.get("top_priorities") or []
    if priorities:
        blocks.append(_section("*📌 Top Priorities*"))
        for p in priorities[:3]:
            rank = p.get("priority_rank", "?")
            title = p.get("title") or p.get("mission_id") or "—"
            mid = p.get("mission_id", "")
            action = p.get("next_action") or ""
            urgency = p.get("deadline_urgency", "")
            confidence = p.get("confidence")
            conf_tag = f"  `{int(confidence * 100)}% conf`" if confidence is not None else ""
            urgency_tag = "  :fire:" if urgency == "high" else ""
            note = p.get("health_constraint_note")
            constraint_tag = f"\n   _Health constraint: {note}_" if note else ""
            mid_tag = f"`{mid}`  " if mid else ""
            detail = f"{rank}. {mid_tag}*{title}*{urgency_tag}{conf_tag}"
            if action:
                detail += f"\n   → {action}{constraint_tag}"
            blocks.append(_section(detail))
    else:
        blocks.append(_section("_No active priorities._"))
    blocks.append(_divider())

    # Blockers
    blockers = brief.get("blockers") or []
    if blockers:
        blocks.append(_section(f"*🔴 Blockers ({len(blockers)})*"))
        for b in blockers[:3]:
            esclvl = b.get("escalation_level", "")
            icon = "🔴" if esclvl == "critical" else "🟡" if esclvl == "high" else "⚪"
            mid = b.get("mission_id", "?")
            title = b.get("mission_title", mid)
            action = b.get("recommended_action") or ""
            esc_tag = f"  `{esclvl.upper()}`" if esclvl else ""
            text = f"{icon} *{mid}* — {title}{esc_tag}"
            if action:
                text += f"\n   → {action}"
            blocks.append(_section(text))
    else:
        blocks.append(_section("🟢 *No blockers detected.*"))
    blocks.append(_divider())

    # Decisions awaiting input
    decisions = brief.get("decisions_awaiting_input") or []
    if decisions:
        blocks.append(_section(f"*⚖️ Decisions Awaiting Captain ({len(decisions)})*"))
        for d in decisions[:4]:
            did = d.get("decision_id", "")
            question = (d.get("question") or "")[:160]
            urgency = d.get("urgency") or ""
            urg_tag = f"  `{urgency}`" if urgency and urgency not in ("none", "normal") else ""
            blocks.append(_section(f"• `{did}`{urg_tag}\n  _{question}_"))
    else:
        blocks.append(_section("✅ *No decisions awaiting Captain input.*"))
    blocks.append(_divider())

    # System health
    sys_health = brief.get("system_health") or {}
    status = sys_health.get("status", "green")
    alert_count = sys_health.get("alert_count", 0)
    active = sys_health.get("active_mission_count", 0)
    blocked_count = sys_health.get("blocked_mission_count", 0)
    status_icon = "🟢" if status == "green" else "🟡" if status == "yellow" else "🔴"
    blocks.append(_section(
        f"{status_icon} *System* — {status.upper()}  ·  "
        f"{active} active  ·  {blocked_count} blocked  ·  {alert_count} alert(s)"
    ))

    # Key dates
    key_dates = brief.get("key_dates_this_week") or []
    if key_dates:
        blocks.append(_divider())
        blocks.append(_section("*📅 Key Dates This Week*"))
        date_lines = [f"• {kd.get('date', '?')} — {kd.get('label', '?')}  `{kd.get('mission_id', '?')}`"
                      for kd in key_dates[:5]]
        blocks.append(_section("\n".join(date_lines)))

    # Number One summary
    n1 = brief.get("number_one_summary")
    if n1:
        blocks.append(_divider())
        blocks.append(_section(f"📡 *Number One:*\n_{n1}_"))

    blocks.append(_divider())
    blocks.append(_context_block(
        "Health detail is intentionally summary-level only.",
        "Use `/operating-picture` for the 5-minute view.",
    ))
    return blocks


def _format_brief_degraded(reason: str) -> list[dict]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return [
        _header("⚓ Captain's Daily Brief — Starship Endeavour"),
        _context_block(f"Requested: {now}", "Source: fallback (service unavailable)"),
        _divider(),
        _section(
            f":warning: *Context Assembly service is unavailable.*\n\n"
            f"Reason: `{reason}`\n\n"
            "To restore:\n"
            f"• Start the Command Centre backend: `cd core/command-centre && npm start`\n"
            f"• Or run directly: `python3 core/context-assembly/context_service.py captain-brief`\n"
            f"• Verify API: `curl {_API_BASE}/api/v1/context/status`"
        ),
        _divider(),
        _context_block("Context Assembly — WP8  |  degraded-state fallback"),
    ]


# ---------------------------------------------------------------------------
# Operating Picture — Block Kit formatter
# ---------------------------------------------------------------------------

def _format_cop_blocks(cop: dict[str, Any]) -> list[dict]:
    blocks: list[dict] = []
    assembled_at = cop.get("assembled_at", "")
    source = cop.get("source") or "unknown"

    overall = (cop.get("operational_status") or {}).get("overall", "green")
    status_icon = "🟢" if overall == "green" else "🟡" if overall == "yellow" else "🔴"

    blocks.append(_header(f"🎯 Captain Operating Picture  {status_icon} {overall.upper()}"))
    blocks.append(_context_block(
        f"Assembled: {assembled_at}",
        f"Source: {source}",
        "5-minute view  |  /operating-picture",
    ))
    blocks.append(_divider())

    # Health snapshot
    hs = cop.get("health_snapshot") or {}
    if hs:
        parts = []
        if hs.get("pain_level"):  parts.append(f"Pain: *{hs['pain_level']}*")
        if hs.get("energy"):      parts.append(f"Energy: *{hs['energy']}*")
        if hs.get("trend"):       parts.append(f"Trend: *{hs['trend']}*")
        health_text = "🏥 " + ("  ·  ".join(parts) if parts else "_No health data_")
        focus = hs.get("recovery_focus")
        if focus:
            health_text += f"\n   Focus: _{focus}_"
        blocks.append(_section(health_text))
        blocks.append(_divider())

    # Top 3 priorities
    top3 = cop.get("top_3_priorities") or []
    if top3:
        blocks.append(_section("*🚀 Top 3 Priorities*"))
        for p in top3[:3]:
            rank = p.get("rank", "?")
            title = p.get("title") or p.get("mission_id") or "—"
            action = p.get("next_action") or ""
            status = (p.get("status") or "").upper()
            status_tag = f"  `{status}`" if status else ""
            text = f"{rank}. *{title}*{status_tag}"
            if action:
                text += f"\n   → {action}"
            blocks.append(_section(text))
    else:
        blocks.append(_section("_No priorities._"))
    blocks.append(_divider())

    # Blockers summary
    bs = cop.get("blockers_summary") or {}
    count = bs.get("count", 0)
    top_blocker = bs.get("top_blocker")
    alert_count = (cop.get("operational_status") or {}).get("alert_count", 0)

    if count == 0 and alert_count == 0:
        blocks.append(_section("✅ *No blockers.*"))
    else:
        blocker_text = f"🔴 *{count} Blocker(s)*"
        if top_blocker:
            blocker_text += f"\n   → {top_blocker}"
        if alert_count > 0:
            blocker_text += f"\n   ⚠️ {alert_count} system alert(s)"
        blocks.append(_section(blocker_text))
    blocks.append(_divider())

    # Number One
    n1 = cop.get("number_one_says")
    if n1:
        blocks.append(_section(f"📡 *Number One:*\n_{n1}_"))
        blocks.append(_divider())

    # Quick actions
    quick = cop.get("quick_actions") or []
    if quick:
        lines = [f"• {a.get('label') or a.get('action') or str(a)}" for a in quick[:4]]
        blocks.append(_section("⚡ *Quick Actions*\n" + "\n".join(lines)))
        blocks.append(_divider())

    blocks.append(_context_block(
        "Use `/captain-brief` for the full daily brief.",
        "Health detail is intentionally summary-level only.",
    ))
    return blocks


def _format_cop_degraded(reason: str) -> list[dict]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return [
        _header("🎯 Captain Operating Picture — Starship Endeavour"),
        _context_block(f"Requested: {now}", "Source: fallback (service unavailable)"),
        _divider(),
        _section(
            f":warning: *Context Assembly service is unavailable.*\n\n"
            f"Reason: `{reason}`\n\n"
            f"• Start the backend: `cd core/command-centre && npm start`\n"
            f"• Or run: `python3 core/context-assembly/context_service.py operating-picture`"
        ),
        _divider(),
        _context_block("Context Assembly — WP8  |  degraded-state fallback"),
    ]


# ---------------------------------------------------------------------------
# Public entry points — Block Kit (for respond(blocks=...))
# ---------------------------------------------------------------------------

def fetch_and_format_captain_brief() -> list[dict]:
    """Fetch the Captain's Brief and return Slack Block Kit blocks."""
    data = _fetch("captain-brief")
    if data is None:
        return _format_brief_degraded(f"Could not reach {_ENDPOINT['captain-brief']}")
    try:
        return _format_brief_blocks(data)
    except Exception as exc:
        log.error("[captain-brief] Formatting failed: %s", exc)
        return _format_brief_degraded(f"Formatting error: {type(exc).__name__}")


def fetch_and_format_operating_picture() -> list[dict]:
    """Fetch the Operating Picture and return Slack Block Kit blocks."""
    data = _fetch("operating-picture")
    if data is None:
        return _format_cop_degraded(f"Could not reach {_ENDPOINT['operating-picture']}")
    try:
        return _format_cop_blocks(data)
    except Exception as exc:
        log.error("[operating-picture] Formatting failed: %s", exc)
        return _format_cop_degraded(f"Formatting error: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# Public entry points — mrkdwn string (standard command handler interface)
# ---------------------------------------------------------------------------

def handle_captain_brief(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Return a mrkdwn-formatted Captain's Brief string for respond()."""
    blocks = fetch_and_format_captain_brief()
    # Convert Block Kit sections to plain mrkdwn for respond(text=...)
    return _blocks_to_mrkdwn(blocks)


def handle_operating_picture(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Return a mrkdwn-formatted Operating Picture string for respond()."""
    blocks = fetch_and_format_operating_picture()
    return _blocks_to_mrkdwn(blocks)


def _blocks_to_mrkdwn(blocks: list[dict]) -> str:
    """Flatten Block Kit blocks into a plain mrkdwn string."""
    parts: list[str] = []
    for b in blocks:
        btype = b.get("type")
        if btype == "header":
            parts.append(f"*{b['text']['text']}*")
        elif btype == "section":
            parts.append(b["text"]["text"])
        elif btype == "context":
            elems = [e.get("text", "") for e in b.get("elements", [])]
            parts.append("_" + "  |  ".join(elems) + "_")
        # dividers become blank lines (already handled by joining with \n\n)
    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Smoke test (python3 captain_brief.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== /captain-brief smoke test ===")
    blocks = fetch_and_format_captain_brief()
    print(f"Returned {len(blocks)} blocks\n")
    for i, b in enumerate(blocks[:10]):
        btype = b.get("type", "?")
        if btype == "section":
            print(f"  [{i}] section: {b['text']['text'][:100]!r}")
        elif btype == "header":
            print(f"  [{i}] header:  {b['text']['text']!r}")
        elif btype == "divider":
            print(f"  [{i}] divider")
        elif btype == "context":
            print(f"  [{i}] context: {[e.get('text','')[:50] for e in b.get('elements',[])]} ")
    if len(blocks) > 10:
        print(f"  ... ({len(blocks) - 10} more blocks)")

    print("\n=== /operating-picture smoke test ===")
    cop_blocks = fetch_and_format_operating_picture()
    print(f"Returned {len(cop_blocks)} blocks")
    is_degraded = any("service is unavailable" in str(b).lower() for b in cop_blocks)
    print("Status: DEGRADED (service unavailable)" if is_degraded else "Status: LIVE")
