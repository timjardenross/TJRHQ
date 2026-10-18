"""Capacity enforcement mode (owner decision, 2026-10-18).

Capacity is still measured and shown everywhere it was before. What this switch controls is
whether a Red / Amber / Unknown reading *holds anything back*:

  advisory (default)  capacity is reported and flagged; nothing is trimmed, deferred or blocked.
  enforce             the original D-055 behaviour: follow-through nudges are trimmed, the gate
                      emits defer / limit actions, and the improvement budget closes on Red.

The default is "advisory" for the time being: the daily capacity signal is not yet linked into HQ
(the phone app is a capture source; aggregation and alerting in HQ is a later release), so gating
on a missing or thin signal would hold things back for no reason. To restore the original
behaviour, set the environment variable CAPACITY_ENFORCEMENT=enforce.
"""

from __future__ import annotations

import os

ENV_VAR = "CAPACITY_ENFORCEMENT"
MODES = ("advisory", "enforce")
DEFAULT_MODE = "advisory"


def capacity_enforcement_mode() -> str:
    value = (os.environ.get(ENV_VAR) or DEFAULT_MODE).strip().lower()
    return value if value in MODES else DEFAULT_MODE


def enforcing() -> bool:
    """True when capacity readings should hold work back (the original D-055 behaviour)."""
    return capacity_enforcement_mode() == "enforce"
