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
from .priority_analyzer import PriorityAnalyzer
from .delegation_router import DelegationRouter

__all__ = [
    "ContextManager",
    "PriorityAnalyzer",
    "DelegationRouter",
]
