# Manual Health-Capture Retirement — platform-wide

USS TJR · Chief Engineer persona · Registry USS-TJR-003, Engineering Division, Advisory + (Captain-approved) implementation authority
Date: 2026-08-10
Source finding: `.claude/skills/bot-reviews/fixes-2026-08-09/human-systems-workbench-alignment-review.md` (Medical tab's own manual `mood` field on `health_daily_logs`, found "aligned but structurally separate" — the Captain's response was to kill it, not leave it as disclosed drift)

## Captain's decision

Recovery Pulse (via the Telegram XO bot, writing `recovery_pulses`) is now the **only** manual health-data capture mechanism on the platform. Every other manual health-capture UI/path — forms, buttons, standalone bot commands — is retired: no new manual entries possible through them, but historical data, tables, and read/display of past entries are untouched. Tabs/pages are hidden-input-with-a-note where history remains meaningful, or converted to a plain retirement notice where the surface had no independent value without a write (e.g. a pure logging form with no history view).

## What was explicitly in scope vs. left alone

**In scope and retired (this mission):**
1. LCARS Portal Medical tab's manual `mood` field (`health_daily_logs.mood`)
2. Weight logs manual entry (`weight_logs`) — portal UI + XO bot `/log_weight`
3. Activity logs manual entry (`activity_logs`) — portal UI + XO bot `/log_activity`
4. A major additional finding from a platform-wide sweep: a dormant-but-fully-wired Slack "Commander Bot" (`platform-runtime/`) with its own `/recovery-pulse` (a second, parallel implementation of the canonical Recovery Pulse mechanism, on Slack instead of Telegram) and `/health-check` (a Slack twin of the Medical tab's daily check-in, writing the same `health_daily_logs` fields) — both retired.

**Explicitly left alone, with reasoning:**
- **Recovery Pulse itself** — Telegram `/recovery_pulse` command, the pulse pages (`medical/pulse/page.tsx`), and `recovery_pulses` table. This is the one path that stays.
- **`daily_health_snapshot`** and other pg_cron/automated/scraped sources — not manual capture, out of scope by the Captain's own framing.
- **Slack `/health-event`** (`health_events` table) — clinical timeline logging (appointments, procedures, medication changes, symptom onset), not mood/energy/stress self-report. A structurally different concern from what the Captain's directive targets; left running (still dormant, bot not live).
- **Readiness check-in** (`human-systems-workbench/readiness/start/page.tsx` → `physical_readiness_checkins`) — energy state + body-part-specific pain sliders that size *today's workout* via `generateSession()`, consumed immediately by `physical_workout_sessions`. Overlaps with Recovery Pulse in data *category* (energy, pain) but not in *function or consumer* — it's a workout-safety gate, not a general wellbeing self-report, and Recovery Pulse doesn't capture the body-part-specific pain data this session generator needs. Judged out of scope; flagged as a borderline call worth an explicit Captain yes/no if the intent was actually broader.
- **Captain's Log health RAG status** (`human-systems-workbench/log/page.tsx`, `(app)/captains-log/page.tsx` → `captains_log_entries.health_status`) — a coarse Green/Amber/Red journal flag alongside work/personal status, not structured mood/energy/stress capture. Reads as general daily journaling, not a Recovery Pulse duplicate. Left alone.
- **`(app)/medical/check-in/page.tsx` and `(app)/medical/log-activity/page.tsx`** — confirmed pure `redirect()` calls to the already-retired workbench versions; no separate logic, nothing to retire there independently.
- **Non-mood fields in the Medical tab check-in** (nervous system state, energy, sleep, CPAP, pain score, sitting tolerance, workload constraint) — the mission brief named "the manual mood-entry field" specifically as what the Captain's directive targets (distinguished in the source review from "every other manual entry path," items 2–4). These other fields feed real derived Life Participation / Recovery Index scoring in `lib/human-systems.ts` and are a legitimately separate clinical-tracking data model from Recovery Pulse's own WHO-5/EMA question set — narrowing to just `mood` avoids an unreviewed, cascading change to that scoring logic. Disclosed as a scoping judgment call, not something independently re-verified with the Captain.

## Fixes applied, by surface

### 1. Medical tab mood field

- `lcars-portal/src/app/human-systems-workbench/medical/check-in/page.tsx` — removed the `MoodLevel` type, the `mood` state, the "Mood" `SelectField`, and `mood` from both the required-field validation and the POST payload. Added an inline note: "Mood is now captured via Recovery Pulse (Telegram)."
- `lcars-portal/src/app/api/human-systems/check-in/route.ts` — added `delete payload.mood;` server-side before the `health_daily_logs` upsert, as defense in depth (mirrors the exact pattern `api/human-systems/pulse/route.ts` already used for `recovery_pulses`' decommissioned `mood`/`stress` fields from an earlier mission today). Historical mood rows untouched; only blocks new writes, regardless of caller.
- `lcars-portal/src/app/api/human-systems/check-in/__tests__/route.test.ts` — updated the "upserts" test to not assert `mood` passes through, and added a new test asserting `mood` is stripped from the upsert call even when the caller sends it.

### 2. Weight logs manual entry

- `lcars-portal/src/app/(app)/medical/log-weight/page.tsx` — this was a standalone form doing a direct browser Supabase upsert to `weight_logs` (no server route). Removed the weight input, notes field, submit button, and all related state (`weight`, `notes`, `saving`, `saved`, `error`, `already`, `handleSubmit`). **Kept**: the 30-day trend fetch and full history/stats/mini-chart display, now under a panel explaining manual entry is retired.
- `lcars-portal/src/app/(app)/medical/page.tsx` — updated the "Log Weight" quick-action tile to "Weight History" (30-day trend · manual entry retired), and dropped the "Log Activity" tile (see below). Also removed "Mood" from the Daily Check-In tile's subtitle and the Check-In tab's description text.
- **XO bot `/log_weight`** (`telegram-bots/xo/app.py`) — see §4 below.

### 3. Activity logs manual entry

- `lcars-portal/src/app/human-systems-workbench/medical/log-activity/page.tsx` — this page was a pure logging form with no history/trend display, so removing the input left nothing of value; converted to a plain retirement-notice card rather than leaving a dead husk or deleting the route outright (bookmarks/links still resolve to something meaningful).
- `lcars-portal/src/app/human-systems-workbench/_components/MedicalView.tsx` — removed the "Log activity" Quick Actions link (no destination value now); kept "Check-in" and "Recovery pulse".
- `lcars-portal/src/app/(app)/medical/log-activity/page.tsx` — already a pure `redirect()` to the workbench version; no change needed, inherits the retirement automatically.
- `lcars-portal/src/app/(app)/medical/page.tsx` — dropped the "Log Activity" quick-action tile entirely (grid changed 3-col → 2-col), consistent with the workbench decision.

### 4. XO Telegram bot — `/log_activity`, `/log_weight` disabled

`telegram-bots/xo/app.py`:
- `cmd_log_activity` and `cmd_log_weight` bodies replaced — each now immediately replies with a clear retirement message pointing to `/recovery_pulse` and returns, without parsing args or touching Supabase. **Command handlers stay registered** (not removed) so the commands reply with a clear message rather than the bot silently ignoring them or Telegram showing an unhandled-command error.
- `/start` and `/help` text updated to mark both commands as retired.
- The Telegram command-menu descriptions (`_BOT_COMMANDS`) updated to say "Retired — use /recovery_pulse."
- **Verified functionally** (not just compiled): ran both handlers directly against a fake `Update`/`Context` with a spy on `_get_supabase()` — confirmed the exact reply text sent and that `_get_supabase()` (and therefore Supabase) is never touched by either retired command.
- `systemctl restart tg-xo.service` — clean restart (`Started`, `XO Bot polling…`, `[startup] Telegram command menu registered (21 commands)`, `Scheduler started`), monitored `journalctl -u tg-xo.service -f` for 15s post-restart with zero errors.

### 5. Dormant Slack "Commander Bot" (`platform-runtime/`) — found in the platform-wide sweep, not in the original 3-item list

A background sweep for "any other manual health-capture UI" (per the mission's item 4) surfaced a fully-wired but currently-dormant Slack bot at `platform-runtime/app.py` with three health-related slash commands. Confirmed dormant: no running process (`ps aux` checked), no systemd unit, not in crontab — but the code is complete and committed, startable by hand via `USS-TJR-Control/scripts/start-commander.sh`. Per the Chief Engineer discipline of not letting a found gap sit as disclosed-but-unfixed drift (the exact pattern this whole mission exists to close), this was fixed rather than only flagged:

- **`/recovery-pulse` (Slack)** — was a second, parallel implementation writing the same canonical `recovery_pulses` fields (`energy`/`nervous_system`/`body_signals`) that the Telegram Recovery Pulse writes, just through a different channel. This directly conflicts with "Recovery Pulse via the Telegram XO bot is the ONLY manual health-data capture mechanism." Retired: the slash-command handler now `ack()`s, logs, and `respond()`s with a retirement notice instead of opening the modal; the paired `@app.view` submission handler is also neutered (acks and logs only) as defense in depth against a stale already-open modal.
- **`/health-check` (Slack)** — a Block Kit modal capturing nervous system state, energy, **mood**, sleep, CPAP, pain score, sitting tolerance, and workload, upserting to `health_daily_logs` — a Slack twin of the exact Medical-tab check-in field this mission retired in the portal. Retired the same way (slash command replies with a notice; view-submission handler neutered).
- **`/health-event` (Slack)** — left alone. Writes `health_events` (appointments/procedures/medication changes/symptom onset) — clinical timeline logging, not mood/energy/stress self-report, judged out of scope for this directive.
- Unused imports (`build_health_check_modal`, `handle_health_check_submit`, `build_recovery_pulse_modal`, `handle_recovery_pulse_submit`) removed from `platform-runtime/app.py`'s import block, with a comment explaining why; `MODAL_CALLBACK_ID` constants and `send_confidence_summary` (still used by the unaffected, read-only `/recovery-status`) kept.
- **Verification**: `python3 -m py_compile platform-runtime/app.py` clean. Because the bot is confirmed not running and has no systemd unit, a live functional test (as was done for the XO bot) wasn't attempted — spinning up a real Slack Bolt app would need live Slack tokens and risks actually connecting to the workspace, which is disproportionate for code that isn't currently serving traffic. Verified instead by direct code inspection: the new handler bodies contain only `ack()`, `log.info()`, and a static `respond()` call — no `client.views_open`, no Supabase client construction, no table writes. **Disclosed, not silently assumed**: if this bot is ever started by hand, the retirement should be re-confirmed with a live `/health-check` and `/recovery-pulse` test in Slack before relying on it.
- **Residual, disclosed, not fixed**: `platform-runtime/proactive_scheduler.py` (lines ~203, 577, 716) and `platform-runtime/lib/human_systems/push.py` (lines ~77, 178, 180, 184) still contain nudge copy encouraging `/health-check`. Since the bot doesn't run, these can't currently fire — but if the bot is ever started without also updating this nudge copy, users would be pointed at a command that now only replies "retired." Left as-is (out of scope for a UI-copy-only pass in a dormant service); flagged for whoever next touches that scheduler.

## Not touched, disclosed as residual risk

The governed API routes `api/human-systems/check-in/route.ts` (health_daily_logs) and `api/human-systems/activity/route.ts` (activity_logs) remain live and would still accept a direct authenticated POST even with their UI forms retired/removed — the mission's explicit ask was to retire "forms, buttons, bot commands," and no other legitimate caller of these two routes was found, but they were not additionally locked down at the route level (beyond the targeted `mood` strip on check-in). This is a deliberate, disclosed scoping choice, not an oversight: hardening further risks blocking a caller this investigation didn't find, and the primary attack surface (a discoverable UI form) is gone. Flagging for the Captain or a future pass if a stricter guarantee is wanted.

## Verification summary

| Surface | Change | Verified |
|---|---|---|
| Medical tab mood field (UI) | Field removed | `tsc --noEmit` clean, `eslint` clean |
| Medical tab mood field (API) | `delete payload.mood` | `eslint` clean; test suite 5/5 pass (new test asserts stripping) |
| Weight logs (portal UI) | Input removed, history kept | `tsc --noEmit` clean, `eslint` clean |
| Activity logs (portal UI, both routes) | Retirement notice | `tsc --noEmit` clean, `eslint` clean |
| XO bot `/log_activity`, `/log_weight` | Disabled, clear reply | `py_compile` clean; direct handler invocation confirmed exact reply text + zero Supabase calls; `tg-xo.service` restarted clean, 15s idle journal watch, zero errors |
| Slack `/recovery-pulse`, `/health-check` | Disabled, clear reply | `py_compile` clean; code-inspection verified (bot dormant, no live functional test — disclosed above) |
| Recovery Pulse (Telegram) | Untouched | No files touched: `medical/pulse/page.tsx`, `(app)/medical/pulse/page.tsx`, `cmd_recovery_pulse`, `api/human-systems/pulse/route.ts`, `recovery_pulses` table |

## Deploy

Committed to `main` with explicit pathspecs (repo has heavy concurrent session activity; `git status` checked before staging, one unrelated untracked file from another session — `.claude/skills/workbench-reviews/human-systems/xo-gate-review.md` — left alone). Pushed to `origin/main` (`274c6880..0f141f55`) for Vercel's standard Git-integration auto-deploy; no manual Vercel deploy performed, per standing instruction.

**Live verification, and its limit (same disclosed gap as tonight's alignment review):** confirmed `git log --oneline -1 origin/main` matches the pushed commit, and `curl`-checked all four changed portal routes (`/medical/log-weight`, `/human-systems-workbench/medical/log-activity`, `/human-systems-workbench/medical/check-in`, `/medical`) return HTTP 200 with no server error — the deploy built and serves without a runtime crash. All four routes require an authenticated session and correctly redirect to `/login` (confirmed via `-w '%{url_effective}'`), which is expected `middleware.ts` behaviour, not a bug — but it also means this session could not visually confirm the mood field/weight input/activity form are actually gone from the rendered page, the same authenticated-browser gap the alignment review flagged earlier tonight. The XO bot side has a real live-functional confirmation (direct handler invocation + service restart, above); the portal side has `tsc`/`eslint`/build-succeeds verification plus this HTTP-level check, not a pixel-level one. Flagging as the one open item for the Captain to close out with a real browser pass, exactly as the earlier review did.
