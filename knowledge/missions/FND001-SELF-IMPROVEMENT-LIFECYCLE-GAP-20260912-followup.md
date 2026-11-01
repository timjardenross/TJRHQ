# Follow-up finding — repeated HIGH/needs_signoff findings have no escalation path, 2026-09-12

## What was checked

Why was FND-001 (model-router escalate/fallback-complex routing to an
unavailable cloud model) detected repeatedly without ever becoming a
completed remediation, until an unrelated VM resource investigation
surfaced it externally on 2026-09-12?

`data/self-improvement/review/remediation_results.jsonl` shows the answer
directly — `AutoRemediationExecutor` (the bounded-remediation engine) ran
against a finding labelled `FND-001` on **every single cycle from
2026-08-29 through 2026-09-08** (15 recorded attempts across 10 days) and
skipped it every time, with the identical message:

```
"Skipped: model confidence, risk level, or automation eligibility"
```

This matches the finding's own `policy_decision_rationale`
(`automation_eligibility: needs_signoff`, `risk_level: high`) — the skip is
*correct* per policy; a high-risk, needs-signoff change is deliberately not
something the bounded-remediation engine should auto-apply. That part of
the system is working as designed.

## The actual gap

Nothing happens after the skip. `AutoRemediationExecutor` logs the skip and
moves on; there is no mechanism that:

- notices a finding has now been skipped N times in a row,
- distinguishes "skipped once, still fresh" from "skipped on every cycle
  for over a week," or
- pushes a repeatedly-skipped, high-risk finding toward an actual human
  decision (as opposed to waiting for a human to open the dashboard and
  notice it).

Even after `internal_discovery`'s dedup work (2026-09-12, separate PR)
promoted this into human-visible `Opportunity` cards (`EVO-0009` /
`EVO-0012` / `EVO-0035`), the canonical card (`EVO-0009`) sat in
`lifecycle_state: "proposed"` with no further movement — the dashboard's
`/api/opportunity/decide` endpoint is pull-based (a human has to visit and
act), not push-based. A `needs_signoff` finding that nobody happens to look
at can sit indefinitely with no signal that it is overdue.

## Recommended future lifecycle (not implemented here — out of scope per mission)

```
DETECTED -> CONFIRMED -> PRIORITISED -> ASSIGNED -> FIXED -> VERIFIED -> CLOSED
```

A finding that has been independently re-detected (same fingerprint, or the
same underlying condition) across some threshold of consecutive cycles
while sitting in a non-terminal state should stop being passive
observability and become an actionable signal — at minimum, distinct from a
first-time finding, in whatever channel already carries HQ's actionable
items (Captain's Brief, XO notification, etc.), and ideally with a
"cycles-unresolved" counter attached to the Opportunity record itself so
its urgency is visible at a glance rather than requiring someone to
cross-reference `remediation_results.jsonl` by hand, the way this
investigation had to.

## Scope note

This is a follow-up finding only, per this mission's explicit instruction
not to redesign the self-improvement system. No code changed for this item.
Referenced from [[FND-001 model-router escalation hardening (LL-149)]].
