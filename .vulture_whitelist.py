"""Vulture whitelist — TJRHQ.

Only add entries here for CONFIRMED false positives (verified by reading the
call site, not preemptively). See reports/vulture/README.md for the run that
produced these.

Each entry is a dummy reference so Vulture's static usage-graph stops
flagging the name as unused; it is never executed.
"""

# `__exit__(self, exc_type, exc_val, exc_tb)` is the Python context-manager
# protocol signature — the three trailing args are required by the interface
# even when the implementation (as here) ignores them and just calls
# self.close(). Confirmed at:
#   core/infrastructure/mac-collector/db.py:71
#   core/infrastructure/vm-transfer/transfer_db.py:78
_exit_protocol = None
_exit_protocol.exc_type
_exit_protocol.exc_val
_exit_protocol.exc_tb
