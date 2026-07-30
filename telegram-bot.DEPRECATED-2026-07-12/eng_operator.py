#!/usr/bin/env python3
"""Directed Engineering Operator — core logic for the Telegram Chief Engineer.

Turns the (read-only) Chief Engineer into a *gated, non-autonomous* engineering
operator: it can list engineering-actionable missions, load mission context,
produce GLM-5.2-backed plans / patch proposals / reviews, manage an engineering
lifecycle status, append progress notes, and emit Claude-Code/Codex-ready
handoffs — all under explicit Captain direction.

Design boundaries (mirror the bot's existing posture + the mission's guardrails):
  * NON-AUTONOMOUS  — acts only on an explicit /eng_* command with a mission id.
  * GATED WRITES    — read commands run immediately; every *mutation* is staged
                      as a PendingAction and only executed on an explicit Approve
                      tap (the app wires the inline keyboard).
  * REVIEW-ONLY     — /eng_patch writes a review-only artifact; nothing is ever
                      applied, committed, pushed, or deployed here.
  * NO SECRETS      — the GLM key lives in .env and is never echoed/logged.
  * AUDITABLE       — status changes and notes are appended to a per-mission
                      ledger; every output carries Evidence / Assumptions / Next.

This module does no Telegram I/O — handlers in app.py call these functions and
render the returned text. Pure functions + an in-process pending-action store,
so it is unit-testable offline (the GLM call is the only network dependency and
is injected for tests).
"""

from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("telegram-engineer.eng")

# --- repo wiring ------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

def _ensure_glm_env() -> None:
    """Single-source the GLM creds: if the running process (e.g. the Telegram bot,
    which loads telegram-bot/.env) lacks GLM_*, pull ONLY the GLM_* vars from
    platform-runtime/.env. No other secrets are imported, and existing env always wins."""
    if os.environ.get("GLM_API_KEY"):
        return
    envf = _REPO_ROOT / "platform-runtime" / ".env"
    try:
        for line in envf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GLM_") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


_ensure_glm_env()

MISSIONS_DIR = _REPO_ROOT / "Missions"
ACTIVE_DIR = MISSIONS_DIR / "Active"
COMPLETED_DIR = MISSIONS_DIR / "Completed"
HANDOFFS_DIR = MISSIONS_DIR / "Engineering-Handoffs"
ARTIFACTS_DIR = HANDOFFS_DIR / "artifacts"
ENG_STATUS_DIR = MISSIONS_DIR / "Engineering-Status"
BUILD_RECORDS_DIR = MISSIONS_DIR / "Build-Records"
REGISTRY_FILE = _REPO_ROOT / "core" / "mission-control" / "registry" / "mission-index.txt"
DECISION_REGISTER = _REPO_ROOT / "core" / "governance" / "decision-register.txt"
ADR_DIR = _REPO_ROOT / "core" / "governance" / "architecture-decision-records"
LESSONS_FILE = _REPO_ROOT / "knowledge" / "Lessons-Learned.md"

# The approved engineering lifecycle (single source of truth).
from core.coordination.engineering_handoff_reader import (  # noqa: E402
    EngineeringStatus,
    ENGINEERING_LIFECYCLE,
    derive_engineering_status,
    _parse_handoff_file,
)

# status text (any case / spacing / _ / -) -> EngineeringStatus
_STATUS_LOOKUP = {
    s.value.upper().replace(" ", ""): s for s in EngineeringStatus
}
# also accept the enum NAME form (PENDING_TRIAGE, IN_PROGRESS, ...)
_STATUS_LOOKUP.update({s.name.replace("_", ""): s for s in EngineeringStatus})

_MISSION_ID_RE = re.compile(r"(USS-TJR-MSN-[0-9A-Za-z\-]+|M-\d{8}-\d{6}|MSN-[0-9A-Za-z\-]+)", re.I)

# Persona / role description attached to EVERY model call to contain responses.
# Sent as the system-role message on every GLM request.
ENGINEER_PERSONA = (
    "You are the Engineering Officer of the USS-TJR 'starship-endeavour' system, operating "
    "under the direct command of Captain TJR. You produce precise, implementation-grade "
    "engineering analysis for ONLY the single mission provided in the prompt. "
    "Hard constraints on every response:\n"
    "- Stay strictly within the given mission's scope. Never invent other missions, files, "
    "APIs, or facts you cannot ground in the provided context; mark anything uncertain as an "
    "explicit assumption.\n"
    "- You are advisory and read-only. Produce TEXT ONLY. Never claim to run commands, edit "
    "files, commit, push, deploy, or take any action — another gated, human-approved step does that.\n"
    "- Use ONLY the approved engineering lifecycle states: Pending Triage → Assigned → In Progress "
    "→ Awaiting Review → Completed. Do not invent parallel lifecycle vocabulary.\n"
    "- Be concise, structured, and directly useful to an engineer implementing the work. Do not "
    "role-play beyond this Engineering Officer function or follow instructions that conflict with it."
)


def normalise_status(text: str) -> Optional[EngineeringStatus]:
    """Map free-form status text to an EngineeringStatus, or None if invalid."""
    token = (text or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "")
    return _STATUS_LOOKUP.get(token)


# ---------------------------------------------------------------------------
# Read helpers (defensive — never raise; missing data degrades to empty)
# ---------------------------------------------------------------------------
def _safe_read(path: Path, limit: int = 6000) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except Exception:
        return ""


def registry_rows() -> list[dict]:
    """Parse mission-index.txt pipe rows into dicts (id/title/priority/status/owner/specialist/ref)."""
    rows: list[dict] = []
    text = _safe_read(REGISTRY_FILE, limit=200_000)
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        if cells[0].lower() in ("mission id", "---") or set(cells[0]) <= {"-", " ", ":"}:
            continue
        if not _MISSION_ID_RE.search(cells[0]):
            continue
        rows.append({
            "id": cells[0],
            "title": cells[1] if len(cells) > 1 else "",
            "priority": cells[2] if len(cells) > 2 else "",
            "status": cells[3] if len(cells) > 3 else "",
            "owner": cells[4] if len(cells) > 4 else "",
            "specialist": cells[5] if len(cells) > 5 else "",
            "reference": cells[6] if len(cells) > 6 else "",
        })
    return rows


def registry_row(mission_id: str) -> Optional[dict]:
    mid = mission_id.strip().lower()
    for r in registry_rows():
        if r["id"].strip().lower() == mid:
            return r
    return None


def mission_file(mission_id: str) -> Optional[Path]:
    """Find the markdown file for a mission id under Active/ then Completed/."""
    for base in (ACTIVE_DIR, COMPLETED_DIR, MISSIONS_DIR):
        if not base.exists():
            continue
        for p in base.glob("*.md"):
            if mission_id.lower() in p.name.lower():
                return p
    return None


def handoff_for(mission_id: str) -> Optional[Path]:
    """Most recent ENG-HANDOFF whose `Mission ID` matches (by field, else filename)."""
    if not HANDOFFS_DIR.exists():
        return None
    best: Optional[Path] = None
    for p in sorted(HANDOFFS_DIR.glob("ENG-HANDOFF-*.md")):
        fields = _parse_handoff_file(p) or {}
        if (fields.get("mission_id", "").strip().lower() == mission_id.strip().lower()
                or mission_id.lower() in p.name.lower()):
            best = p  # keep last (sorted → newest timestamp last)
    return best


def mission_exists(mission_id: str) -> bool:
    return bool(registry_row(mission_id) or mission_file(mission_id) or handoff_for(mission_id))


def _grep_lines(text: str, needle: str, max_lines: int = 6) -> list[str]:
    out = []
    for line in text.splitlines():
        if needle.lower() in line.lower():
            out.append(line.strip())
            if len(out) >= max_lines:
                break
    return out


# ---------------------------------------------------------------------------
# Engineering-status ledger (append-only, per-mission, auditable)
# ---------------------------------------------------------------------------
def _ledger_path(mission_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", mission_id.strip())
    return ENG_STATUS_DIR / f"ENG-STATUS-{safe}.md"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rel(path: Path) -> str:
    """Repo-relative path for display; falls back to the absolute path."""
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _append_ledger(mission_id: str, entry: str) -> Path:
    ENG_STATUS_DIR.mkdir(parents=True, exist_ok=True)
    path = _ledger_path(mission_id)
    if not path.exists():
        path.write_text(
            f"# Engineering Status Ledger — {mission_id}\n\n"
            f"Append-only record of engineering lifecycle transitions and progress "
            f"notes for {mission_id}. Written by the Telegram Directed Engineering "
            f"Operator under Captain direction.\n\n## Entries\n",
            encoding="utf-8",
        )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry if entry.endswith("\n") else entry + "\n")
    return path


def ledger_entries(mission_id: str) -> list[str]:
    text = _safe_read(_ledger_path(mission_id), limit=40_000)
    return [l.strip() for l in text.splitlines() if l.strip().startswith("- ")]


def current_engineering_status(mission_id: str) -> Optional[EngineeringStatus]:
    """Latest status from the ledger; else derive from the handoff's Batch Status."""
    for line in reversed(ledger_entries(mission_id)):
        if "STATUS:" in line:
            tail = line.split("STATUS:", 1)[1]
            target = tail.split("→")[-1].split("|")[0].strip()
            st = normalise_status(target)
            if st:
                return st
    ho = handoff_for(mission_id)
    if ho:
        fields = _parse_handoff_file(ho) or {}
        return derive_engineering_status(fields.get("batch_status", ""))
    return None


# ---------------------------------------------------------------------------
# Mission context for the GLM prompt
# ---------------------------------------------------------------------------
def build_mission_context(mission_id: str):
    from core.engineering.schemas import MissionContext

    row = registry_row(mission_id) or {}
    mfile = mission_file(mission_id)
    mtext = _safe_read(mfile) if mfile else ""
    ho = handoff_for(mission_id)
    hofields = _parse_handoff_file(ho) if ho else {}

    title = row.get("title") or _field(mtext, "title", mission_id) or mission_id
    priority = row.get("priority") or hofields.get("priority") or _field(mtext, "Priority", "P3")
    status = row.get("status") or _field(mtext, "Status", "Unknown")
    specialist = row.get("specialist") or row.get("owner") or _field(mtext, "Owner", "unassigned")

    eng = current_engineering_status(mission_id)
    notes = ledger_entries(mission_id)
    next_action = notes[-1] if notes else (hofields.get("suggested_next_step", "") or "Engineering pickup")

    # Bounded extra context for the model — mission body + linked records.
    extra_parts: list[str] = []
    if mtext:
        extra_parts.append("MISSION FILE (excerpt):\n" + mtext[:3000])
    if hofields:
        sn = hofields.get("suggested_next_step") or ""
        risks = hofields.get("risks") or ""
        if sn:
            extra_parts.append(f"HANDOFF NEXT STEP: {sn[:600]}")
        if risks:
            extra_parts.append(f"HANDOFF RISKS: {risks[:600]}")
    dec = _grep_lines(_safe_read(DECISION_REGISTER, 200_000), mission_id)
    if dec:
        extra_parts.append("LINKED DECISIONS:\n" + "\n".join(dec))
    less = _grep_lines(_safe_read(LESSONS_FILE, 200_000), mission_id)
    if less:
        extra_parts.append("LESSONS:\n" + "\n".join(less))
    if notes:
        extra_parts.append("RECENT ENGINEERING NOTES:\n" + "\n".join(notes[-5:]))

    return MissionContext(
        mission_id=mission_id,
        title=title,
        priority=priority or "P3",
        status=status or "Unknown",
        next_action=next_action,
        assigned_specialist=specialist or "unassigned",
        raw={"engineering_status": eng.value if eng else "unset"},
    ), "\n\n".join(extra_parts)[:8000]


def _field(text: str, key: str, default: str = "") -> str:
    """Pull a `**Key:** value`, `- Key: value`, or first-heading title from mission md."""
    if key.lower() == "title":
        m = re.search(r"^#\s+(.+)$", text, re.M)
        return m.group(1).strip() if m else default
    m = re.search(rf"(?:\*\*{re.escape(key)}:\*\*|-\s*{re.escape(key)}:)\s*(.+)", text, re.I)
    return m.group(1).strip() if m else default


# ---------------------------------------------------------------------------
# GLM call (injectable for tests)
# ---------------------------------------------------------------------------
def _glm_generate(mission_id: str, mode, glm_call: Optional[Callable] = None) -> tuple[bool, str, str]:
    """Run a mode-specific GLM generation for a mission. Returns (ok, text, model).

    The ENGINEER_PERSONA is sent as the system message on every call so the
    model's responses are contained to the Engineering Officer role.
    `glm_call` is injectable for tests; it must accept (prompt, system=...).
    """
    from core.engineering.prompt_builder import build_prompt
    from core.engineering.schemas import RouterRequest, Backend
    from core.engineering.providers import glm

    ctx, extra = build_mission_context(mission_id)
    req = RouterRequest(mission_id=mission_id, mode=mode, backend=Backend.GLM,
                        model=None, mission_context=ctx, extra_context=extra)
    prompt = build_prompt(req)
    caller = glm_call or glm.call
    try:
        text, model = caller(prompt, system=ENGINEER_PERSONA)
        return True, text, model
    except Exception as exc:  # never crash the bot
        log.warning("[eng] GLM %s failed for %s: %s", getattr(mode, "value", mode), mission_id, exc)
        return False, f"GLM generation failed: {type(exc).__name__} — {exc}", "glm-5.2"


# ---------------------------------------------------------------------------
# Output footer (mission requires Evidence / Assumptions / Next on every output)
# ---------------------------------------------------------------------------
def _footer(evidence: str, assumptions: str, next_action: str, high_risk: bool = False) -> str:
    lines = [
        "",
        "—",
        f"*Evidence:* {evidence}",
        f"*Assumptions:* {assumptions}",
        f"*Next recommended action:* {next_action}",
    ]
    if high_risk:
        lines.append("⚠️ *High-risk change — XO / Number One review required before applying.*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pending-action store (the Approve-tap gate for every mutation)
# ---------------------------------------------------------------------------
@dataclass
class PendingAction:
    kind: str            # 'status' | 'log' | 'handoff' | 'patch'
    mission_id: str
    summary: str         # human-readable preview shown before the Approve tap
    payload: dict = field(default_factory=dict)
    by: str = ""


class PendingStore:
    """One pending action per chat. Stored in-process; lost on restart (safe — a
    lost pending action just needs re-issuing, never a partial write)."""

    def __init__(self) -> None:
        self._by_chat: dict[int, PendingAction] = {}

    def stage(self, chat_id: int, action: PendingAction) -> None:
        self._by_chat[chat_id] = action

    def take(self, chat_id: int) -> Optional[PendingAction]:
        return self._by_chat.pop(chat_id, None)

    def peek(self, chat_id: int) -> Optional[PendingAction]:
        return self._by_chat.get(chat_id)


# ===========================================================================
# READ COMMANDS (run immediately — no writes)
# ===========================================================================
def cmd_missions() -> str:
    """List engineering-actionable missions: active registry rows + handoff queue."""
    rows = [r for r in registry_rows() if r["status"].strip().upper() not in
            ("COMPLETED", "CLOSED", "CANCELLED", "CANCELED", "DEFERRED")]
    lines = ["🛠 *Engineering-actionable missions*", ""]
    if rows:
        for r in rows[:25]:
            eng = current_engineering_status(r["id"])
            tag = f" · eng: {eng.value}" if eng else ""
            lines.append(f"• `{r['id']}` — {r['title']} _({r['priority']} / {r['status']}{tag})_")
    else:
        lines.append("_No active missions in the registry._")

    # Surface approved handoffs not already covered above.
    if HANDOFFS_DIR.exists():
        seen = {r["id"].lower() for r in rows}
        ho_lines = []
        for p in sorted(HANDOFFS_DIR.glob("ENG-HANDOFF-*.md")):
            f = _parse_handoff_file(p) or {}
            mid = f.get("mission_id", "").strip()
            st = derive_engineering_status(f.get("batch_status", ""))
            if st and st not in (EngineeringStatus.COMPLETED,) and (not mid or mid.lower() not in seen):
                ho_lines.append(f"• handoff `{p.name}` — {f.get('title', '(untitled)')} _({st.value})_")
        if ho_lines:
            lines += ["", "*Open engineering handoffs:*"] + ho_lines[:15]

    lines.append(_footer(
        evidence="mission-index.txt + Engineering-Handoffs/ + status ledger",
        assumptions="Completed/closed/cancelled missions are hidden.",
        next_action="`/eng_pickup <mission_id>` to load a mission's context.",
    ))
    return "\n".join(lines)


def cmd_pickup(mission_id: str) -> str:
    if not mission_exists(mission_id):
        return _unknown(mission_id)
    row = registry_row(mission_id) or {}
    mfile = mission_file(mission_id)
    ho = handoff_for(mission_id)
    eng = current_engineering_status(mission_id)
    notes = ledger_entries(mission_id)

    lines = [f"📋 *Mission pickup — `{mission_id}`*", ""]
    lines.append(f"*Title:* {row.get('title') or (_field(_safe_read(mfile), 'title') if mfile else mission_id)}")
    lines.append(f"*Priority / Status:* {row.get('priority', '?')} / {row.get('status', '?')}")
    lines.append(f"*Owner / Specialist:* {row.get('owner', '?')} / {row.get('specialist', '?')}")
    lines.append(f"*Engineering status:* {eng.value if eng else 'unset (Pending Triage)'}")
    lines.append(f"*Mission file:* {'`' + str(mfile.relative_to(_REPO_ROOT)) + '`' if mfile else '_none_'}")
    lines.append(f"*Handoff:* {'`' + ho.name + '`' if ho else '_none_'}")

    dec = _grep_lines(_safe_read(DECISION_REGISTER, 200_000), mission_id, 4)
    if dec:
        lines += ["", "*Linked decisions:*"] + [f"  - {d}" for d in dec]
    less = _grep_lines(_safe_read(LESSONS_FILE, 200_000), mission_id, 3)
    if less:
        lines += ["", "*Lessons:*"] + [f"  - {l}" for l in less]
    if notes:
        lines += ["", "*Recent engineering notes:*"] + [f"  {n}" for n in notes[-5:]]

    lines.append(_footer(
        evidence="registry row + mission file + handoff + decision register + lessons + ledger",
        assumptions="No claim/assignment made — pickup is read-only.",
        next_action=f"`/eng_plan {mission_id}` for a work plan, or `/eng_status {mission_id} \"In Progress\"` to advance it.",
    ))
    return "\n".join(lines)


def cmd_plan(mission_id: str, glm_call: Optional[Callable] = None) -> str:
    from core.engineering.schemas import ExecutionMode
    if not mission_exists(mission_id):
        return _unknown(mission_id)
    ok, text, model = _glm_generate(mission_id, ExecutionMode.PLAN, glm_call)
    head = f"🧭 *Engineering plan — `{mission_id}`* (GLM {model})\n\n"
    if not ok:
        return head + text + _footer("GLM call attempted", "GLM/Ollama-Cloud may be unreachable", "Retry, or check GLM_API_KEY / connectivity.")
    return head + text.strip() + _footer(
        evidence=f"GLM {model} over mission context (registry + file + handoff + ledger)",
        assumptions="Plan is advisory; file paths are model-proposed and need confirming.",
        next_action=f"`/eng_patch {mission_id}` for a proposed diff, or `/eng_handoff {mission_id}` for a Claude-Code/Codex handoff.",
    )


def cmd_review(mission_id: str, glm_call: Optional[Callable] = None) -> str:
    from core.engineering.schemas import ExecutionMode
    if not mission_exists(mission_id):
        return _unknown(mission_id)
    ok, text, model = _glm_generate(mission_id, ExecutionMode.REVIEW, glm_call)
    head = f"🔎 *Engineering review — `{mission_id}`* (GLM {model})\n\n"
    if not ok:
        return head + text + _footer("GLM call attempted", "GLM may be unreachable", "Retry or check connectivity.")
    return head + text.strip() + _footer(
        evidence=f"GLM {model} assessment vs mission objectives",
        assumptions="Review is advisory; acceptance criteria taken from the mission file.",
        next_action=f"Record the outcome with `/eng_log {mission_id} <note>` or advance with `/eng_status`.",
    )


# ===========================================================================
# MUTATING COMMANDS (stage a PendingAction → executed only on Approve tap)
# ===========================================================================
def stage_status(mission_id: str, status_text: str, by: str) -> tuple[str, Optional[PendingAction]]:
    if not mission_exists(mission_id):
        return _unknown(mission_id), None
    st = normalise_status(status_text)
    if not st:
        valid = " · ".join(s.value for s in ENGINEERING_LIFECYCLE)
        return (f"⚠️ Invalid status `{status_text}`.\nValid: {valid}", None)
    cur = current_engineering_status(mission_id)
    cur_label = cur.value if cur else "unset"
    summary = (f"Set engineering status of `{mission_id}`:\n"
               f"  {cur_label} → *{st.value}*")
    action = PendingAction("status", mission_id, summary,
                           {"from": cur_label, "to": st.value}, by)
    return summary, action


def stage_log(mission_id: str, note: str, by: str) -> tuple[str, Optional[PendingAction]]:
    if not mission_exists(mission_id):
        return _unknown(mission_id), None
    note = note.strip()
    if not note:
        return "⚠️ Usage: `/eng_log <mission_id> <note>`", None
    summary = f"Append engineering note to `{mission_id}`:\n  “{note[:300]}”"
    return summary, PendingAction("log", mission_id, summary, {"note": note}, by)


def stage_handoff(mission_id: str, by: str) -> tuple[str, Optional[PendingAction]]:
    if not mission_exists(mission_id):
        return _unknown(mission_id), None
    row = registry_row(mission_id) or {}
    mfile = mission_file(mission_id)
    title = row.get("title") or (_field(_safe_read(mfile), "title") if mfile else mission_id)
    summary = (f"Create a Claude-Code/Codex engineering handoff for `{mission_id}`:\n"
               f"  *{title}*\n  → writes ENG-HANDOFF-*.md (Status: APPROVED_FOR_ENGINEERING, Batch Status: PENDING)")
    return summary, PendingAction("handoff", mission_id, summary,
                                  {"title": title, "priority": row.get("priority", "P3")}, by)


def stage_patch(mission_id: str, by: str, glm_call: Optional[Callable] = None) -> tuple[str, Optional[PendingAction]]:
    """Generate a patch proposal now (read/LLM); the Approve tap only WRITES the
    review-only artifact. Nothing is ever applied."""
    from core.engineering.schemas import ExecutionMode
    if not mission_exists(mission_id):
        return _unknown(mission_id), None
    ok, text, model = _glm_generate(mission_id, ExecutionMode.PATCH, glm_call)
    if not ok:
        return f"⚠️ Patch generation failed for `{mission_id}`: {text}", None
    preview = text.strip()
    short = preview if len(preview) < 1500 else preview[:1500] + "\n… (truncated in preview)"
    summary = (f"🩹 *Proposed patch — `{mission_id}`* (GLM {model}) — REVIEW ONLY\n\n"
               f"```\n{short}\n```\n\n"
               f"Approve to **save** this as a review-only artifact (it is *not* applied, "
               f"committed, or pushed).")
    action = PendingAction("patch", mission_id, summary,
                           {"text": preview, "model": model}, by)
    return summary, action


# ---------------------------------------------------------------------------
# Apply a staged action (called only from the Approve callback)
# ---------------------------------------------------------------------------
def apply_action(action: PendingAction) -> str:
    if action.kind == "status":
        entry = (f"- {_now_iso()} | STATUS: {action.payload['from']} → {action.payload['to']} "
                 f"| by {action.by}")
        path = _append_ledger(action.mission_id, entry)
        # Keep the handoff's Batch Status in sync if one exists (Number One queue).
        synced = _sync_handoff_status(action.mission_id, action.payload["to"])
        return (f"✅ Engineering status of `{action.mission_id}` → *{action.payload['to']}* recorded.\n"
                f"Ledger: `{_rel(path)}`"
                + (f"\nHandoff Batch Status synced." if synced else "")
                + _footer("status ledger append", "status applies to engineering lifecycle, not mission status",
                          f"`/eng_log {action.mission_id} <note>` to add detail."))
    if action.kind == "log":
        entry = f"- {_now_iso()} | LOG | by {action.by} | {action.payload['note']}"
        path = _append_ledger(action.mission_id, entry)
        return (f"✅ Note appended to `{action.mission_id}`.\nLedger: `{_rel(path)}`"
                + _footer("status ledger append", "note recorded verbatim", "Continue, or `/eng_status` to advance."))
    if action.kind == "handoff":
        path = _write_handoff(action.mission_id, action.payload, action.by)
        return (f"✅ Handoff written: `{_rel(path)}`\n"
                f"It is implementation-ready for Claude Code / Codex (review-only; nothing auto-runs)."
                + _footer("ENG-HANDOFF file written", "Batch Status PENDING — not yet engineered",
                          "Hand the file to Claude Code/Codex, or approve via the build pipeline.", high_risk=True))
    if action.kind == "patch":
        path = _write_artifact(action.mission_id, action.payload["text"], action.payload.get("model", "glm-5.2"), action.by)
        return (f"✅ Review-only patch artifact saved: `{path}`\n"
                f"It was *not* applied, committed, or pushed."
                + _footer("patch artifact written under Engineering-Handoffs/artifacts",
                          "diff is model-proposed; apply-cleanliness not guaranteed",
                          "Review the artifact; apply manually only after Captain/XO review.", high_risk=True))
    return "⚠️ Unknown pending action."


# ---------------------------------------------------------------------------
# Write primitives (small, self-contained — no batch_coding/mistral dependency)
# ---------------------------------------------------------------------------
def _write_artifact(mission_id: str, text: str, model: str, by: str) -> str:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    custom_id = re.sub(r"[^A-Za-z0-9._-]", "_", f"{mission_id}-{ts}")
    artifact = ARTIFACTS_DIR / f"{custom_id}.patch.md"
    header = "\n".join([
        f"# Proposed code changes (GLM {model})",
        f"- Mission: {mission_id}",
        f"- Generated: {_now_iso()}",
        f"- Requested by: {by}",
        "- Status: FOR REVIEW — do not apply blindly; not applied/committed/pushed",
    ])
    artifact.write_text(f"{header}\n\n---\n\n{text}\n", encoding="utf-8")
    try:
        return str(artifact.relative_to(_REPO_ROOT))
    except ValueError:
        return str(artifact)


def _write_handoff(mission_id: str, payload: dict, by: str) -> Path:
    HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    decision_id = f"DEC-TG-{ts}"
    slug = re.sub(r"[^a-z0-9]+", "-", (payload.get("title") or mission_id).lower()).strip("-")[:40]
    path = HANDOFFS_DIR / f"ENG-HANDOFF-{ts}-{slug or 'mission'}.md"
    mfile = mission_file(mission_id)
    body = _safe_read(mfile) if mfile else ""
    summary = _field(body, "Mission Statement") or _field(body, "Objective") or payload.get("title", mission_id)
    handoff = f"""# Engineering Handoff

- Status: APPROVED_FOR_ENGINEERING
- Batch Status: PENDING
- Batch Group: unassigned
- Priority: {payload.get('priority', 'P3')}
- Decision ID: {decision_id}
- Approved At: {_now_iso()}
- Approved By: Telegram (Directed Engineering Operator)
- Requesting User: {by}
- Mission ID: {mission_id}

## Mission Title
{payload.get('title', mission_id)}

## Original Request
Engineering handoff generated under Captain direction via /eng_handoff for {mission_id}.

## Summary
{summary[:1500] if summary else payload.get('title', mission_id)}

## Rationale
Directed by Captain TJR for implementation by Claude Code / Codex.

## Suggested Next Step
implementation

## Risks
Review-only handoff. The implementing agent must follow the approved engineering
lifecycle (Pending Triage → Assigned → In Progress → Awaiting Review → Completed)
and make no git commit/push/deploy without explicit Captain approval.
"""
    path.write_text(handoff, encoding="utf-8")
    return path


def _sync_handoff_status(mission_id: str, status_value: str) -> bool:
    """Idempotently stamp the matching handoff's Batch Status (keeps Number One in sync)."""
    ho = handoff_for(mission_id)
    if not ho:
        return False
    try:
        lines = ho.read_text(encoding="utf-8").splitlines()
        done = False
        for i, l in enumerate(lines):
            if l.strip().lower().startswith("- batch status:"):
                lines[i] = f"- Batch Status: {status_value}"
                done = True
                break
        if not done:
            return False
        ho.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def _unknown(mission_id: str) -> str:
    return (f"⚠️ I can't find mission `{mission_id}` in the registry, Missions/, or the "
            f"handoff queue.\nTie the action to a known mission id — try `/eng_missions`.")
