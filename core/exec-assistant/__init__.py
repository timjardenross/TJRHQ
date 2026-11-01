# ruff: noqa: N999 - directory name is fixed (core/exec-assistant/), matching the
# hyphenated convention used across this repo's top-level core/ modules
# (context-assembly, model-router, etc.); renaming would require touching every
# sys.path.insert()/import site across parallel in-flight worktrees. Out of
# scope for this ruff-cleanup mission.
"""Exec-Assistant Module

Proactive personal administrative support coordinating calendar, priorities,
communications, and strategic alignment.

Key Components:
- ContextManager: Learn and maintain executive preferences
- CalendarSync: Google Calendar integration
- PriorityAnalyzer: Eisenhower Matrix prioritization
- DelegationRouter: Route tasks to specialists
- BriefGenerator: Create daily/weekly briefs
- AlertEngine: Proactive alerts and recommendations
"""

__version__ = "0.1.0"
__status__ = "Phase 1: Foundation"

from .context_manager import ContextManager
from .delegation_router import DelegationRouter
from .priority_analyzer import PriorityAnalyzer

__all__ = [
    "ContextManager",
    "DelegationRouter",
    "PriorityAnalyzer",
]
