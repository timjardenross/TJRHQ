<!--
Worked example for docs/decisions/TEMPLATE-madr.md (MADR 4.0.0 format,
adopted format-only under USS-TJR-MSN-0366 Stream 10). This is not a
hypothetical — it documents a decision this repo already made and shipped
in core/model-router/app.py, written up retroactively in MADR shape so the
template has a real, grounded example to show future ADR authors instead
of a toy one. See that file's `_resolve_cloud_escalation()` (around line
472) and the MODEL_CLOUD / MODEL_CLOUD_ALT / MODEL_ESCALATION_SAFE_LOCAL
catalogue comments (around line 107) for the primary source this ADR is
transcribed from — labeled there as FND-001.
-->

---
status: "accepted"
date: 2026-09-12
decision-makers: Chief Engineer, self-improvement system (FND-001 detection)
consulted: Captain
informed: Knowledge Officer
---

# Model Router cloud-escalation degrade chain must never fall through to MODEL_LARGE automatically

## Context and Problem Statement

`core/model-router/app.py`'s `escalate` and `fallback-complex` task types
are meant to be cloud-first: they route to `MODEL_CLOUD` (`glm-5.3:cloud`),
a fast hosted model, with no local model kept resident (`keep_alive: "0"`).
On 2026-09-08, `MODEL_CLOUD` was bumped to `glm-5.3:cloud` on GLM 5.3's
release, but `ollama pull glm-5.3:cloud` was never actually run on this
host — the tag was configured in code without ever being registered.
`_available_model_names()` correctly reported the tag absent on every
call, so the router correctly fell through to its *only* fallback at the
time: `MODEL_LARGE` (`mistral-small3.2:24b`).

`MODEL_LARGE` is a 24B model this host (no GPU, 8 CPU cores, Ollama
running with `-np 1`, i.e. no parallel request slots) cannot serve within
any real timeout — `call_log.jsonl` showed repeated 300s "escalate"
timeouts, every time, from 2026-09-08 onward. The self-improvement system
flagged this independently on 2026-09-10 and again on 2026-09-11 (tracked
as FND-001) before it was root-caused and fixed on 2026-09-12.

Confirmed live: the `glm-5.3:cloud` tag itself is genuine and fast once
actually pulled (`ollama pull glm-5.3:cloud` succeeds; a real generate call
completed in ~1.8s). This was a registration/naming-drift defect — a gap
between "configured in code" and "registered on this host" — not a
liveness problem with the model itself, and not something the guard's own
availability check got wrong. The defect was architectural: the guard had
exactly one fallback step, and that step was unsafe to select
automatically.

How should an automatic cloud-unavailability guard degrade when its
preferred cloud model is unavailable, without ever landing on a fallback
that is itself unsafe to reach for automatically?

## Decision Drivers

* An automatic availability guard must never be able to pick a fallback
  destination that is *itself* unsafe under the conditions that triggered
  the fallback (a CPU-only, no-GPU, single-request-slot host).
* `MODEL_LARGE` has a legitimate, valuable role for *other*, deliberate
  task types (e.g. `intelligence-signals`) that explicitly budget for its
  multi-minute CPU-only latency — the fix must not remove that role, only
  stop an automatic path from reaching for it.
* Registration drift (a model tag configured in code but never
  `ollama pull`ed on the actual host) needs to fail toward something
  survivable, not toward the platform's single heaviest local model.
* The fix should be visible in logs and in the response's own routing
  metadata, so a future recurrence is diagnosable without re-deriving this
  investigation from scratch.

## Considered Options

* One-step fallback straight to `MODEL_LARGE` (the pre-existing behavior
  that caused FND-001)
* Three-step degrade chain: preferred cloud → approved alternate cloud →
  a small, always-safe local model (never `MODEL_LARGE`)
* Fail the request outright when `MODEL_CLOUD` is unavailable (no
  automatic local fallback at all)

## Decision Outcome

Chosen option: "Three-step degrade chain: preferred cloud → approved
alternate cloud → a small, always-safe local model", implemented as
`_resolve_cloud_escalation()`:

```
MODEL_CLOUD (glm-5.3:cloud)
    -> MODEL_CLOUD_ALT (glm-5.2:cloud)
    -> MODEL_ESCALATION_SAFE_LOCAL (gemma3:4b)
```

`MODEL_ESCALATION_SAFE_LOCAL` is deliberately `MODEL_MID` (`gemma3:4b`),
never `MODEL_LARGE` — the router's local model catalogue keeps both, but
only `gemma3:4b` is reachable from this automatic path. The function
returns `(policy, route_tier, route_reason)` so `_run_task()` can log
which tier actually served each request (`cloud_primary`, `cloud_alt`, or
`local_safe_degraded`), and the log line for the final degrade step
explicitly names what it did *not* do (`"...degrading to host-safe local
%s (NOT %s - see FND-001)"`) so a future reader hitting this path in logs
lands directly on the reasoning instead of having to reconstruct it.

This was the only option that satisfies every decision driver at once: it
keeps `MODEL_LARGE` available for deliberate, budgeted task types (driver
2) while making it structurally unreachable from the automatic guard
(driver 1), degrades toward something the host can actually serve within
the existing timeout (driver 3), and the tier is captured in the response
metadata and logs for future diagnosis (driver 4).

### Consequences

* Good, because a repeat of this exact failure mode (a cloud tag
  configured but never registered) now degrades to a fast local model
  within the existing timeout instead of hanging for 300s on every call.
* Good, because `MODEL_LARGE` keeps its role for task types that
  explicitly budget for it — nothing about those callers changed.
* Good, because the route actually taken (`route_tier`) is now visible in
  both logs and the task result, so a silent full-chain degrade is
  observable rather than indistinguishable from a normal cloud response.
* Bad, because a request that degrades all the way to
  `MODEL_ESCALATION_SAFE_LOCAL` gets a smaller, less capable model's
  output for a task type (`escalate`, `fallback-complex`) that was
  specifically routed to cloud for quality reasons — an accepted
  degradation in quality in exchange for not hanging or failing outright.
* Bad, because there are now three model tags
  (`MODEL_CLOUD`/`MODEL_CLOUD_ALT`/`MODEL_ESCALATION_SAFE_LOCAL`) to keep
  registered and correct on this host instead of one, which is more
  surface area for the next registration-drift defect — mitigated by the
  explicit self-improvement check that caught FND-001 in the first place
  continuing to run.

### Confirmation

`call_log.jsonl` entries for `escalate`/`fallback-complex` task types
carry the `route_tier` this function returned; a sustained run of
`local_safe_degraded` entries (rather than occasional ones during a real
cloud outage) is the signal that `MODEL_CLOUD` and/or `MODEL_CLOUD_ALT`
have drifted out of registration again, the same way FND-001 was
originally caught by the self-improvement system's periodic checks.

## Pros and Cons of the Options

### One-step fallback straight to `MODEL_LARGE`

The pre-existing behavior. Simple — one fallback, one code path.

* Good, because it requires no new model tags or code.
* Bad, because it is exactly the defect this ADR exists to fix: the one
  fallback destination is itself unsafe to select automatically on this
  host, and a registration-drift on `MODEL_CLOUD` turns every call into a
  guaranteed 300s timeout.
* Bad, because it gives a future reader no signal in logs about *why* a
  request degraded, or to what.

### Three-step degrade chain (chosen)

See Decision Outcome above.

* Good, because it separates "no cloud available" from "unsafe local
  fallback" — the chain only ever lands on a destination this host can
  actually serve quickly.
* Good, because it preserves an approved alternate cloud tier
  (`MODEL_CLOUD_ALT`) before giving up on cloud entirely, so a single
  tag's registration drift doesn't immediately sacrifice quality.
* Neutral, because it adds two more named constants to the model
  catalogue and one more branch to reason about.
* Bad, because (see Consequences) it is more surface area to keep
  correctly registered than a single fallback.

### Fail the request outright when `MODEL_CLOUD` is unavailable

No automatic local fallback at all — surface the unavailability to the
caller immediately instead of silently degrading quality.

* Good, because it never silently serves a lower-quality response in
  place of the one the caller asked for.
* Bad, because every caller of `escalate`/`fallback-complex` would need
  its own retry/fallback handling, duplicating logic this router exists
  to centralize.
* Bad, because a transient registration gap (like FND-001, fixable by
  running one `ollama pull`) would turn into hard failures for every
  caller in the meantime, rather than a degraded-but-working response.

## More Information

Primary source: `core/model-router/app.py`, `_resolve_cloud_escalation()`
(around line 472) and the `MODEL_CLOUD` / `MODEL_CLOUD_ALT` /
`MODEL_ESCALATION_SAFE_LOCAL` catalogue comments (around line 107),
labeled `FND-001` throughout. Detected by the self-improvement system on
2026-09-10 and 2026-09-11; root-caused and fixed 2026-09-12.
