"""Objective Registry + Strategic Domain Model (MSN-SPC-001 WP1/WP2).

Reads the strategic layer (six domains → objectives → linked missions) and
composes the pure snapshot the Daily Operating Picture consumes. Reuses the
Command Memory access pattern (graceful CommanderSupabaseClient) and the
Active-Priorities P0–P5 scale. No new dashboard or pipeline.

Pure helpers (``rank_active``, ``top_per_domain``, ``compose_focus``) are fully
testable without Supabase; only the ``fetch_*`` functions touch the database.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

OBJECTIVES_TABLE = "strategic_objectives"
PROGRESS_VIEW = "strategic_objective_progress"
ORPHAN_VIEW = "strategic_orphan_missions"

# WP1: the six standing strategic domains (a closed set — mirrors the doctrine
# and the migration 0026 CHECK constraint).
STRATEGIC_DOMAINS: list[str] = [
    "Health & Human Systems",
    "Career & Professional Impact",
    "Starship Endeavour",
    "Coaching Enterprise",
    "Financial & Lifestyle",
    "Learning & Growth",
]

# The Vision is Captain-owned (see STRATEGIC-PLANNING-DOCTRINE.md §2.1). Held here
# as the north-star reference the strategic focus can point back to.
VISION = (
    "Build a sustainable, high-impact life — a regulated nervous system, "
    "meaningful professional impact, a coaching enterprise that helps others, "
    "and an AI Starship that compounds the Captain's leverage — capacity first."
)

ACTIVE_STATUS = "active"
_TERMINAL_STATUSES = {"closed", "archived"}
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Objective:
    objective_id: str
    domain: str
    title: str
    status: str = ACTIVE_STATUS
    priority: str = "P2"
    # Progress (populated from strategic_objective_progress when available).
    linked_missions: int = 0
    open_missions: int = 0
    completed_missions: int = 0
    completion_rate: float | None = None

    @property
    def is_active(self) -> bool:
        return (self.status or "").lower() == ACTIVE_STATUS

    @property
    def _rank(self) -> int:
        return _PRIORITY_ORDER.get((self.priority or "").upper(), 9)

    def progress_label(self) -> str:
        if self.linked_missions:
            rate = self.completion_rate
            pct = f" ({round(rate * 100)}%)" if rate is not None else ""
            return f"{self.completed_missions}/{self.linked_missions} missions done{pct}"
        return "no missions linked yet"


@dataclass
class StrategicSnapshot:
    objectives: list[Objective] = field(default_factory=list)
    orphan_count: int = 0
    data_available: bool = False

    @property
    def active(self) -> list[Objective]:
        return rank_active(self.objectives)

    @property
    def top(self) -> Objective | None:
        ranked = self.active
        return ranked[0] if ranked else None

    @property
    def active_domains(self) -> list[str]:
        seen: list[str] = []
        for o in self.active:
            if o.domain not in seen:
                seen.append(o.domain)
        return seen


# ── Pure helpers (testable without Supabase) ──────────────────────────────────

def rank_active(objectives: list[Objective]) -> list[Objective]:
    """Active objectives, highest priority first (then more-progressed first)."""
    active = [o for o in objectives if o.is_active]
    return sorted(active, key=lambda o: (o._rank, -(o.completion_rate or 0.0)))


def top_per_domain(objectives: list[Objective]) -> list[Objective]:
    """The single highest-priority active objective in each domain (domain order)."""
    ranked = rank_active(objectives)
    chosen: dict[str, Objective] = {}
    for o in ranked:
        chosen.setdefault(o.domain, o)
    order = {d: i for i, d in enumerate(STRATEGIC_DOMAINS)}
    return sorted(chosen.values(), key=lambda o: order.get(o.domain, 99))


def compose_focus(snapshot: StrategicSnapshot, *, limit: int = 3) -> list[str]:
    """Pure: the strategic-focus lines for the Daily Operating Picture (WP4)."""
    ranked = snapshot.active
    if not ranked:
        return []
    lines: list[str] = []
    for o in ranked[:limit]:
        lines.append(f"   • [{o.priority}] {o.title} — _{o.domain}_ · {o.progress_label()}")
    return lines


# ── Supabase access (graceful) ────────────────────────────────────────────────

def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("[strategy.objectives] Supabase unavailable: %s", exc)
        return None


def _row_to_objective(row: dict) -> Objective:
    rate = row.get("completion_rate")
    return Objective(
        objective_id=str(row.get("objective_id") or row.get("id") or ""),
        domain=str(row.get("domain") or ""),
        title=str(row.get("title") or "").strip(),
        status=str(row.get("status") or ACTIVE_STATUS),
        priority=str(row.get("priority") or "P2"),
        linked_missions=int(row.get("linked_missions") or 0),
        open_missions=int(row.get("open_missions") or 0),
        completed_missions=int(row.get("completed_missions") or 0),
        completion_rate=(float(rate) if rate is not None else None),
    )


def fetch_snapshot() -> StrategicSnapshot:
    """Compose the strategic snapshot from the registry + progress + orphan views.

    Always returns a value; ``data_available`` is False when Supabase is absent or
    no objectives exist (the brief then simply omits the strategic section).
    """
    c = _client()
    if c is None:
        return StrategicSnapshot()

    # Prefer the progress view (carries mission counts); fall back to the table.
    rows: list[dict] = []
    try:
        res = c.raw_client.table(PROGRESS_VIEW).select("*").execute()
        rows = list(res.data or [])
    except Exception:
        try:
            res = c.raw_client.table(OBJECTIVES_TABLE).select(
                "objective_id, domain, title, status, priority").execute()
            rows = list(res.data or [])
        except Exception as exc:
            log.warning("[strategy.objectives] fetch failed: %s", exc)
            return StrategicSnapshot()

    objectives = [_row_to_objective(r) for r in rows]

    orphan_count = 0
    try:
        ores = c.raw_client.table(ORPHAN_VIEW).select("mission_id").execute()
        orphan_count = len(list(ores.data or []))
    except Exception:
        orphan_count = 0

    return StrategicSnapshot(
        objectives=objectives,
        orphan_count=orphan_count,
        data_available=bool(objectives),
    )
