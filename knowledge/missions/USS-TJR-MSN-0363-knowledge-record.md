# Knowledge Record — USS-TJR-MSN-0363

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0363 |
| Title | Removing a dead integration surfaces its own orphaned dependents, and app.py's removal doesn't imply theirs |
| Date | 2026-09-08 |
| Lesson | LL-139 |

## Outcome

Deleted 30 files genuinely coupled to the Slack SDK; rewired command_bus.py, notification_service.py, and the human_systems delivery pipeline to Telegram-only; kept the transport-agnostic Commander brain stack and platform-runtime/commands/ modules despite zero current callers, filing two task suggestions (health_appointment_prep.py's orphaned briefs, USS-TJR-Control's dashboard) rather than guessing at revive-vs-retire. All touched test suites re-run clean (19 suites, 0 failures).

## Lesson

Deleting platform-runtime/app.py (the Slack Bolt process) as directed left a whole cluster of modules with zero live callers: the Commander brain stack (commander_runtime.py etc.), the entire ~20-module platform-runtime/commands/ slash-command surface, and captains_inbox_capture.py's pipeline. All were only ever reachable through app.py's dispatch table. The instinct to also delete these because 'nothing calls them now' would have been wrong twice over: (1) most were never Slack-specific themselves, just Slack-dispatched — deleting them would destroy working, reusable logic over a removed transport, not removed functionality; (2) they were already unreachable in production before this change, since the Captain had already disabled Slack — the code cleanup just made that existing reality visible in the repo rather than creating it.

## Future Guidance

When removing a transport/integration's entry point, distinguish 'coupled to the transport itself' (imports the SDK, calls its API directly — delete or rewire) from 'only ever invoked through that transport's dispatch table' (generic logic that happens to have had one caller — keep, and flag the now-orphaned capability for a deliberate revive-or-retire decision rather than silently deleting or silently leaving it undocumented). Verify each file's actual imports and callers before batch-deleting anything that merely mentions the removed system's name.
