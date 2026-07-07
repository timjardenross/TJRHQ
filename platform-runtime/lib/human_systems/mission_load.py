"""HSF-002 — Mission load ingestion (WP2).

Reads the Captain's current work load so the Decision Engine can evaluate
capacity *and* commitments together rather than independently.

Sources, all graceful (return empty/None when unavailable):
  - Supabase `missions` table — open (in-flight) mission count + titles.
  - memory/Active-Priorities.md — the Captain's standing priority list (P0–P5).

Nothing here decides anything; it only ingests. The allocation and overload
logic lives in decision.py.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# A mission is "open" (counts as load) unless it has reached a terminal state.
TERMINAL_STATUSES = {"closed", "archived"}

PRIORITIES_FILE = _REPO_ROOT / "memory" / "Active-Priorities.md"


@dataclass
class Priority:
    rank: str        # P0..P5
    label: str
    status: str = ""

    @property
    def is_active(self) -> bool:
        s = self.status.lower()
        return self.rank in ("P0", "P1", "P2") and "defer" not in s and "parked" not in s


@dataclass
class MissionLoad:
    open_count: int = 0
    open_titles: list[str] = field(default_factory=list)
    priorities: list[Priority] = field(default_factory=list)
    data_available: bool = False

    @property
    def top_priorities(self) -> list[Priority]:
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
        return sorted(self.priorities, key=lambda p: order.get(p.rank, 9))


def _supabase():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("[mission-load] Supabase unavailable: %s", exc)
        return None


def fetch_open_missions() -> tuple[int, list[str]]:
    """Return (open_count, titles) of in-flight missions. ([],0) when unavailable."""
    client = _supabase()
    if client is None:
        return 0, []
    try:
        result = client.raw_client.table("missions").select("title,status").execute()
        rows = list(result.data or [])
        open_rows = [
            r for r in rows
            if str(r.get("status", "")).strip().lower() not in TERMINAL_STATUSES
        ]
        titles = [str(r.get("title", "")).strip() for r in open_rows if r.get("title")]
        return len(open_rows), titles
    except Exception as exc:
        log.error("[mission-load] mission fetch failed: %s", exc)
        return 0, []


_PRIORITY_RE = re.compile(r"\b(P[0-5])\b[\s—:-]*(.+?)(?:\s*\((.*?)\))?$")


def load_priorities(path: Path | None = None) -> list[Priority]:
    """Best-effort parse of memory/Active-Priorities.md. Tolerant of format drift."""
    path = path or PRIORITIES_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    priorities: list[Priority] = []
    in_scale = False
    for line in text.splitlines():
        # Skip the priority-scale legend table (it defines P0..P5 generically).
        if line.strip().lower().startswith("## 2") or "priority scale" in line.lower():
            in_scale = True
            continue
        if in_scale and line.strip().startswith("##"):
            in_scale = False
        if in_scale:
            continue
        # Numbered list items like "1. **P0 — Repo Security** (In Progress, ...)"
        m = re.search(r"\*\*\s*(P[0-5])\s*[—:-]\s*(.+?)\*\*\s*(?:\((.*?)\))?", line)
        if m:
            rank, label, status = m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
            priorities.append(Priority(rank=rank, label=label, status=status))
    return priorities


def get_mission_load() -> MissionLoad:
    """Ingest current mission load + standing priorities. Always returns a value."""
    count, titles = fetch_open_missions()
    priorities = load_priorities()
    return MissionLoad(
        open_count=count,
        open_titles=titles,
        priorities=priorities,
        data_available=bool(count or titles or priorities),
    )
