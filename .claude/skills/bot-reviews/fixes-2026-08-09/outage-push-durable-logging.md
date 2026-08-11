# Outage-push durable logging + weekly report surfacing

**Commissioned by:** Captain, in response to XO's product review of the
2026-08-09/10 Telegram brief rework — finding #5
(`xo-telegram-review.md` §2b): the new outage-push-alert feature had no
durable record of its own activity, and none of the three regular briefs
referenced it.

**Delivered:** 2026-08-10, commit `ffbbe23c` on `main` (pushed).

---

## 1. Durable logging

Read `core/platform/notification_service.py` fully first. Its only
bookkeeping is an in-process `_CALL_LOG` list — never persisted, doesn't
survive a restart, not queryable. Its own docstring already pointed at the
intended durable path: `core/platform/audit_service.py`'s `audit_events`
table (migration 0054), described there as taking "permission decisions,
approval decisions, **notification activity**, or anything else worth a
durable record" — built for exactly this, just never wired up for this
feature.

Checked the schema live before building anything new: `audit_events`
already exists (`id, category, actor, action, outcome, details jsonb,
mission_id, created_at`), is actively written to by three other call sites
in the codebase (`intelligence/governance/workflow_gate.py`'s
`log_mutation`, `core/coordination/telegram_build_executor.py`,
`platform-runtime/lib/comms/pipeline.py`), and has 423 real rows. No new
table or migration was needed — composition over duplication.

**Implementation** — `intelligence/persistence/intelligence_store.py`:
- `_maybe_push_outage_alert()` now captures the `NotificationResult` from
  `notify()` and passes it to a new `_log_outage_alert_fired()`.
- `_log_outage_alert_fired()` calls `core.platform.audit_service.
  record_audit_event()` with:
  - `category="notification"`, `actor="outage-alert-service"`,
    `action="outage_alert_push"`
  - `outcome="sent"` or `"failed"` (from `result.ok`)
  - `details`: `event_id`, `event_title`, `event_type`, `customer_impact`,
    `confidence`, `transport`, `error`
- Best-effort/non-blocking, matching the rest of this module's contract —
  a logging failure can never affect the alert that already fired.

## 2. Weekly report section

Read `intelligence/captains_brief.py` fresh (several agents were actively
editing it tonight — confirmed via a fresh `git status`/read, not assumed
from memory).

Added:
- `_get_weekly_outage_alerts(days=7)` — queries `audit_events` for
  `category=notification&action=outage_alert_push` in the trailing window.
- `_format_weekly_outage_alerts_block()` — renders `🚨 OUTAGE ALERTS THIS
  WEEK (N)`, a sent/failed count line, and up to 5 items
  (✅/❌ + title + impact/confidence), truncated with the existing
  `_truncate_clean` helper. Omitted entirely on a quiet week — same
  silence-is-a-valid-state convention `_format_infra_block` already uses.
- Wired into `generate_weekly_report()`, placed first in the message body
  (ahead of Tech/Health OSINT) — a fired outage push is the highest-severity
  single item any week can contain; the weekly reference is retrospective
  audit, not first notice (the real-time push already interrupted the
  Captain), so it leads rather than buries.

## Verification

- `python3 -m py_compile` clean on both files.
- Test-fired the logging path directly: called `_log_outage_alert_fired()`
  with a synthetic event and a fake `NotificationResult(ok=True)` — no
  `notify()` call, no real Telegram send. Confirmed via Supabase MCP that a
  row landed in `audit_events` with the correct category/action/outcome/
  details shape, then deleted the test row.
- Generated `generate_weekly_report()` live twice: once with the test row
  present (section rendered correctly — count, sent/failed line, item),
  once after cleanup (section correctly absent, rest of the report
  unaffected). Both states read correctly.

## Notes / open items (not in scope for this fix)

- No real outage-push events have fired since the logging call was added
  (verified: 0 real `audit_events` rows with this action live, other than
  the deleted test row) — the first live entry will land whenever the
  outage gate next fires for real. That's expected for a same-night fix,
  not a defect.
- This does not address XO review finding §2b's other flag (the
  misclassified political-story event on 2026-08-04) — that was fixed
  separately tonight in `intelligence/persistence/intelligence_store.py`
  via the `_has_outage_language` guard (commit `f555355c`, prior to this
  change).
