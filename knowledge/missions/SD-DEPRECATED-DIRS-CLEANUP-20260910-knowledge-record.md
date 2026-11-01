# Knowledge Record — SD-FND-002 (dead_code, 2026-09-08 cycle)

| Field | Value |
|---|---|
| Mission ID | SD-FND-002 (dead_code, run 2026-09-08-210035) |
| Title | "Quarantined, not deleted" needs an expiry, or the quarantine never ends |
| Date | 2026-09-10 |
| Lesson | LL-143 |

## Outcome

Removed `telegram-bot.DEPRECATED-2026-07-12/` and `self-improving-loop.DEPRECATED-2026-07-29/` from the tree via PR #102, after confirming via `tools/verify_dead_code.py` that neither had any Python import, systemd unit, or crontab reference — only narrative doc mentions, which were updated to point at git history instead. Both directories' own `DEPRECATED.md` write-ups explicitly framed the retention as "quarantined (renamed, not removed) to preserve a recovery window" — not a permanent home.

## Lesson

Self-improvement's dead-code check flagged `telegram-bot.DEPRECATED-2026-07-12/` (2 months stale) and its own auto-remediation explicitly declined to delete it ("code deletions require manual review") — correctly conservative, but nothing then routed that manual-review request to a human or follow-up mission. It sat flagged-but-untouched for at least two more cycles. `self-improving-loop.DEPRECATED-2026-07-29/` was never flagged at all despite matching the identical pattern (quarantined directory, past its own stated recovery window, zero live references) — the dead-code check evidently isn't re-scanning directories it has no memory of having quarantined, only ones matching its live detection heuristics on that run.

## Future Guidance

A directory renamed to `*.DEPRECATED-<date>/` as a deliberate "recovery window, not permanent" convention needs either an actual expiry (a follow-up mission auto-created N weeks out) or a periodic sweep that lists every `*.DEPRECATED-*` directory in the tree and checks it against today's date — otherwise the convention silently degrades into permanent dead weight, discovered only by chance during an unrelated audit. When auto-remediation declines a finding as "needs manual review," that decline should itself be visible somewhere a human will actually see it (a handoff, a digest, a recurring reminder) rather than only living in `remediation_results.jsonl`.
