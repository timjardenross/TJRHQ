"""XO Bot — MY CAPACITY TODAY (2026-08-21).

Replaces Recovery Pulse. Purpose: "track what my system needs today, not
what diagnosis explains it." Not a diagnostic tool — tracks capacity,
stimulation, pain, overload, masking/compensation, and what actually
helps. See docs/capacity-today-spec.md (Captain's original brief) for the
full product spec this module implements section-by-section.

Convention, matching app.py's retired pulse flow and mood_chart.py:
  - Callback data is pipe-delimited key=value pairs, flow tag `ct|`.
  - All state lives in the callback data itself — no ConversationHandler.
  - query.edit_message_text() updates the same message in place.
  - Terminal state is detected by field presence, not a step counter.

New pattern this module adds — multi-select steps (Q6 active_loads, Q8
identified_needs): each option is a single-digit/letter index into a fixed
array; selections are a comma-joined index list in the callback data.
Telegram's callback_data hard limit is 64 bytes, so every field uses a
single-character code and multi-select lists use bare digit indices — a
fully-populated quick check-in's callback data stays well under that limit.

Messages are plain text (no MarkdownV2) throughout — deliberately, to avoid
escaping bugs across rich, punctuation-heavy summary text. Matches
mood_chart.py's callback-edit messages, which do the same.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_TZ = ZoneInfo("Australia/Brisbane")
log = logging.getLogger(__name__)

TABLE = "capacity_checkins"


# ── Option tables (index-coded for multi-select callback data) ────────────────

CAPACITY_OPTIONS = [
    ("g", "🟢 Sustainable"),
    ("o", "🟠 Stretched"),
    ("r", "🔴 Depleted"),
]
CAPACITY_LABEL = {"green": "🟢 Sustainable", "orange": "🟠 Stretched", "red": "🔴 Depleted"}
CAPACITY_CODE_TO_STATE = {"g": "green", "o": "orange", "r": "red"}

STIMULATION_OPTIONS = [
    ("l", "⬇️ Not enough"),
    ("b", "⚖️ About right"),
    ("h", "⬆️ Too much"),
]
STIMULATION_LABEL = {"low": "⬇️ Not enough", "balanced": "⚖️ About right", "high": "⬆️ Too much"}
STIM_CODE_TO_STATE = {"l": "low", "b": "balanced", "h": "high"}

PAIN_OPTIONS = [
    ("l", "🟢 Lower than usual"),
    ("b", "🟡 Around usual"),
    ("e", "🟠 Higher than usual"),
    ("h", "🔴 Much higher than usual"),
]
PAIN_LABEL = {
    "low": "🟢 Lower than usual", "baseline": "🟡 Around usual",
    "elevated": "🟠 Higher than usual", "high": "🔴 Much higher than usual",
}
PAIN_CODE_TO_STATE = {"l": "low", "b": "baseline", "e": "elevated", "h": "high"}

REGULATION_OPTIONS = [
    ("s", "😌 Settled"),
    ("m", "🙂 Manageable"),
    ("a", "😣 Activated"),
    ("o", "🚨 Overloaded"),
]
REGULATION_LABEL = {
    "settled": "😌 Settled", "manageable": "🙂 Manageable",
    "activated": "😣 Activated", "overloaded": "🚨 Overloaded",
}
REG_CODE_TO_STATE = {"s": "settled", "m": "manageable", "a": "activated", "o": "overloaded"}

EF_OPTIONS = [
    ("g", "✅ Working well"),
    ("s", "🟡 More effort than usual"),
    ("d", "🟠 Difficult"),
    ("v", "🔴 Very difficult"),
]
EF_LABEL = {
    "good": "✅ Working well", "strained": "🟡 More effort than usual",
    "difficult": "🟠 Difficult", "very_difficult": "🔴 Very difficult",
}
EF_CODE_TO_STATE = {"g": "good", "s": "strained", "d": "difficult", "v": "very_difficult"}

COMPENSATION_OPTIONS = [
    ("l", "🟢 Very little"),
    ("m", "🟡 Some"),
    ("h", "🟠 A lot"),
    ("e", "🔴 I'm forcing myself through"),
]
COMPENSATION_LABEL = {
    "low": "🟢 Very little", "moderate": "🟡 Some",
    "high": "🟠 A lot", "extreme": "🔴 I'm forcing myself through",
}
COMP_CODE_TO_STATE = {"l": "low", "m": "moderate", "h": "high", "e": "extreme"}

# index-coded multi-select — position in this list IS the callback digit
ACTIVE_LOADS = [
    "🔊 Noise / sensory input", "👥 People / social interaction", "💼 Work",
    "🧠 Thinking / decisions", "🔄 Change / uncertainty", "🩹 Pain / physical symptoms",
    "😟 Anxiety / emotional load", "😴 Poor sleep / fatigue", "📱 Too much stimulation",
    "🥱 Not enough stimulation", "🏠 Life admin / chores", "❓ Something else",
]
ACTIVE_LOADS_OTHER_IDX = 11

IDENTIFIED_NEEDS = [
    "🔇 Less sensory input", "🛑 Reduce demands", "🧘 Quiet / solitude", "🚶 Movement",
    "🎵 Music / stimulation", "🎯 Something interesting to focus on", "🛌 Rest", "💤 Sleep",
    "🩹 Pain management", "📋 Clear plan / structure", "🔄 More predictability",
    "💬 Connection / talk to someone", "🍽️ Food / hydration", "🌿 Outside / change of environment",
    "⏸️ Stop pushing", "❓ Something else",
]
IDENTIFIED_NEEDS_OTHER_IDX = 15

LOAD_CATEGORY_OPTIONS = [
    ("p", "physical"), ("c", "cognitive"), ("s", "sensory"),
    ("e", "emotional"), ("so", "social"), ("en", "environmental"),
]
DAY_WIN_HELPED_OPTIONS = [
    "Rest", "Movement", "Reduced demands", "Sensory control", "Structure",
    "Connection", "Interesting activity", "Pain management", "Nothing clearly helped",
]


# ── Action suggestion engine (spec §2 + §10 REVS levers) ──────────────────────
# Small master table of short codes -> action text, so a chosen action can
# live in callback data as a code instead of free text (kept fully in the
# existing "state lives in the callback string" pattern rather than relying
# on ephemeral per-chat memory).

MASTER_ACTIONS: dict[str, str] = {
    "reduce_input":   "Reduce sensory input",
    "postpone":       "Stop or postpone one non-essential demand",
    "quieter_place":  "Move somewhere quieter",
    "rest_20":        "Rest for 20-30 minutes",
    "pain_strategy":  "Use your normal pain/regulation strategy",
    "move_5":         "Move for 5-10 minutes",
    "music_on":       "Put music on",
    "bounded_task":   "Choose one interesting bounded task",
    "change_env":     "Change environment",
    "talk_briefly":   "Talk to someone briefly",
    "reduce_physical":"Reduce physical demand",
    "pain_mgmt":      "Use agreed pain-management strategies",
    "change_posture": "Change posture / position",
    "pace_not_push":  "Pace rather than push",
    "protect_recovery":"Protect recovery time",
    "one_task":       "Pick one task only",
    "first_action":   "Break it into the first physical action",
    "remove_optional":"Remove optional decisions",
    "use_timer":      "Use a timer",
    "defer_admin":    "Defer low-value admin",
    "stop_performing":"Where can you stop performing today?",
    "cancel_unnecessary":"Cancel something unnecessary",
    "reduce_social":  "Reduce social interaction",
    "work_directly":  "Work more directly",
    "drop_eye_contact":"Stop forcing eye contact or conversation where safe",
    "ask_dont_guess": "Ask for clarity instead of guessing",
    "simplify_expect":"Simplify expectations",
    "take_recovery":  "Take recovery time",
    "maintain":       "Maintain — no need to add load just because capacity is available",
    "early_reduce":   "What can you reduce, regulate, or change before this becomes red?",
}


def suggest_actions(row: dict) -> list[str]:
    """Rule-based, spec §2 — returns 3-5 MASTER_ACTIONS codes.
    Order of rules matches the spec's own worked examples; later rules can
    add to an already-partly-filled list without duplicating a code."""
    codes: list[str] = []

    def add(*cs: str) -> None:
        for c in cs:
            if c not in codes:
                codes.append(c)

    cap, stim, pain, ef, comp = (
        row.get("capacity_state"), row.get("stimulation_state"),
        row.get("pain_state"), row.get("executive_function"), row.get("compensation_load"),
    )

    if cap == "red" and stim == "high":
        add("reduce_input", "postpone", "quieter_place", "rest_20", "pain_strategy")
    elif cap == "orange" and stim == "low":
        add("move_5", "music_on", "bounded_task", "change_env", "talk_briefly")

    if pain in ("elevated", "high"):
        add("reduce_physical", "pain_mgmt", "change_posture", "pace_not_push", "protect_recovery")

    if ef == "very_difficult":
        add("one_task", "first_action", "remove_optional", "use_timer", "defer_admin")

    if comp == "extreme":
        add("stop_performing", "cancel_unnecessary", "reduce_social", "work_directly",
            "ask_dont_guess", "simplify_expect", "take_recovery")

    if not codes:
        if cap == "green":
            add("maintain")
        elif cap == "orange":
            add("early_reduce", "move_5", "quieter_place")
        elif cap == "red":
            add("rest_20", "quieter_place", "protect_recovery")

    return codes[:5] if len(codes) > 5 else codes


# ── Keyboard builders ──────────────────────────────────────────────────────────

def kb_capacity() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"ct|c={code}") for code, label in CAPACITY_OPTIONS],
    ])


def _done_row(prefix_state: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton("✅ Done for now", callback_data=f"{prefix_state}|done=1")]


def kb_stimulation(c: str) -> InlineKeyboardMarkup:
    base = f"ct|c={c}"
    rows = [[InlineKeyboardButton(label, callback_data=f"{base}|t={code}") for code, label in STIMULATION_OPTIONS]]
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def kb_pain(c: str, t: str) -> InlineKeyboardMarkup:
    base = f"ct|c={c}|t={t}"
    rows = [[InlineKeyboardButton(l, callback_data=f"{base}|p={cd}") for cd, l in PAIN_OPTIONS]]
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def kb_pain_score(c: str, t: str, p: str) -> InlineKeyboardMarkup:
    base = f"ct|c={c}|t={t}|p={p}"
    rows = [
        [InlineKeyboardButton(str(i), callback_data=f"{base}|ps={i}") for i in range(0, 6)],
        [InlineKeyboardButton(str(i), callback_data=f"{base}|ps={i}") for i in range(6, 11)],
        [InlineKeyboardButton("⏭ Skip", callback_data=f"{base}|ps=skip")],
    ]
    return InlineKeyboardMarkup(rows)


def kb_regulation(c: str, t: str, p: str, ps: str) -> InlineKeyboardMarkup:
    base = f"ct|c={c}|t={t}|p={p}|ps={ps}"
    rows = [[InlineKeyboardButton(l, callback_data=f"{base}|r={cd}") for cd, l in REGULATION_OPTIONS]]
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def kb_executive_function(c: str, t: str, p: str, ps: str, r: str) -> InlineKeyboardMarkup:
    base = f"ct|c={c}|t={t}|p={p}|ps={ps}|r={r}"
    rows = [[InlineKeyboardButton(l, callback_data=f"{base}|e={cd}") for cd, l in EF_OPTIONS]]
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def _toggle_list(current: str, idx: int) -> str:
    sel = [x for x in current.split(",") if x] if current else []
    s = str(idx)
    if s in sel:
        sel.remove(s)
    else:
        sel.append(s)
    return ",".join(sel)


def kb_multiselect(base: str, key: str, options: list[str], selected: str) -> InlineKeyboardMarkup:
    """Generic toggle-list keyboard. `base` already contains every prior
    field; `key` is this step's callback-data key (e.g. 'ld' or 'nd').
    Two options per row (not one) — one-per-row read as a long vertical
    list that was hard to scan; matches the single-select steps, which
    already pack their options horizontally."""
    sel_set = set((selected or "").split(",")) if selected else set()
    buttons = []
    for i, label in enumerate(options):
        mark = "✅ " if str(i) in sel_set else ""
        new_val = _toggle_list(selected, i)
        buttons.append(InlineKeyboardButton(f"{mark}{label}", callback_data=f"{base}|{key}={new_val}"))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("➡️ Continue", callback_data=f"{base}|{key}={selected}|next=1")])
    rows.append([InlineKeyboardButton("✅ Done for now", callback_data=f"{base}|{key}={selected}|done=1")])
    return InlineKeyboardMarkup(rows)


def kb_compensation(base: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(l, callback_data=f"{base}|cp={cd}") for cd, l in COMPENSATION_OPTIONS]]
    rows.append(_done_row(base))
    return InlineKeyboardMarkup(rows)


def kb_actions(base: str, codes: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(MASTER_ACTIONS[c], callback_data=f"{base}|act={c}")] for c in codes]
    rows.append([InlineKeyboardButton("⏭ Skip", callback_data=f"{base}|act=skip")])
    return InlineKeyboardMarkup(rows)


def kb_go_deeper(row_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Go deeper", callback_data=f"ctd|id={row_id}")],
        [InlineKeyboardButton("⏰ Remind me", callback_data=f"ctr|id={row_id}")],
        [InlineKeyboardButton("Done", callback_data="ct|noop=1")],
    ])


# ── Remind me later (spec §2, "optionally allow") ────────────────────────────
# No existing generic reminder mechanism in this bot to integrate with (the
# only reminder-shaped code in the repo is platform-runtime/recovery_scheduler
# .py, a Slack-side L2/L3 escalation DM unrelated to a per-check-in nudge) —
# built as a one-off python-telegram-bot JobQueue.run_once, in-memory only:
# if the bot restarts before it fires, the reminder is lost. Acceptable for a
# same-day nudge; not durable enough for anything longer.

REMIND_OPTIONS = [("15", "15 min"), ("45", "45 min"), ("120", "2 hours")]


def kb_remind_duration(row_id: str) -> InlineKeyboardMarkup:
    base = f"ctr|id={row_id}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, callback_data=f"{base}|m={mins}") for mins, label in REMIND_OPTIONS
    ]])


# ── Deep check-in (spec §4) ───────────────────────────────────────────────────
# All 8 questions: load_category, unexpected change, masking present, what
# was skipped (recovery_factors), recovery duration, what helped, what made
# things worse (buttons — index-coded multi-select, same convention as the
# quick check-in's active_loads/identified_needs), and a final free-text
# note covering both "what happened before" (trigger) and anything else
# (notes) — one text reply rather than two, to keep this bounded (spec §11.8:
# "no long forms"). Written via cmd_message's pending-state hook in app.py.

RECOVERY_DURATION_OPTIONS = [
    ("n",  "No recovery needed"),
    ("30", "Under 30 minutes"),
    ("2h", "1-2 hours"),
    ("hd", "Half a day"),
    ("fd", "Full day"),
    ("md", "Multiple days"),
]
_RD_CODE_TO_LABEL = dict(RECOVERY_DURATION_OPTIONS)

# index-coded multi-select, same convention as ACTIVE_LOADS/IDENTIFIED_NEEDS —
# spec §4 Q5 ("did you skip food, movement, rest, medication, sleep, or
# recovery?"), stored as recovery_factors (what got skipped, not what helped).
RECOVERY_FACTORS = [
    "Food", "Movement", "Rest", "Medication", "Sleep", "Recovery time", "Nothing skipped",
]

# spec §4 Q6 "what helped?" — same set as the evening reflection's
# DAY_WIN_HELPED_OPTIONS list minus its "nothing helped" catch-all, which
# reads oddly for a mid-episode question.
HELPFUL_ACTIONS_OPTIONS = [o for o in DAY_WIN_HELPED_OPTIONS if o != "Nothing clearly helped"]

# spec §4 Q7 "what made things worse?" — deliberately its own list rather
# than reusing HELPFUL_ACTIONS_OPTIONS; "what helped" and "what hurt" are not
# symmetric (e.g. "time pressure" has no helpful-list counterpart).
UNHELPFUL_ACTIONS_OPTIONS = [
    "Noise / sensory input", "Being interrupted", "Time pressure", "Uncertainty / change",
    "Social demands", "Physical exertion", "Skipping rest or food", "Pushing through pain",
    "Nothing made it worse",
]


def kb_deep_load_category(row_id: str) -> InlineKeyboardMarkup:
    base = f"ctd|id={row_id}"
    rows = [[InlineKeyboardButton(label.capitalize(), callback_data=f"{base}|lc={code}")]
            for code, label in LOAD_CATEGORY_OPTIONS]
    return InlineKeyboardMarkup(rows)


def kb_deep_yesno(base: str, key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes", callback_data=f"{base}|{key}=y"),
        InlineKeyboardButton("No", callback_data=f"{base}|{key}=n"),
    ]])


def kb_deep_recovery_duration(base: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"{base}|rd={code}")]
            for code, label in RECOVERY_DURATION_OPTIONS]
    return InlineKeyboardMarkup(rows)


def kb_deep_multiselect(row_id: str, key: str, options: list[str], selected: str) -> InlineKeyboardMarkup:
    """Same toggle-list shape as kb_multiselect, but for the deep-check
    steps that come after lc/uc/mp/rd are already saved to the row — base is
    always just the row id (write-through per tap), never an accumulating
    field string, so these stay well under the callback_data byte limit no
    matter how many of the (up to 9) options are selected."""
    base = f"ctd|id={row_id}"
    sel_set = set((selected or "").split(",")) if selected else set()
    buttons = []
    for i, label in enumerate(options):
        mark = "✅ " if str(i) in sel_set else ""
        sel = [x for x in (selected.split(",") if selected else []) if x]
        s = str(i)
        if s in sel:
            sel.remove(s)
        else:
            sel.append(s)
        new_val = ",".join(sel)
        buttons.append(InlineKeyboardButton(f"{mark}{label}", callback_data=f"{base}|{key}={new_val}"))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("➡️ Continue", callback_data=f"{base}|{key}={selected}|next=1")])
    rows.append([InlineKeyboardButton("✅ Done for now", callback_data=f"{base}|{key}={selected}|done=1")])
    return InlineKeyboardMarkup(rows)


def kb_deep_note_prompt(row_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⏭ Skip / save now", callback_data=f"ctd|id={row_id}|final=1"),
    ]])


# ── Evening reflection (spec §5) ─────────────────────────────────────────────

def kb_evening_trajectory() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬆️ Improved", callback_data="cte|dt=u"),
        InlineKeyboardButton("➡️ About the same", callback_data="cte|dt=s"),
        InlineKeyboardButton("⬇️ Declined", callback_data="cte|dt=d"),
    ]])


def kb_evening_helpful(dt: str) -> InlineKeyboardMarkup:
    base = f"cte|dt={dt}"
    rows = [[InlineKeyboardButton(label, callback_data=f"{base}|hf={i}")]
            for i, label in enumerate(DAY_WIN_HELPED_OPTIONS)]
    return InlineKeyboardMarkup(rows)


def kb_evening_debt(dt: str, hf: str) -> InlineKeyboardMarkup:
    base = f"cte|dt={dt}|hf={hf}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("No", callback_data=f"{base}|cd=n"),
        InlineKeyboardButton("Maybe", callback_data=f"{base}|cd=m"),
        InlineKeyboardButton("Yes", callback_data=f"{base}|cd=y"),
    ]])


# ── Therapy summary window selector ─────────────────────────────────────────

def kb_therapy_window() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("1 week", callback_data="cty|w=1"),
        InlineKeyboardButton("2 weeks", callback_data="cty|w=2"),
        InlineKeyboardButton("4 weeks", callback_data="cty|w=4"),
    ]])


# ── Parsing ─────────────────────────────────────────────────────────────────

def parse_cb(data: str) -> dict:
    result: dict[str, str] = {}
    for part in data.split("|")[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result


_FIELD_ORDER = ["c", "t", "p", "ps", "r", "e", "ld", "cp", "nd"]


def base_from(f: dict, keys: list[str] | None = None) -> str:
    """Rebuild a `ct|...` callback-data prefix from parsed fields, in
    canonical order, restricted to `keys` if given. Used to reconstruct the
    base string for the next screen instead of slicing the raw callback
    string (robust regardless of which button produced `f`)."""
    order = keys if keys is not None else _FIELD_ORDER
    parts = ["ct"] + [f"{k}={f[k]}" for k in order if f.get(k) is not None]
    return "|".join(parts)


def _idx_list(csv: str | None, options: list[str]) -> list[str]:
    if not csv:
        return []
    out = []
    for tok in csv.split(","):
        if tok.isdigit() and int(tok) < len(options):
            out.append(options[int(tok)])
    return out


# ── Writes ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(_TZ).isoformat()


def _time_of_day_label() -> str:
    h = datetime.now(_TZ).hour
    if 5 <= h < 12:
        return "Morning"
    if 12 <= h < 17:
        return "Afternoon"
    if 17 <= h < 21:
        return "Evening"
    return "Night"


async def write_quick_checkin(db, f: dict) -> tuple[bool, dict | None, str | None]:
    """Insert (or, if `id` already present, update) a capacity check-in row
    from parsed callback fields. Returns (saved, row, err_msg)."""
    if not db:
        return False, None, "Supabase unavailable (check SUPABASE_KEY)"

    payload: dict = {"checkin_type": "capacity", "source": "telegram"}
    if f.get("c"):
        payload["capacity_state"] = CAPACITY_CODE_TO_STATE.get(f["c"])
    if f.get("t"):
        payload["stimulation_state"] = STIM_CODE_TO_STATE.get(f["t"])
    if f.get("p"):
        payload["pain_state"] = PAIN_CODE_TO_STATE.get(f["p"])
    if f.get("ps") and f["ps"] != "skip":
        try:
            payload["pain_score"] = int(f["ps"])
        except ValueError:
            pass
    if f.get("r"):
        payload["regulation_state"] = REG_CODE_TO_STATE.get(f["r"])
    if f.get("e"):
        payload["executive_function"] = EF_CODE_TO_STATE.get(f["e"])
    if f.get("ld") is not None:
        loads = _idx_list(f["ld"], ACTIVE_LOADS)
        payload["active_loads"] = loads
    if f.get("cp"):
        payload["compensation_load"] = COMP_CODE_TO_STATE.get(f["cp"])
    if f.get("nd") is not None:
        needs = _idx_list(f["nd"], IDENTIFIED_NEEDS)
        payload["identified_needs"] = needs
    if f.get("act") and f["act"] != "skip":
        payload["selected_action"] = MASTER_ACTIONS.get(f["act"], f["act"])

    row_id = f.get("id")
    try:
        if row_id:
            payload["updated_at"] = _now_iso()
            res = db.table(TABLE).update(payload).eq("id", row_id).execute()
        else:
            payload["time_of_day"] = _time_of_day_label()
            res = db.table(TABLE).insert(payload).execute()
        row = (res.data or [None])[0]
        try:
            from core.platform.heartbeat import record_heartbeat
            record_heartbeat(TABLE, status="ok", detail=f"checkin_type=capacity source=telegram")
        except Exception:
            pass
        return True, row, None
    except Exception as exc:
        log.error("capacity_checkins write failed: %s | payload=%s", exc, payload)
        return False, None, str(exc)


async def fetch_checkin(db, row_id: str) -> dict | None:
    if not db:
        return None
    try:
        res = db.table(TABLE).select("*").eq("id", row_id).limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:
        log.error("capacity_checkins fetch by id failed: %s", exc)
        return None


async def write_deep_checkin(db, row_id: str, f: dict) -> tuple[bool, str | None]:
    if not db:
        return False, "Supabase unavailable (check SUPABASE_KEY)"
    payload: dict = {"updated_at": _now_iso()}
    if f.get("lc"):
        cat_map = {c: label for c, label in LOAD_CATEGORY_OPTIONS}
        payload["load_category"] = cat_map.get(f["lc"])
    if f.get("uc"):
        payload["unexpected_change"] = f["uc"] == "y"
    if f.get("mp"):
        payload["masking_present"] = f["mp"] == "y"
    if f.get("rd"):
        payload["recovery_duration"] = _RD_CODE_TO_LABEL.get(f["rd"], f["rd"])
    if f.get("rf") is not None:
        payload["recovery_factors"] = _idx_list(f["rf"], RECOVERY_FACTORS)
    if f.get("ha") is not None:
        payload["helpful_actions"] = _idx_list(f["ha"], HELPFUL_ACTIONS_OPTIONS)
    if f.get("ua") is not None:
        payload["unhelpful_actions"] = _idx_list(f["ua"], UNHELPFUL_ACTIONS_OPTIONS)
    if f.get("tn"):
        payload["trigger_note"] = f["tn"]
    if f.get("nt"):
        payload["notes"] = f["nt"]
    try:
        db.table(TABLE).update(payload).eq("id", row_id).execute()
        return True, None
    except Exception as exc:
        log.error("capacity_checkins deep-check update failed: %s", exc)
        return False, str(exc)


async def write_evening(db, f: dict) -> tuple[bool, str | None]:
    if not db:
        return False, "Supabase unavailable (check SUPABASE_KEY)"
    hf_idx = f.get("hf")
    helpful_factor = None
    if hf_idx is not None and hf_idx.isdigit() and int(hf_idx) < len(DAY_WIN_HELPED_OPTIONS):
        helpful_factor = DAY_WIN_HELPED_OPTIONS[int(hf_idx)]
    payload = {
        "checkin_type": "evening",
        "source": "telegram",
        "time_of_day": _time_of_day_label(),
        "day_trajectory": {"u": "improved", "s": "same", "d": "declined"}.get(f.get("dt")),
        "helpful_factor": helpful_factor,
        "capacity_debt": {"n": "no", "m": "maybe", "y": "yes"}.get(f.get("cd")),
    }
    try:
        db.table(TABLE).insert(payload).execute()
        try:
            from core.platform.heartbeat import record_heartbeat
            record_heartbeat(TABLE, status="ok", detail="checkin_type=evening source=telegram")
        except Exception:
            pass
        return True, None
    except Exception as exc:
        log.error("capacity_checkins evening write failed: %s", exc)
        return False, str(exc)


# ── Summary rendering (spec §3) ─────────────────────────────────────────────

def render_summary(row: dict) -> str:
    lines = ["MY CAPACITY TODAY", ""]
    if row.get("capacity_state"):
        lines.append(f"Capacity: {CAPACITY_LABEL.get(row['capacity_state'], row['capacity_state'])}")
    if row.get("stimulation_state"):
        lines.append(f"Stimulation: {STIMULATION_LABEL.get(row['stimulation_state'], row['stimulation_state'])}")
    if row.get("pain_state"):
        lines.append(f"Pain: {PAIN_LABEL.get(row['pain_state'], row['pain_state'])}")
    if row.get("regulation_state"):
        lines.append(f"System: {REGULATION_LABEL.get(row['regulation_state'], row['regulation_state'])}")
    if row.get("executive_function"):
        lines.append(f"Executive function: {EF_LABEL.get(row['executive_function'], row['executive_function'])}")
    if row.get("compensation_load"):
        lines.append(f"Compensation: {COMPENSATION_LABEL.get(row['compensation_load'], row['compensation_load'])}")
    loads = row.get("active_loads") or []
    if loads:
        lines += ["", "Main loads:"] + [f"  {l}" for l in loads]
    needs = row.get("identified_needs") or []
    if needs:
        lines += ["", "What I need:"] + [f"  {n}" for n in needs]
    if row.get("selected_action"):
        lines += ["", f"Next action: {row['selected_action']}"]
    lines += ["", "Today is about management, not proving what you can tolerate."]
    return "\n".join(lines)


# ── Trend / pattern analysis (spec §7 — no causal language) ────────────────

async def fetch_recent(db, days: int) -> list[dict]:
    if not db:
        return []
    since = (datetime.now(_TZ).date() - timedelta(days=days)).isoformat()
    try:
        res = (
            db.table(TABLE)
            .select("*")
            .gte("log_date", since)
            .order("captured_at", desc=False)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        log.error("capacity_checkins fetch_recent failed: %s", exc)
        return []


def render_trend_summary(rows: list[dict], label: str) -> str:
    quick = [r for r in rows if r.get("checkin_type") == "capacity"]
    evenings = [r for r in rows if r.get("checkin_type") == "evening"]
    if not quick and not evenings:
        return f"{label}\n\nNo check-ins logged in this window yet."

    zone_counts = Counter(r["capacity_state"] for r in quick if r.get("capacity_state"))
    total_zones = sum(zone_counts.values()) or 1
    load_counts = Counter(l for r in quick for l in (r.get("active_loads") or []))
    need_counts = Counter(n for r in quick for n in (r.get("identified_needs") or []))
    action_counts = Counter(r["selected_action"] for r in quick if r.get("selected_action"))
    debt_counts = Counter(e["capacity_debt"] for e in evenings if e.get("capacity_debt"))

    lines = [label, ""]
    if zone_counts:
        lines.append("Capacity:")
        for state, cd in (("green", "Green"), ("orange", "Orange"), ("red", "Red")):
            if zone_counts.get(state):
                pct = round(100 * zone_counts[state] / total_zones)
                lines.append(f"  {cd}: {pct}%")
        lines.append("")

    if load_counts:
        lines.append("Most common loads:")
        for i, (load, _) in enumerate(load_counts.most_common(3), 1):
            lines.append(f"  {i}. {load}")
        lines.append("")

    red_rows = [r for r in quick if r.get("capacity_state") == "red"]
    if red_rows:
        pre = Counter()
        for r in red_rows:
            if r.get("pain_state") in ("elevated", "high"):
                pre["elevated pain"] += 1
            if r.get("stimulation_state") == "high":
                pre["high sensory load"] += 1
            if r.get("compensation_load") in ("high", "extreme"):
                pre["high compensation"] += 1
        if pre:
            top = ", ".join(k for k, _ in pre.most_common(3))
            lines.append(f"Possible pattern: red-capacity check-ins often co-occurred with {top}.")
            lines.append("")

    if need_counts:
        lines.append("What helped most (needs identified most often):")
        for i, (need, _) in enumerate(need_counts.most_common(3), 1):
            lines.append(f"  {i}. {need}")
        lines.append("")

    if action_counts:
        lines.append("Most-used actions:")
        for i, (act, _) in enumerate(action_counts.most_common(3), 1):
            lines.append(f"  {i}. {act}")
        lines.append("")

    if debt_counts:
        total_evenings = len(evenings)
        yes_maybe = debt_counts.get("yes", 0) + debt_counts.get("maybe", 0)
        lines.append(f"Capacity debt: {yes_maybe} of {total_evenings} evening reflections")
        lines.append("")

    lines.append("(Patterns here are simple frequency counts, not clinical claims — worth testing, not treating as fact.)")
    return "\n".join(lines).rstrip()


def render_actions_summary(rows: list[dict]) -> str:
    quick = [r for r in rows if r.get("checkin_type") == "capacity" and r.get("selected_action")]
    if not quick:
        return "No actions logged yet in this window."
    counts = Counter(r["selected_action"] for r in quick)
    lines = ["Strategies used most often:", ""]
    for i, (act, n) in enumerate(counts.most_common(10), 1):
        lines.append(f"{i}. {act} ({n}x)")
    return "\n".join(lines)


def render_therapy_summary(rows: list[dict], weeks: int) -> str:
    quick = [r for r in rows if r.get("checkin_type") == "capacity"]
    evenings = [r for r in rows if r.get("checkin_type") == "evening"]
    lines = [f"THERAPY SUMMARY — LAST {weeks} WEEK{'S' if weeks != 1 else ''}", ""]

    if not quick:
        lines.append("No check-ins logged in this window yet.")
        return "\n".join(lines)

    zone_counts = Counter(r["capacity_state"] for r in quick if r.get("capacity_state"))
    total = sum(zone_counts.values()) or 1
    dominant = zone_counts.most_common(1)[0][0] if zone_counts else None
    dom_label = {"green": "green (sustainable)", "orange": "orange (stretched)", "red": "red (depleted)"}.get(dominant, "mixed")
    lines.append(f"Capacity: most check-ins were {dom_label}, with {zone_counts.get('red', 0)} red periods "
                  f"out of {total}.")
    lines.append("")

    load_counts = Counter(l for r in quick for l in (r.get("active_loads") or []))
    if load_counts:
        lines.append("Common contributors:")
        for load, _ in load_counts.most_common(4):
            lines.append(f"  - {load}")
        lines.append("")

    comp_rows = [r for r in quick if r.get("compensation_load")]
    if comp_rows:
        high_comp = sum(1 for r in comp_rows if r.get("compensation_load") in ("high", "extreme"))
        pct = round(100 * high_comp / len(comp_rows))
        lines.append(f"Compensation: high or extreme on {pct}% of check-ins.")
        lines.append("")

    high_pain = sum(1 for r in quick if r.get("pain_state") in ("elevated", "high"))
    if high_pain:
        lines.append(f"Pain: elevated or high on {high_pain} of {len(quick)} check-ins.")
        lines.append("")

    action_counts = Counter(r["selected_action"] for r in quick if r.get("selected_action"))
    if action_counts:
        lines.append("What helped:")
        for act, _ in action_counts.most_common(4):
            lines.append(f"  - {act}")
        lines.append("")

    debt_yes = sum(1 for e in evenings if e.get("capacity_debt") in ("yes", "maybe"))
    if evenings:
        lines.append(f"Capacity debt: {debt_yes} of {len(evenings)} evening reflections flagged borrowing from tomorrow.")
        lines.append("")

    lines.append("Questions to explore:")
    lines.append("  1. What early signals indicate a move from orange to red?")
    lines.append("  2. Where is masking happening that may not be necessary?")
    lines.append("  3. Which environmental changes could reduce baseline load?")

    return "\n".join(lines)
