"""HSF-002 — Cross-Domain XO Decision Support (WP6).

The first cross-command orchestration capability. The XO estimates how the
Captain's capacity is already committed across Commands, computes what's left,
and answers a plain-language request with ONE recommendation.

Today only two providers report real signal — Human Systems (recovery need) and
Mission Load (work commitment). Engineering, Operational Resilience Intelligence,
Coaching Enterprise, and Knowledge are registered but not yet emitting capacity;
they are shown honestly as "not yet reporting" rather than guessed. As those
Commands are built (per CAP-001), they register a provider and light up here.

Pure and network-free. Decision-reduction: one recommendation, not a menu.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import framework, safety
from .mission_load import MissionLoad
from . import decision


# Registered Commands. `reporting=False` = ready to plug in, not yet emitting.
REGISTERED_COMMANDS = [
    {"key": "recovery", "label": "Recovery", "reporting": True},
    {"key": "work", "label": "Missions / Work", "reporting": True},
    {"key": "engineering", "label": "Engineering", "reporting": False},
    {"key": "ori", "label": "Operational Resilience Intelligence", "reporting": False},
    {"key": "coaching", "label": "Coaching Enterprise", "reporting": False},
    {"key": "knowledge", "label": "Knowledge", "reporting": False},
]

_RECOVERY_SHARE = {"depleted": 50, "limited": 35, "moderate": 25, "good": 15}


@dataclass
class CapacityAllocationView:
    band: str
    shares: dict[str, int] = field(default_factory=dict)  # label → % committed
    remaining: int = 0
    not_reporting: list[str] = field(default_factory=list)


def allocate(snapshot: framework.CapacitySnapshot, load: MissionLoad) -> CapacityAllocationView:
    """Estimate how current capacity is already committed across Commands."""
    band = snapshot.overall_band
    recovery = _RECOVERY_SHARE.get(band, 25)
    work = min(70, load.open_count * 12) if load.data_available else 0
    committed = min(100, recovery + work)
    remaining = max(0, 100 - committed)

    shares = {"Recovery": recovery}
    if load.data_available:
        shares["Missions / Work"] = work

    not_reporting = [c["label"] for c in REGISTERED_COMMANDS if not c["reporting"]]
    return CapacityAllocationView(
        band=band, shares=shares, remaining=remaining, not_reporting=not_reporting,
    )


_NEW_INITIATIVE_HINTS = (
    "business", "coaching", "new ", "start", "launch", "initiative", "side project",
    "build a", "grow", "expand",
)


def _is_new_initiative(request: str) -> bool:
    r = request.lower()
    return any(h in r for h in _NEW_INITIATIVE_HINTS)


def xo_decision(
    request: str,
    snapshot: framework.CapacitySnapshot,
    load: MissionLoad,
    *,
    notes: str | None = None,
    scan: bool = True,
) -> str:
    """Answer a cross-domain Captain request with one capacity-grounded recommendation.

    ``scan`` may be set False when the caller has already scanned the input for
    red flags (e.g. the /hs command boundary), to avoid a duplicate banner.
    """
    escalation = (
        safety.escalation_banner(safety.scan_red_flags(f"{request} {notes or ''}"))
        if scan else None
    )

    view = allocate(snapshot, load)
    remaining = view.remaining
    wants_new = _is_new_initiative(request)

    # Single recommendation, grounded in remaining capacity.
    if wants_new and remaining < 20:
        rec = (
            "Consider holding new initiatives this week. With limited spare "
            "capacity, the higher-value choice is protecting recovery and existing "
            "commitments — the new work will land better when there's room for it."
        )
    elif wants_new and remaining < 40:
        rec = (
            "A small, time-boxed first step could fit — but keep it to one session "
            "and protect recovery around it. Avoid committing to more than that yet."
        )
    elif wants_new:
        rec = (
            "There is room to make a start. Consider one concrete, time-boxed step "
            "this week, and keep a recovery block protected so it stays sustainable."
        )
    else:
        # Non-"new-initiative" request: defer to the highest-leverage action.
        frictions = decision.detect_friction([])  # no rows here; rely on snapshot
        rec = decision.highest_leverage(snapshot, load, frictions).primary

    lines = []
    if escalation:
        lines += [escalation, "", "———", ""]
    lines += [
        "*XO Decision Support*",
        f"_Request: {request.strip()}_" if request.strip() else "",
        "",
        f"*Current capacity allocation* (capacity is {view.band}):",
    ]
    for label, pct in view.shares.items():
        lines.append(f"• {label}: ~{pct}%")
    lines.append(f"• Remaining: ~{remaining}%")
    if view.not_reporting:
        lines.append("")
        lines.append(
            "_Not yet reporting capacity: " + ", ".join(view.not_reporting) +
            " — these light up as those Commands come online._"
        )
    lines += ["", "*Recommendation:*", rec]
    return safety.frame("\n".join(l for l in lines if l is not None))
