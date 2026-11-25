# Brief delivery recovery job: registration specification (for Production Operations)

Status: specification only. `intelligence/delivery_recovery.py` exists and is tested but is **not registered** in
`intelligence/scheduler.py`, in any unit, or in any configuration. Scheduler placement, privilege, runtime configuration and
activation are Production Operations decisions.

## What the job does
`delivery_recovery.job_recovery()` (never raises; same shape as `intel_products_job.job_daily`) reads the durable attempt
records (`intelligence_delivery_attempts`, draft migration 0264, not applied) for the last 48 hours and, for each brief
delivery that is not CONFIRMED, reports what the delivery state machine would do. It emits one structured report.

| Mode | Condition | Effect |
|---|---|---|
| report-only (default) | always | SELECT only. No store write, no send. The "after recovery" view is projected on a throwaway in-memory copy. |
| apply | `BRIEF_DELIVERY_RECOVERY_APPLY_V1` AND `BRIEF_DELIVERY_RECORD_V1` AND `BRIEF_DELIVERY_AUTO_RESEND_V1` all on | recovers interrupted attempts, then at most `MAX_SENDS_PER_RUN` (3) sends through `delivery_record.deliver` |

Apply actions, all through the state machine and its store uniqueness guard:
1. Attempts still `sending` for more than 15 minutes are marked finished with the in-flight chunk UNKNOWN (a younger one
   is left alone: it may be a live send).
2. Ambiguous (UNKNOWN or UNCONFIRMED) and not CONFIRMED: ONE marked `AUTHORISED_RECOVERY_RESEND` (marker message, then only
   the chunks not known to be confirmed), only if the last real activity is at least 10 minutes old, the brief is at most
   12 hours old, and the stored `brief_text` still hashes to the attempted content. A second resend is refused by the state
   machine however often the job runs.
3. Definite failure or definite partial (no ambiguity): continue as a plain PRIMARY for the missing chunks, no marker.
Nothing is sent on a brief whose outcome is CONFIRMED. No text for the brief (for example a `ref` key) means no send.

## Registration pattern (follow `_credential_expiry_job`, `intel_products_job.register_jobs`)
```python
# intelligence/scheduler.py (Production Operations to place; not done here)
from intelligence.delivery_recovery import job_recovery
scheduler.add_job(
    job_recovery,
    CronTrigger(minute="*/30", timezone=tz),           # suggestion; HOLD windows are also enforced inside the job
    id="brief_delivery_recovery", name="Brief delivery recovery (report-only unless apply flags set)",
    replace_existing=True, misfire_grace_time=600, coalesce=True, max_instances=1,
)
```
Suggested placement: guarded by its own enable env var like `INTEL_PRODUCTS_ENABLED` (not defined by this change; PO's
choice), default off. `max_instances=1` plus the store's uniqueness guard make overlap harmless; the job is still safe if
two instances run (tested with concurrent runs: exactly one marked resend).

## Runtime configuration (names only; values are Production Operations')
| Variable | Meaning | Default |
|---|---|---|
| `BRIEF_DELIVERY_RECOVERY_APPLY_V1` | allow apply (needs the two flags below too) | off |
| `BRIEF_DELIVERY_RECORD_V1`, `BRIEF_DELIVERY_AUTO_RESEND_V1` | existing WP2 flags, both required for apply | off |
| `BRIEF_DELIVERY_RECOVERY_DISABLE` | kill switch: truthy makes the job a no-op, re-checked before every send | unset |
| `BRIEF_DELIVERY_RECOVERY_REPORT_PATH` | optional file path; the report JSON is atomically replaced there each run | unset (log line only) |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | already present for the scheduler; the job needs the same access the brief writer has | existing |

## HOLD windows
The job returns `status="held"` without reading or sending inside 06:55-07:10, 12:25-12:40 and 17:55-18:10
Australia/Melbourne (inclusive, wall clock, DST-safe) and re-checks immediately before each send. Registration should
still avoid those minutes.

## Report record (deadman contract), schema 1
Logged as one line `[delivery_recovery_report] {json}` and optionally written to `BRIEF_DELIVERY_RECOVERY_REPORT_PATH`.
```
{schema:1, kind:"brief_delivery_recovery_report", generated_at, mode:"report_only"|"apply",
 status:"ok"|"held"|"disabled"|"error", hold_window, kill_switch, lookback_hours,
 counts:{briefs, confirmed, needs_attention, due_authorised_resend, due_continue, in_flight_wait, recovered_interrupted, expired, refused, sent},
 preventable_duplicates:int, needs_attention:bool, exactly_once_claimed:false,
 items:[{brief_table, brief_id, channel, content_hash(12), outcome, action, plan_reason, confirmed_chunks, ambiguous_chunks, chunks_total,
         recovery_resends, disclosure, apply_result?, not_before?, ...}], errors:[short codes]}
```
`action` is one of `confirmed`, `authorised_resend_due`, `continue_due`, `refused`, `expired`, `in_flight_wait`, `error`.
The report never contains message text. Suggested deadman rules: stale report (no `generated_at` within 2 intervals outside
HOLD) is a miss; `status="error"` is a miss; `preventable_duplicates > 0` is an alert; `needs_attention` for more than N
consecutive runs is an alert (an `expired` or repeatedly `refused` item needs a human; the job will not act on it).

## Dependencies and ordering (from the Production Operations assessment)
* The table (draft 0264) must exist and be approved/applied first; without it `list_recent` fails and the job reports
  `status="error"` (it never sends).
* Report-only can go first and is read-only. Apply must wait for R1 (#758, scheduler unprivileged) and an explicit owner
  approval to enable the three flags; this change enables nothing.
* Needs the notification-service extension merged first only for `classify_send_error` (the adapter delegates to it).
* Whole-repo staleness restarts every service on merge; land the notification-service PR and the recovery PR separately.

## Proposed API addition for `delivery_record` (not made here; that module has another owner)
`AttemptStore.list_recent(since_iso) -> list[AttemptRecord]` on the Protocol and both stores. This job subclasses the stores
(`InMemoryRecoveryStore`, `PostgrestRecoveryStore`) to add it; if the owner adds it natively the subclasses can be dropped.
