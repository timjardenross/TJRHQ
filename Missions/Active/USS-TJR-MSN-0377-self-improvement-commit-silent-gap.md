# Mission Brief

## Mission Header

- **Mission ID:** USS-TJR-MSN-0377
- **Priority:** P2 — real, recurring data-pile-up; not itself an outage
- **Source:** live incident follow-up (2026-09-13) — ~61 cycles of `data/self-improvement/runs/*` sat uncommitted until manually committed today.

## Pre-flight

1. **Existing-entry check / premise verification** — the working assumption going in ("the orchestrator never commits its own output") is **already wrong**:
   ```
   grep -n "git_commit" scripts/self_improvement/orchestrator.py
   → line 194: run_full_cycle() DOES call self.executor.git_commit(..., paths=[artifacts_path])
     at the end of every cycle. Added 2026-09-10 specifically to fix this exact class of bug
     (comment cites "FND-001, Uncommitted Self-Improvement Cycle Artifacts").

   git log --all --grep="self-improvement: cycle" --format="%ad %s" --date=short | sort
   → 8 real cycle-artifact commits exist, 2026-08-31 through 2026-09-09. NONE since.
     hq-evolution.timer fires daily — that's a 3+ day silent gap, not "never worked."

   knowledge/Lessons-Learned.md LL-146 (2026-09-12): diagnosed root cause — git_commit()
   ran against whatever branch happened to be checked out, no push, commits landing as
   orphan local commits that never reached origin. Explicitly "Not fixed here."

   knowledge/Lessons-Learned.md LL-149 (same day, 2026-09-12): the actual fix — git_commit()
   now "fails closed on branch mismatch and pushes on success."
   ```
   So the real question isn't "does it commit" — it's: **after LL-149's fail-closed fix landed, is it now silently refusing every cycle (real branch mismatch on the VM, no alert), or did the 61-cycle pile-up predate the fix and just needed a one-time manual catch-up?** This mission does not assume either answer.

2. **Explicitly not in scope:**
   - Rewriting `git_commit()`'s branch/push logic — LL-149 already fixed the mechanism itself; this mission only checks whether it's actually firing successfully and, if not, why silently.
   - `.secrets.baseline` allowlisting or any detect-secrets exclusion decision — separate track (MSN-0376).
   - Any other self-improvement pipeline behavior (classification, remediation, decisions) — commit-path only.

## Scope

1. **Confirm on the real VM** (not this sandbox) whether `/opt/starship-endeavour`'s checked-out branch matches what `git_commit()` expects, and whether recent `hq-evolution.timer` runs are hitting the fail-closed path (check its logs/journal for the warning at orchestrator.py:200, `"Cycle artifacts commit failed or had nothing to commit"`, or LL-149's branch-mismatch message).
2. Based on that finding: either (a) it's a stale/one-off branch state — fix the checkout and confirm the next scheduled run produces a real commit, or (b) it's a structural mismatch that will keep recurring — fix that condition.
3. Either way: **the fail-closed path currently has no alerting.** Add one — a repeated silent refusal is exactly the failure mode that let 61 cycles pile up unnoticed. Route it through the existing Notification capability (`core/platform/notification_service.py`), not a new mechanism.

## Acceptance

- Real evidence of which failure mode was live (branch-state check + timer logs), not assumed.
- At least one real `hq-evolution.timer` run after the fix produces an actual pushed cycle-artifact commit — verified, not asserted.
- A repeat fail-closed refusal now produces a real, visible notification instead of silence.
- SUOC Platform Registry: note under whichever capability owns self-improvement's operational health (or add one if none currently does) — flag if that's a real gap in itself.

## Reporting

One knowledge record (`knowledge/missions/USS-TJR-MSN-0377-knowledge-record.md`).
