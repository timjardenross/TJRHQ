# Authority manifest baseline — 2026-09-15

This directory never existed in the repo despite `core/governance/authority_validator.py`
being built entirely around it (EXEC-001 WP1, MSN-0326 Waves 3/4). Every
`can_officer()`/`enforce_authority()`/`AuthorityContext` check for every
officer always hit the "no manifest" gap branch, which — since
`AUTHORITY_MANIFEST_GAP_MODE` defaults to `"raise"` — raised
`ManifestGapError` on every single check across the whole platform. Both
real call sites (`core/coordination/execution_engine.py`,
`platform-runtime/command_memory_integration.py`) only catch
`AuthorityError` specifically or a broad `except Exception: log
non-blocking, proceed` — `ManifestGapError` fell through to the broad
catch and was silently swallowed, so the gate was 100% fail-open in
practice everywhere, opposite of the documented "fail-closed by default"
intent.

Each `<officer>.yaml` in this directory gives that officer a real, present
manifest so the gap bug stops firing — deliberately unrestricted (empty
allow/deny/approval lists) to avoid changing any live behaviour
unilaterally. Real allow/deny/approval-required policy per officer/action
is a governance decision for a human to make, not inferred from what
happened to work while the bug was silently permitting everything.
