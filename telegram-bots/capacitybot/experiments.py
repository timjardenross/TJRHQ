"""Capacity Bot — /experiment (V3 Mission 4: Personal Experiment Engine).

See TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md §15
"Personal Experiment Engine" and §19 "System Learning Upgrade". Turns
"Worth Testing" from a narrative sentence (RecoveryView.tsx's worthTesting()
heuristic — still the fallback when no structured experiment exists) into a
real, persisted capacity_experiments row (migration 0159).

Design (documented here since this is the most open-ended part of the
mission — see the Mission 4 report for the full rationale):

  - ONE command, /experiment, with a small menu (propose / view existing) —
    per the mission brief's "keep the command surface small" instruction,
    rather than /experiment_propose, /experiment_stop, etc.

  - The lifecycle is propose -> active -> completed|stopped. 'stopped' is
    kept distinct from 'completed' (see migration 0159's comment) so an
    experiment abandoned because it made things worse reads differently
    from one that ran its full course.

  - hypothesis and proposed_change are free text (there's no sensible
    enumerated set for "what do you think might help"), so this flow is
    the one place in this bot that holds cross-message conversational
    state via context.user_data + app.py's cmd_message, the same pattern
    already established for the deep check-in's closing note
    (capacity_deep_note_id). Everything else in this module is buttons.

  - trial_window (the DB column) stays pure free text per the V3 doc's own
    schema sketch — never parsed. Reminder scheduling is a SEPARATE,
    lightweight question asked only at the moment an experiment is marked
    active ("remind me to check in after: 1 week / 2 weeks / 3 weeks /
    1 month / no reminder") using the same job_queue.run_once mechanism
    /helpme's reassessment reminder already uses (see
    _helpme_offer_next/handle_helpme_offer_callback in app.py) — not a
    second scheduling mechanism, and not a heuristic parse of whatever
    free text the user typed into trial_window.

  - target_condition is only asked as part of the optional "add details"
    branch, alongside baseline_window/trial_window/outcome_measures — the
    minimal propose path is just hypothesis + proposed_change, matching
    the mission brief's "minimal fields, rest optional/skippable".
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

log = logging.getLogger(__name__)

TABLE = "capacity_experiments"

# ── Reminder presets (bot-side only — NOT the trial_window DB column,
# see module docstring) ──────────────────────────────────────────────────
TRIAL_WINDOW_PRESETS = [
    ("1w", "1 week", 7),
    ("2w", "2 weeks", 14),
    ("3w", "3 weeks", 21),
    ("1m", "1 month", 30),
]
_PRESET_LABEL_BY_DAYS = {days: label for _code, label, days in TRIAL_WINDOW_PRESETS}

OPEN_STATUSES = ("proposed", "active")

CONFIDENCE_OPTIONS = [("low", "Low"), ("moderate", "Moderate"), ("high", "High")]


# ── Menu (spec §15 — command surface stays small: one /experiment entry) ───

def render_menu(experiments: list[dict]) -> str:
    if not experiments:
        return (
            "EXPERIMENTS\n\n"
            "No experiments proposed or in progress right now.\n\n"
            "An experiment is one meaningful, reversible change worth testing "
            "— never a treatment, always stoppable."
        )
    lines = ["EXPERIMENTS", ""]
    for e in experiments:
        status_label = "In progress" if e["status"] == "active" else "Worth testing"
        lines.append(f"[{status_label}] {e['hypothesis']}")
    return "\n".join(lines)


def kb_menu(experiments: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for e in experiments:
        short = e["hypothesis"][:40] + ("…" if len(e["hypothesis"]) > 40 else "")
        rows.append([InlineKeyboardButton(f"View — {short}", callback_data=f"cx|a=view|id={e['id']}")])
    rows.append([InlineKeyboardButton("📝 Propose new experiment", callback_data="cx|a=propose")])
    return InlineKeyboardMarkup(rows)


# ── Detail view ──────────────────────────────────────────────────────────

def render_experiment_detail(e: dict) -> str:
    lines = [f"Hypothesis: {e['hypothesis']}", "", f"Trying: {e['proposed_change']}"]
    if e.get("target_condition"):
        lines += ["", f"Target condition: {e['target_condition']}"]
    if e.get("baseline_window"):
        lines += ["", f"Baseline: {e['baseline_window']}"]
    if e.get("trial_window"):
        lines += ["", f"Trial: {e['trial_window']}"]
    if e.get("outcome_measures"):
        lines += ["", "Watching: " + ", ".join(e["outcome_measures"])]
    lines += ["", f"Status: {e['status']}"]
    if e["status"] in ("completed", "stopped") and e.get("result"):
        lines += ["", f"Result: {e['result']}"]
        if e.get("confidence"):
            lines.append(f"Confidence: {e['confidence']}")
    lines += ["", "Reversible and stoppable at any time — this is not a treatment."]
    return "\n".join(lines)


def kb_experiment_detail(e: dict) -> InlineKeyboardMarkup:
    eid = e["id"]
    rows = []
    if e["status"] == "proposed":
        rows.append([InlineKeyboardButton("▶️ Mark active", callback_data=f"cx|a=activate|id={eid}")])
        rows.append([InlineKeyboardButton("🛑 Stop", callback_data=f"cx|a=stop|id={eid}")])
    elif e["status"] == "active":
        rows.append([InlineKeyboardButton("✅ Log outcome", callback_data=f"cx|a=complete|id={eid}")])
        rows.append([InlineKeyboardButton("🛑 Stop", callback_data=f"cx|a=stop|id={eid}")])
    rows.append([InlineKeyboardButton("« Back to experiments", callback_data="cx|a=menu")])
    return InlineKeyboardMarkup(rows)


# ── Propose flow — free-text hypothesis/proposed_change, everything else
# buttons ─────────────────────────────────────────────────────────────────

def q_propose_hypothesis() -> str:
    return "What do you want to test? Reply with your hypothesis — what you think might help."


def q_propose_change() -> str:
    return "What's the proposed change — what will you actually do differently during the trial?"


def kb_after_minimal() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Save now", callback_data="cx|a=save_now")],
        [InlineKeyboardButton("➕ Add baseline, trial window & what to watch", callback_data="cx|a=add_details")],
    ])


def q_target_condition() -> str:
    return "What condition or driver is this about? (optional) Reply with text, or tap Skip."


def kb_skip(next_action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Skip", callback_data=f"cx|a={next_action}")]])


def q_baseline() -> str:
    return (
        "What's the baseline — what are you seeing now? (optional)\n\n"
        "e.g. \"4 of 5 office afternoons reached Stretched or Depleted\"\n\n"
        "Reply with text, or tap Skip."
    )


def q_trial_window() -> str:
    return "How long is the trial? (optional)"


def kb_trial_window() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(label, callback_data=f"cx|a=trial|d={days}")
        for _code, label, days in TRIAL_WINDOW_PRESETS
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("✏️ Custom", callback_data="cx|a=trial_custom")])
    rows.append([InlineKeyboardButton("⏭ Skip", callback_data="cx|a=skip_trial")])
    return InlineKeyboardMarkup(rows)


def q_trial_custom() -> str:
    return "Type the trial window (e.g. \"two weeks\")."


def q_outcome_measures() -> str:
    return (
        "What do you want to watch during the trial? (optional)\n\n"
        "List a few things, separated by commas — e.g. \"3pm capacity, sensory load, "
        "next-morning capacity\".\n\n"
        "Reply with text, or tap Skip."
    )


def render_proposed_confirmation(e: dict) -> str:
    return f"✅ Experiment proposed:\n\n{e['hypothesis']}\n\nUpdate it anytime with /experiment."


# ── Mark active — reminder scheduling question (bot-side only) ─────────────

def q_activate_reminder() -> str:
    return "Remind you to check in after:"


def kb_activate_reminder(experiment_id) -> InlineKeyboardMarkup:
    base = f"cx|a=activate_confirm|id={experiment_id}"
    buttons = [
        InlineKeyboardButton(label, callback_data=f"{base}|d={days}")
        for _code, label, days in TRIAL_WINDOW_PRESETS
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("No reminder", callback_data=f"{base}|d=0")])
    return InlineKeyboardMarkup(rows)


def render_activated(e: dict, reminder_days: int) -> str:
    lines = [f"▶️ Marked active: {e['hypothesis']}"]
    if reminder_days:
        label = _PRESET_LABEL_BY_DAYS.get(reminder_days, f"{reminder_days} days")
        lines.append(f"\nI'll check back in {label}.")
    return "\n".join(lines)


# ── Reassessment reminder + completion ──────────────────────────────────────

def q_reassess_prompt(e: dict) -> str:
    return f"How's this experiment going?\n\n{e['hypothesis']}"


def kb_reassess_prompt(experiment_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Log outcome now", callback_data=f"cx|a=complete|id={experiment_id}")],
        [InlineKeyboardButton("⏳ Not yet — remind me in a week", callback_data=f"cx|a=snooze|id={experiment_id}")],
    ])


def q_complete_result() -> str:
    return "How did it go? Describe what changed — or didn't."


def kb_confidence(experiment_id) -> InlineKeyboardMarkup:
    base = f"cx|a=conf|id={experiment_id}"
    buttons = [InlineKeyboardButton(label, callback_data=f"{base}|c={code}") for code, label in CONFIDENCE_OPTIONS]
    rows = [buttons]
    rows.append([InlineKeyboardButton("⏭ Skip", callback_data=f"{base}|c=skip")])
    return InlineKeyboardMarkup(rows)


def render_completed(e: dict) -> str:
    return f"✅ Logged. Marked completed:\n\n{e['hypothesis']}\n\nResult: {e.get('result') or '(none)'}"


# ── Stop (spec §15 — "must be stoppable if worse") ──────────────────────────

def q_stop_reason() -> str:
    return "Optional: why are you stopping? Reply with a reason, or tap 'Stop now' to skip."


def kb_stop_now(experiment_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Stop now (no reason)", callback_data=f"cx|a=stop_now|id={experiment_id}")]])


def render_stopped(e: dict) -> str:
    return f"🛑 Stopped:\n\n{e['hypothesis']}"


# ── Parsing (matches capacity_today.parse_cb's convention exactly) ─────────

def parse_cb(data: str) -> dict:
    result: dict[str, str] = {}
    for part in data.split("|")[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result


# ── DB access ────────────────────────────────────────────────────────────

async def list_experiments(db, statuses: tuple[str, ...] = OPEN_STATUSES) -> list[dict]:
    if not db:
        return []
    try:
        res = (
            db.table(TABLE)
            .select("*")
            .in_("status", list(statuses))
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        log.error("capacity_experiments list failed: %s", exc)
        return []


async def get_experiment(db, experiment_id) -> dict | None:
    if not db:
        return None
    try:
        res = db.table(TABLE).select("*").eq("id", experiment_id).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:
        log.error("capacity_experiments lookup failed: %s", exc)
        return None


async def create_experiment(
    db,
    *,
    hypothesis: str,
    proposed_change: str,
    target_condition: str | None = None,
    baseline_window: str | None = None,
    trial_window: str | None = None,
    outcome_measures: list[str] | None = None,
) -> tuple[bool, dict | None, str | None]:
    if not db:
        return False, None, "Supabase unavailable (check SUPABASE_KEY)"
    payload = {
        "hypothesis": hypothesis,
        "proposed_change": proposed_change,
        "target_condition": target_condition,
        "baseline_window": baseline_window,
        "trial_window": trial_window,
        "outcome_measures": outcome_measures or [],
        "status": "proposed",
    }
    try:
        res = db.table(TABLE).insert(payload).execute()
        row = (res.data or [None])[0]
        return True, row, None
    except Exception as exc:
        log.error("capacity_experiments insert failed: %s | payload=%s", exc, payload)
        return False, None, str(exc)


async def _update(db, experiment_id, fields: dict) -> tuple[bool, str | None]:
    if not db:
        return False, "Supabase unavailable (check SUPABASE_KEY)"
    try:
        db.table(TABLE).update(fields).eq("id", experiment_id).execute()
        return True, None
    except Exception as exc:
        log.error("capacity_experiments update failed: %s | fields=%s", exc, fields)
        return False, str(exc)


async def mark_active(db, experiment_id) -> tuple[bool, str | None]:
    return await _update(db, experiment_id, {"status": "active", "started_at": "now()"})


async def complete_experiment(db, experiment_id, *, result: str, confidence: str | None) -> tuple[bool, str | None]:
    return await _update(db, experiment_id, {
        "status": "completed", "result": result, "confidence": confidence, "completed_at": "now()",
    })


async def stop_experiment(db, experiment_id, *, result: str | None) -> tuple[bool, str | None]:
    return await _update(db, experiment_id, {
        "status": "stopped", "result": result, "completed_at": "now()",
    })
