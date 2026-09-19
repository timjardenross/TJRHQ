# Coordination modules — command bus, delivery reconciliation, lifecycle
# tracking, engineering handoffs. Package marker only (no re-exports): its
# absence let pytest's package-root walk for core/coordination/tests/ stop
# one directory too early and import those tests under the bare name
# `tests`, colliding with the real top-level tests/ package whenever both
# were collected in one pytest invocation (`pytest tests core/coordination/tests`).
# Adding this file makes that walk continue past core/coordination/, so the
# leaf package resolves to core.coordination.tests instead.
