"""MY CAPACITY TODAY — the day plan (step 2 of the good-days model).

Shown under the quick check-in summary. It is a set of suggestions the Captain can ignore:
a capacity reading never defers, limits or blocks anything (owner decision 2026-11-02), and
nothing here is stored or enforced. Pure functions, no I/O, so the wording and the reasons are
easy to test and to change.

Shape: the zone with a few plain reasons taken from the whole check-in (not just the one-tap
zone), one prompt that depends on the zone, then up to three ranked suggestions, each tagged with
its management lever (Reduce / Regulate / Recover / Redesign). Language follows the spec: no
diagnosis, no shame, no "should", and no productivity pressure.
"""

from __future__ import annotations

from typing import Any

MAX_SUGGESTIONS = 3

LEVER_LABEL = {
    "reduce_load": "Reduce",
    "regulate": "Regulate",
    "recover": "Recover",
    "redesign": "Redesign",
}

ZONE_HEADLINE = {
    "green": "🟢 Sustainable",
    "orange": "🟠 Stretched",
    "red": "🔴 Depleted",
}

# One prompt per zone (spec section 9). Orange is the early-intervention moment.
ZONE_PROMPT = {
    "green": "You have room today. Spend some, bank some: capacity left over doesn't have to be used.",
    "orange": "What could you reduce, regulate or change before this becomes red?",
    "red": "Today can be the smallest workable day. Nothing else is held back; this is just the "
           "gentlest option.",
}

_PAIN_REASON = {
    "elevated": "pain is above your usual",
    "high": "pain is much higher than usual",
}
_EF_REASON = {
    "strained": "thinking and deciding is taking more effort",
    "difficult": "thinking and deciding is difficult",
    "very_difficult": "thinking and deciding is very difficult",
}
_COMP_REASON = {
    "high": "you're pushing or masking a lot",
    "extreme": "you're forcing yourself through",
}
_REG_REASON = {
    "activated": "your system feels activated",
    "overloaded": "your system feels overloaded",
}
_STIM_REASON = {
    "high": "stimulation is too high",
    "low": "stimulation is too low",
}


def day_reasons(row: dict[str, Any], recent_debt: tuple[int, int] | None = None) -> list[str]:
    """Plain-language reasons from the whole check-in. Only things that were answered and are
    notable are listed; a missing answer is never treated as a problem.

    ``recent_debt`` is (evenings that flagged borrowing capacity, evenings answered) over the
    last few days, or None when there's nothing to report.
    """
    reasons: list[str] = []
    for key, table in (
        ("pain_state", _PAIN_REASON),
        ("executive_function", _EF_REASON),
        ("compensation_load", _COMP_REASON),
        ("regulation_state", _REG_REASON),
        ("stimulation_state", _STIM_REASON),
    ):
        text = table.get(row.get(key) or "")
        if text:
            reasons.append(text)
    if recent_debt and recent_debt[1] > 0 and recent_debt[0] > 0:
        flagged, answered = recent_debt
        reasons.append(f"you marked borrowing capacity on {flagged} of your last {answered} evenings")
    return reasons


def _suggestion_line(index: int, intervention: dict[str, Any]) -> str:
    title = intervention.get("title") or intervention.get("button_label") or "Suggestion"
    lever = LEVER_LABEL.get(intervention.get("management_lever") or "")
    minutes = intervention.get("estimated_minutes")
    tags = [t for t in (lever, f"{minutes} min" if minutes else None) if t]
    suffix = f" ({', '.join(tags)})" if tags else ""
    return f"{index}. {title}{suffix}"


def render_day_plan(
    row: dict[str, Any],
    interventions: list[dict[str, Any]] | None = None,
    recent_debt: tuple[int, int] | None = None,
) -> str:
    """The plan text, or "" when there's no capacity answer to build it on."""
    zone = row.get("capacity_state")
    if zone not in ZONE_HEADLINE:
        return ""

    lines = ["TODAY'S PLAN (suggestions only, nothing is held back)", ""]
    reasons = day_reasons(row, recent_debt)
    headline = ZONE_HEADLINE[zone]
    if reasons:
        lines.append(f"{headline}: " + "; ".join(reasons) + ".")
    else:
        lines.append(headline + ".")
    lines += ["", ZONE_PROMPT[zone]]

    picks = (interventions or [])[:MAX_SUGGESTIONS]
    if picks:
        lines += ["", "A few options, if any of them help:"]
        lines += [_suggestion_line(i, p) for i, p in enumerate(picks, 1)]
    return "\n".join(lines)
