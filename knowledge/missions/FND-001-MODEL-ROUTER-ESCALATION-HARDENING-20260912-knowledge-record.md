# Knowledge Record — FND-001 model-router escalation hardening, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | none (direct fix commissioned from the 2026-09-12 VM resource investigation) |
| Title | Cloud-unavailability guard existed and worked correctly; its only fallback was itself unsafe on this host |
| Date | 2026-09-12 |
| Lesson | LL-149 |

## Outcome

`core/model-router/app.py`'s `escalate`/`fallback-complex` task types target
`MODEL_CLOUD` (`glm-5.3:cloud`) with a fallback to local `MODEL_LARGE`
(`mistral-small3.2:24b`) if the cloud tag isn't available. This guard was
added deliberately (PR #87/#101) and correctly detected `glm-5.3:cloud`'s
absence on every single call since the 2026-09-08 migration — the tag had
been configured in code but never actually pulled/registered on this VM's
Ollama install (`ollama pull glm-5.3:cloud` was never run here). Self-
improvement flagged this as FND-001 on both 2026-09-10 and 2026-09-11
(`EVO-0009`/`EVO-0012`/`EVO-0035`, later deduplicated to one record), each
time framed as an "ops-only" gap — pull the tag and the guard resolves
itself.

That framing was half right and half wrong. Pulling the tag is real (it now
works: a genuine `glm-5.3:cloud` inference call completes in ~1.8s once
registered) — but the deeper defect was structural, not operational: the
guard's *only* fallback destination, `MODEL_LARGE`, is a 24B model this host
(no GPU, 8 CPU cores, Ollama running with `-np 1`) cannot serve within any
real timeout. `call_log.jsonl` showed repeated genuine 300-second timeouts
on this exact path, confirmed live during the 2026-09-12 VM resource
investigation and independently during PR #113's testing that same day.
Pulling `glm-5.3:cloud` fixes today's specific instance, but the code had no
protection against the same class of failure recurring through any other
model or route — the next unavailable cloud tag would have degraded into
the same unsafe automatic 24B call.

Fixed by replacing the single-step fallback with a real degrade chain in a
new shared helper, `_resolve_cloud_escalation()`:

```
preferred cloud (glm-5.3:cloud)
    -> approved alternate cloud (glm-5.2:cloud — confirmed live via PR #113)
    -> host-safe local fallback (gemma3:4b — MODEL_MID, not MODEL_LARGE)
```

`MODEL_LARGE` was not removed — it remains available for other, deliberate,
scheduled task types (e.g. `intelligence-signals`) that explicitly budget
for its multi-minute CPU-only latency. It is now structurally unreachable
from the automatic escalation path (locked in by a dedicated regression
test that iterates every availability state and asserts `MODEL_LARGE` is
never selected). Every resolution now carries an observable
`route_tier`/`route_reason` in both the call log and the API response, so a
genuine cloud response is distinguishable from a degrade after the fact.

Live-verified post-fix: real `escalate` calls (including two fired
concurrently) completed via `cloud_primary` in 5–10s each; a forced
both-clouds-unavailable call completed via `local_safe_degraded` (gemma3:4b)
in 33s — nowhere near the 300s ceiling that produced the original incident.

## Lesson

**A working availability guard and a safe fallback destination are two
different things, and detecting the first does not prove the second.** This
guard never failed at its actual job — it correctly identified unavailability
on every single call for four days straight. The bug was a design gap one
layer past the guard: nothing evaluated whether the fallback it reached for
was itself appropriate for automatic, unattended use. A model can be
completely legitimate as a *deliberate* capability (scheduled, cost-budgeted,
someone accepted its latency explicitly) while being categorically wrong as
an *automatic* one (silently substituted, no one budgeted for its cost, and
the caller has no idea a degrade even happened until it times out).

## Future Guidance

Whenever a routing/fallback chain has exactly one degrade step, treat that
as a design smell, not a design decision — ask explicitly whether the
fallback destination is safe to select *automatically*, independent of
whether the primary-unavailability detection itself is correct. A resource-
constrained host (no GPU, few cores, no request parallelism) makes this
sharper: a model choice that's fine for a human-approved, scheduled job can
be actively dangerous as something a health check reaches for on its own.
Make the degrade path multi-tier (cheap/fast options before anything heavy),
make the tier that actually served a request observable in logs and
responses (not just the model name), and write the regression test as an
invariant over *every* availability state, not just the one state that
happened to be observed failing — that's what catches a future variant of
this same class of bug in a different task type before it needs its own
incident.

Also: self-improvement detected this finding correctly, twice, and both
times it was rediscovered on a later cycle without ever becoming a fixed
issue — see the separate follow-up finding on the missing
DETECTED→...→CLOSED lifecycle for repeated HIGH findings
([[fnd001-self-improvement-remediation-lifecycle-gap-20260912]]).
