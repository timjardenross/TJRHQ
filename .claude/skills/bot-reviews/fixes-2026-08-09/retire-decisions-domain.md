# Retire `decisions` domain — Captain-confirmed

**Date:** 2026-08-10
**Author:** Chief Engineer (Advisory, USS-TJR-003)
**Source finding:** `.claude/skills/bot-reviews/fixes-2026-08-09/final-4-domains.md`, section "2. `decisions` (Decisions Ledger) — NEEDS CAPTAIN DECISION".

## Decision

The Captain reviewed `final-4-domains.md`'s bundled two-part `decisions` writeup — (a) should `build_learning_loop`/`research_learning_loop`'s Slack-era events be rebuilt against a live entrypoint or retired; (b) should the comms Captain-approval decision-ledger chain be ported into the TS `advance` route or was its absence intentional — and took the third option that write-up flagged but didn't action: **retire the whole `decisions` domain from monitoring.**

Recap of why all three branches point the same way (full detail in `final-4-domains.md`):

- `build_learning_loop.py::record_build_lifecycle_event()` and `research_learning_loop.py::record_research_lifecycle_event()` both trace to retired Slack-era events (`commands/mission_brief.py`, `commands/research_command.py`) with no live replacement anywhere in the platform — not a dead-scheduler-with-a-restorable-schedule case, but an event that no longer exists in any live entrypoint (XO Telegram or LCARS Portal).
- `comms_learning_loop.py::record_comms_approval_event()` traces to `lib/comms/pipeline.py::advance()`, which has zero live callers. The real, live Captain-approval flow for comms content — `lcars-portal/src/app/api/comms/[id]/advance/route.ts` — reimplements the same state machine directly against `comms_content` and does not write `decision_records`, `commander_decisions`, `decision_outcomes`, or `quality_scores` at all.
- All 31 historical rows in `decision_records`/`commander_decisions` already trace to these dead sources.

## 1. Domain registry retirement

`core/infrastructure/supabase/migrations/0117_domain_registry_retire_decisions.sql` — same `active = false` soft-delete pattern as migrations 0112 (`governance_records`), 0113 (`pain_escalation`, `stale_missions_job`), 0114 (6 dead Slack domains), and 0116 (`decision_outcome_reminder`). Appends a dated retirement note to `notes` rather than overwriting it, consistent with every prior retirement migration. Applied live via Supabase MCP (`cjvrpjwewsrumnbdydgg`), matching the committed migration file.

Confirmed post-apply:

```
domain_key: decisions
active: false
notes: "Event-driven; Friday 16:00 weekly review -- RETIRED 2026-08-10: ..."
```

`domain_heartbeat_latest` (migration 0112) is scoped to `active` domains at the view level, so `run_verification_pass()` and `infra_narrative.py` both stop reporting `decisions` automatically — no Python code change required for the monitoring side.

## 2. The 3 now-orphaned heartbeat call sites — left in place

`build_learning_loop.py`, `research_learning_loop.py`, and `comms_learning_loop.py` each still call `record_heartbeat("decisions", ...)` after their respective (unreachable) write paths.

**Decision: left as-is, not removed.** Checked precedent first: migration 0114 retired 6 domains (`human_systems`, `appointment_prep`, `shakedown_digest`, `decision_review`, `knowledge_freshness`, `lessons_learned`) whose own heartbeat call sites live in `platform-runtime/human_systems_scheduler.py` and `platform-runtime/proactive_scheduler.py`. Diffing that migration's commit (`037608c8`) shows it touched only the migration SQL and its report doc — the heartbeat call sites in both `.py` files were left completely untouched, and remain in the code today (`grep` confirms `_record_heartbeat("human_systems", ...)` etc. still present). That's the established convention for this codebase: retiring a domain is a `domain_registry` change, not a code-removal exercise.

Following the same convention for `decisions`:

- A heartbeat write to an inactive domain is harmless — the write still lands in `domain_heartbeats`, but `domain_heartbeat_latest` (and therefore `run_verification_pass()`/monitoring/alerting) no longer reads it, because the view is scoped to `active` domains.
- Removing the calls would be pure code churn with no monitoring benefit, and would make re-activation (if a real live writer is ever built for one of the two Slack-era events, or the comms chain is ported to TS) require re-adding code instead of just flipping `active` back to `true`.

No `.py` files were edited for this task.

## 3. Verification — `decisions` cleared

Ran `run_verification_pass()` fresh (`core/platform/verification_engine.py`, env sourced from `platform-runtime/.env`) immediately after applying the migration:

```json
{
  "state": "unsure",
  "degraded_domains": [
    {"domain_key": "insight_outcomes", "display_name": "Insight Outcomes"},
    {"domain_key": "morning_brief", "display_name": "Morning Brief Push"},
    {"domain_key": "wellness-coaching", "display_name": "Wellness Coaching Signal"}
  ],
  "written": true
}
```

`decisions` confirmed absent. Baseline immediately before the migration (same command, same session) showed 4 entries including `decisions` — matching `final-4-domains.md`'s reported end state exactly, confirming no drift occurred between that report and this fix.

## 4. Final end-of-night sanity check

Ran `run_verification_pass()` a second time, back-to-back, purely as a stability check (no changes in between):

```json
{
  "state": "unsure",
  "degraded_domains": [
    {"domain_key": "insight_outcomes", "display_name": "Insight Outcomes"},
    {"domain_key": "morning_brief", "display_name": "Morning Brief Push"},
    {"domain_key": "wellness-coaching", "display_name": "Wellness Coaching Signal"}
  ],
  "written": true
}
```

Identical both times. **Final end-of-night `degraded_domains`: `insight_outcomes`, `morning_brief`, `wellness-coaching` (3).**

Status of each, per `final-4-domains.md` (unchanged by this mission, restated for the end-of-night record):

- `insight_outcomes` — code-complete from an earlier pass tonight; will clear on the next real insight generation.
- `morning_brief` — code-complete (heartbeat added), but today's 07:00 run already happened before the fix landed; will clear tomorrow 07:00 AEST.
- `wellness-coaching` — correctly wired and live-reachable via `/dispatch` (`tg-xo.service`, confirmed active); left manual-only per Chief Engineer judgment (no safe automated cadence exists without risking repeated Captain pings). Will self-clear on next real `/dispatch` use.

`degraded_count` end of tonight's full monitoring/heartbeat investigation: **4 → 3** (down from **13** at the start of the broader investigation captured across `retire-dead-domains.md` → `final-4-domains.md` → this document).

## Mission Status

Complete. `decisions` domain retired and verified cleared from monitoring. No open items for this domain — the two design questions `final-4-domains.md` raised (rebuild the Slack-era events, or port the comms decision-ledger chain to TS) are moot now that the domain itself is retired; either would require a new `domain_registry` row and a real feature build if ever revisited, not a re-activation of this one.
