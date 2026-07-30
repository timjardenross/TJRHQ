"""Chief Engineer agent: conversational reasoning + build-request extraction.

Stateless-ish: keeps a small, bounded per-chat history in memory. Two LLM uses:
  * answer(): grounded conversational reply over read-only context.
  * draft_build_request(): a strict JSON-extraction pass turning the conversation
    into the required structured fields.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque

import context_reader
import llm
from build_request import BuildRequest

SERVICE_DIR = Path(__file__).resolve().parent
_SYSTEM_PROMPT = (SERVICE_DIR / "prompts" / "chief_engineer.md").read_text(encoding="utf-8")

# Per-chat rolling history of (role, text). Bounded so memory/prompt stay small.
_HISTORY: dict[int, Deque[tuple[str, str]]] = defaultdict(lambda: deque(maxlen=12))


def remember(chat_id: int, role: str, text: str) -> None:
    _HISTORY[chat_id].append((role, text))


def _history_text(chat_id: int) -> str:
    return "\n".join(f"{role}: {text}" for role, text in _HISTORY[chat_id])


def reset(chat_id: int) -> None:
    _HISTORY.pop(chat_id, None)


_MISSION_ID_RE = re.compile(
    r"\b((?:USS-TJR-)?MSN-[A-Za-z0-9-]+|M-\d{6,8}-[A-Za-z0-9-]+|M-\d{8})\b"
)


def _resolve_referenced_missions(user_text: str, max_n: int = 3) -> str:
    """If the Captain names mission id(s), fetch their full records on demand
    (reuses the XO read_mission action) so the agent isn't limited to whatever
    happened to be in the recent-files context. Best-effort; '' on nothing."""
    ids: list[str] = []
    for m in _MISSION_ID_RE.findall(user_text or ""):
        if m not in ids:
            ids.append(m)
    if not ids:
        return ""
    try:
        import sys
        from pathlib import Path
        xo_dir = str(Path(__file__).resolve().parent.parent / "xo-bot")
        if xo_dir not in sys.path:
            sys.path.append(xo_dir)
        import actions as xo_actions
    except Exception:  # noqa: BLE001
        return ""
    blocks: list[str] = []
    for mid in ids[:max_n]:
        try:
            ok, out = xo_actions.ACTIONS["read_mission"]({"mission_id": mid})
            if ok and out:
                blocks.append(out)
        except Exception:  # noqa: BLE001
            continue
    return "# Referenced mission record(s)\n" + "\n\n".join(blocks) + "\n\n" if blocks else ""


def answer(chat_id: int, user_text: str, supabase_client=None) -> str:
    """Produce a grounded conversational reply and record it in history."""
    remember(chat_id, "Captain", user_text)
    context = context_reader.assemble_context()
    memory = context_reader.command_memory(supabase_client)
    referenced = _resolve_referenced_missions(user_text)

    user_prompt = (
        "# Read-only system context\n"
        f"{context}\n\n"
        f"{referenced}"
        f"{memory}\n\n"
        "# Conversation so far\n"
        f"{_history_text(chat_id)}\n\n"
        "# Captain's latest message\n"
        f"{user_text}\n\n"
        "Respond as Chief Engineer. Ground your answer in the context above; cite "
        "mission ids / ADR numbers / paths where relevant. Keep it concise."
    )
    ok, text = llm.ask(_SYSTEM_PROMPT, user_prompt)
    if not ok:
        return (
            "⚠️ Chief Engineer LLM is unavailable right now, so I can't reason over "
            f"context. ({text}). You can still send /build to log a request from our chat."
        )
    remember(chat_id, "Chief Engineer", text)
    return text


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> dict:
    match = _JSON_BLOCK.search(raw or "")
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def draft_build_request(chat_id: int, note: str, requested_by: str) -> BuildRequest:
    """Summarise the conversation into a structured BuildRequest.

    Falls back to a deterministic skeleton if the LLM is unavailable or returns
    unparseable output — the Captain always gets a loggable request.
    """
    convo = _history_text(chat_id)
    extra = f"\nCaptain's framing note for this build request: {note}" if note.strip() else ""
    instruction = (
        "From the conversation below, produce a build request for the engineering "
        "governance queue. Return ONLY a JSON object with these keys:\n"
        '  "title": short imperative title,\n'
        '  "summary": what should be built/changed,\n'
        '  "rationale": why it matters,\n'
        '  "risks": array of short risk strings,\n'
        '  "suggested_next_step": one concrete next action.\n'
        "Do not invent mission ids or approvals. JSON only, no prose.\n\n"
        f"# Conversation\n{convo}{extra}\n"
    )
    ok, raw = llm.ask(_SYSTEM_PROMPT, instruction)
    data = _extract_json(raw) if ok else {}

    title = (data.get("title") or note or "Build request from Telegram chat").strip()
    summary = (data.get("summary") or note or convo[-800:] or "(no summary)").strip()
    rationale = (data.get("rationale") or "Captured from Captain's Telegram conversation.").strip()
    risks = data.get("risks") or []
    if isinstance(risks, str):
        risks = [risks]
    risks = [str(r).strip() for r in risks if str(r).strip()]
    next_step = (
        data.get("suggested_next_step")
        or "Triage in the engineering governance queue and scope implementation."
    ).strip()

    # Keep a trimmed transcript for traceability.
    ctx = convo[-2000:]

    return BuildRequest(
        title=title,
        summary=summary,
        rationale=rationale,
        risks=risks,
        suggested_next_step=next_step,
        requested_by=requested_by,
        conversation_context=ctx,
    )
