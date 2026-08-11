# XO Telegram Bot — debrief_engine + doc-drift fixes

USS TJR — Chief Engineer persona, Registry USS-TJR-003, Advisory authority
Date: 2026-08-09
Source review: `.claude/skills/bot-reviews/xo-telegram-bot/chief-engineer-review.md` (findings 5 and 6)
Commits: `1397784` (code), `bee860f` (docs) — both on `origin/main`

## Finding 6 — `debrief_engine.py` doesn't exist

**Investigation.** Grepped all 5 import sites in `telegram-bots/xo/app.py`
(`cmd_message`, `cmd_voice_note`, `cmd_debrief_close`, the voice-debrief-decision
callback, plus a comment at the `de is None` fallback). `git log --all` for
`debrief_engine.py` returns zero commits on any branch — it was never checked
in; a stale `.pyc` in a dated backup tree is the only trace it ever existed.

Contrary to the review's framing this needed active fixing, all 5 sites were
**already guarded** by two prior commits (`d53dfec`, `65663f6`) found in git
history before I touched anything: every import is wrapped in
`try/except ImportError`, and each of the 4 execution paths degrades honestly
— `cmd_message` falls through to the plain LLM reply, `cmd_voice_note` falls
through to plain quick-capture, `cmd_debrief_close` and the voice-debrief
callback reply "Debrief is unavailable — the module isn't present on this
deploy" instead of crashing. This is not a live crash risk; it's confirmed
dead/unreachable functionality, gracefully absent.

**What was still missing** (the review's own residual note, recommendation 6):
the two silent-degradation branches (`cmd_message`, `cmd_voice_note`) caught
the `ImportError` but never logged it — the only way to know debrief was
broken was inference from the Captain never getting the feature. Added
`log.warning(...)` to both `except ImportError` branches so a missing
`debrief_engine` is now visible in `journalctl -u tg-xo.service` on the very
first free-text message or voice note, not just discoverable by code reading.

No fake `debrief_engine.py` was invented — there wasn't enough source (design
doc, working analog) to build a confident minimal implementation, and the
review explicitly warned against guessing. `py_compile` clean on `app.py`.

## Finding 5 — deploy doc drift

**`deploy/README-xo-bot.md`** fully described the retired shell-agent
architecture (`planner.py`/`executor.py`/`actions.py`/`shellrun.py`, `xo-bot/`
directory, per-step Approve/Skip/Cancel, `/audit`, `XO_ALLOWED_CHAT_IDS`) —
none of that exists in the repo (superseded 2026-07-05). Rewritten from
scratch to describe the real bot: file inventory that actually exists, the
full real command set (pulled from `_BOT_COMMANDS`/`main()`'s
`CommandHandler` registrations in `app.py`), the real security model (the
`_global_auth_gate` `TypeHandler` at `group=-1`, added same day as this
review in commit `fc24c93` — not the old per-handler-only pattern), the
`debrief_engine` gap, and the real install path: `deploy/xo-bot.service` is
copied to `/etc/systemd/system/tg-xo.service` (source and destination
filenames intentionally differ — confirmed against live `systemctl cat
tg-xo.service`).

**`telegram-bots/xo/DEPLOYMENT.md`** had a subtler drift than the README:
it asserted the bot "uses `AsyncIOScheduler` (NOT `BackgroundScheduler`)."
Grepped `app.py`, `voice_capture.py`, `pulse_time.py` for
`apscheduler`/`scheduler` — zero real usage; proactive pushes are entirely
owned by the separate `intelligence-scheduler.service` (confirmed live via
`journalctl`, successful 07:00 deliveries on 08-07/08/09). Its example
systemd unit also showed a single `EnvironmentFile`, which would reintroduce
an already-fixed production bug (missing `platform-runtime/.env` →
`EMBEDDING_PROVIDER` unset → `/advise`/`/challenge` silently degraded on a
1024-vs-768-dim mismatch, per `deploy/xo-bot.service`'s own header comment).
Fixed the scheduler section, corrected the systemd snippet to the real
two-`EnvironmentFile` unit, corrected the `requirements.txt` version list to
match what's actually pinned (`gotrue==1.3.1` was missing, `httpx` bound was
stale), added a security note distinguishing anon vs. `service_role`
Supabase keys (per the review's Finding 2), and added a "Known gaps" section
covering `debrief_engine` and `app.py`'s missing test coverage.

`apscheduler` remains in `requirements.txt` as a flagged-but-not-removed dead
dependency — pruning it is a code/dependency change, out of scope for a docs
fix, and noted explicitly in the doc instead.

## What wasn't done / left open

- `apscheduler` was **not** removed from `requirements.txt` — flagged in the
  doc, not fixed, since that's a dependency change outside this task's scope.
- `debrief_engine.py` itself was **not** rebuilt — no reliable source existed
  to do so with confidence; this remains real lost functionality per the
  original review, now just honestly logged/documented instead of silently
  missing.
- Findings 1–4 (auth-gate gap, token-in-logs, `service_role` key posture) were
  **not** part of this task — a separate commit (`fc24c93`, "Close XO bot auth
  gap and token-in-logs leak") had already landed those fixes on `main` before
  this work started; verified but not touched here.

## Verification

- `python3 -m py_compile telegram-bots/xo/app.py` — clean.
- Diffs for both commits scoped to exactly their intended files (a concurrent
  session sharing this same checkout had unrelated staged changes in the
  index at commit time — caught via `git status`/`git diff --stat` after the
  first commit, undone with a local-only `git reset --soft` since it hadn't
  been pushed yet, and redone with explicit pathspec commits to avoid
  sweeping in other sessions' in-flight work).
- Both commits (`1397784`, `bee860f`) confirmed present on `origin/main` via
  `git merge-base --is-ancestor` after push.

## Mission Status

Advisory work completed and implemented per explicit task authorization (this
was a scoped fix task, not a new architecture decision) — both fixes are
low-risk (a log line, and documentation-only changes), committed and pushed.
No further escalation needed for these two findings.
