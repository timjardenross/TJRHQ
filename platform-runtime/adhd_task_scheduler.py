"""
ADHD Task Nudge Scheduler Integration — Issue 26

Integrates intelligence/adhd/task_nudge_scheduler.py into platform-runtime's
proactive scheduler infrastructure.

Configuration (.env):
  ADHD_NUDGE_ENABLED      = "true"         # Enable task nudge scheduling
  ADHD_NUDGE_INTERVAL     = "3600"         # Check interval in seconds (default: 1 hour)
  ADHD_NUDGE_DB           = "/tmp/adhd_nudges.db"  # Rate limit DB location

Usage:
  from adhd_task_scheduler import start_adhd_task_scheduler
  start_adhd_task_scheduler(supabase_client)  # Call after Supabase client init
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ENABLED = os.environ.get("ADHD_NUDGE_ENABLED", "true").lower() == "true"
_INTERVAL = int(os.environ.get("ADHD_NUDGE_INTERVAL", "3600"))  # 1 hour default


def _run_nudge_check(supabase_client) -> dict | None:
    """Invoke the task nudge scheduler and log results."""
    if not _ENABLED:
        log.debug("[adhd_task_scheduler] Disabled via ADHD_NUDGE_ENABLED=false")
        return None

    try:
        # Dynamically import to avoid hard dependency on intelligence module
        sys.path.insert(0, str(_REPO_ROOT))
        from intelligence.adhd.task_nudge_scheduler import nudge_scheduler_entry_point

        result = nudge_scheduler_entry_point(supabase_client)
        log.info("[adhd_task_scheduler] Nudge check complete: %s", result)
        return result
    except Exception as e:
        log.error("[adhd_task_scheduler] Failed: %s", e)
        return None


def start_adhd_task_scheduler(supabase_client) -> threading.Thread:
    """
    Start the ADHD task nudge scheduler as a background daemon thread.

    Args:
      supabase_client: Initialized Supabase client (from platform-runtime)

    Returns:
      The daemon thread (already started)

    Usage:
      from adhd_task_scheduler import start_adhd_task_scheduler
      thread = start_adhd_task_scheduler(supabase_client)
    """

    def _scheduler_loop():
        log.info(
            "[adhd_task_scheduler] Starting (interval=%d seconds, enabled=%s)",
            _INTERVAL,
            _ENABLED,
        )
        while True:
            try:
                _run_nudge_check(supabase_client)
            except Exception as e:
                log.error("[adhd_task_scheduler] Loop error: %s", e)
            time.sleep(_INTERVAL)

    thread = threading.Thread(target=_scheduler_loop, daemon=True, name="adhd-task-scheduler")
    thread.start()
    return thread
