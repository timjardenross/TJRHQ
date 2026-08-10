# XO Telegram Bot — Scoped `xo_bot` Role: Implementation Record

USS TJR — Registry USS-TJR-003, Engineering Division, Advisory + (Captain-approved) implementation authority
Date: 2026-08-10
Prior decision doc: `xo-bot-service-role-decision.md` (Option C spec'd, not implemented)
Migration: `core/infrastructure/supabase/migrations/0135_xo_bot_scoped_role.sql`

## Bottom line

**Migration applied to the live database and verified correct at the SQL/RLS level. Application code written, wired, and safe-by-default. Cutover NOT performed.** `tg-xo.service` was not touched and still runs on `service_role`, exactly as before this pass. No behaviour change shipped to the live bot today.

**Update 2026-08-10, same day, later pass:** `SUPABASE_JWT_SECRET` was provisioned (in `platform-runtime/.env` and `/opt/starship-endeavour/.env`, chmod 600, gitignored) and added to `telegram-bots/xo/.env` along with `SUPABASE_ANON_KEY`, resolving the original blocker described below in §5. However, **the provided secret does not verify against this project's actual live signing key** — confirmed by attempting to verify the existing, already-working `anon` key's own signature with it (`jwt.decode(anon_key, secret, algorithms=["HS256"])` → `InvalidSignatureError`), and independently by running `test_scoped_role.py` for real, which got `PGRST301 "No suitable key or wrong key type"` on every one of the 18 reachable operations — the identical error signature produced earlier in this investigation by a *deliberately wrong* test secret (§4b). Ruled out transcription/encoding issues on this end: the value is byte-identical across all three files (SHA256-fingerprint compared without printing the value), and base64-decoded/whitespace-stripped variants were also tried and also fail to verify. **This is not something I can fix from here — the secret itself is wrong, stale, or not yet live on Supabase's side, and needs to be re-checked by whoever has Supabase Dashboard access** (Project Settings → API → JWT Settings, project `cjvrpjwewsrumnbdydgg` specifically).

**Cutover held back again, per instruction, on this second, different blocker.** `tg-xo.service` remains untouched (same `ActiveEnterTimestamp` as before this session started). One real, valuable side effect of this pass: the near-miss it exposed (see §6a) is now closed — a bad secret can no longer silently take the bot down on a future restart.

**Update 2026-08-10, third pass, same day — CUT OVER.** Captain provided a corrected `SUPABASE_JWT_SECRET` (base64-style, 88 chars, ending in `==` — a materially different shape from the 36-char value that failed §6a). Sanity-checked first, before touching anything else: verified the new secret against the existing, already-working `anon` key's own signature — `jwt.decode(anon_key, secret, algorithms=["HS256"])` now succeeds, decodes `role: anon`, `ref: cjvrpjwewsrumnbdydgg`, `iss: supabase` — confirming this is genuinely the project's live signing secret. Copied into `telegram-bots/xo/.env` (replacing the stale value), fingerprint-matched across all three files. Re-ran `test_scoped_role.py` for real: **22 passed, 0 failed** — every operation in §1's table, including the `captured_items` DELETE landmine case and the `recovery_pulses` UPDATE landmine case, confirmed working end-to-end through the actual JWT/HTTP mechanism the live bot uses (not the SQL shortcut from earlier passes). Test-generated rows (dated `2099-01-01` / tagged `xo_bot_rls_test`) were swept up afterward via an admin connection — the one test line that legitimately "failed" was the test script's own optional cleanup DELETE on `recovery_pulses`, which `xo_bot` correctly cannot do (the live bot never deletes from that table either) — relabelled from a pass/fail check to non-fatal cleanup in the script so it stops reading as a failure. `systemctl restart tg-xo.service` — clean restart, no errors, `apscheduler`/`telegram.ext.Application` started normally. Monitored `journalctl -u tg-xo.service -f` for 150 seconds post-restart: zero errors, zero permission-denied messages; no organic Captain traffic happened to land inside that specific window (the scoped-client init log line is lazy, fires on first real command), but the restart itself and the idle-polling state are both clean. Given 22/22 real operations were already verified against the exact `scoped_supabase.build_scoped_client()` code path the live process now runs, this is considered a safe, verified cutover — not a hopeful one.

## 1. Operation list — re-verified fresh, larger than the prior investigation found

The prior decision doc scoped this to **9 tables / ~10 operations**, sourced mostly from `app.py`'s direct `.table()` calls. This pass re-traced every function XO's own Supabase client is passed into — `voice_capture.py`, `telegram_bots/recovery_officer/engagement_dispatcher.py` (`get_recovery_status`, `run_dispatch_check`), `telegram_bots/wellness_officer/intelligence.py` (`get_wellness_snapshot`) — and found **13 tables**. The 4 new ones (`health_daily_logs`, `health_insights`, `wellness_reminder_log`, and the already-known `recovery_pulses` gaining UPDATE) were invisible to a grep of `app.py` alone because they're touched inside imported modules that receive the bot's client as a parameter.

| Table | Operations | Where |
|---|---|---|
| `missions` | SELECT | `_get_open_missions`, `/mission_list`, `/mission_status` |
| `recovery_confidence_today` (view) | SELECT | `/recovery_status`, `/db_status`, wellness snapshot |
| `recovery_pulses` | SELECT, INSERT, UPDATE | pulse button flow (`.upsert`), voice-capture promotion (insert+update), wellness 7-day history |
| `activity_logs` | SELECT, INSERT | `/log_activity`, wellness snapshot |
| `weight_logs` | SELECT, INSERT, UPDATE | `/log_weight` (`.upsert`), wellness snapshot |
| `intelligence_briefs` | SELECT | `/brief`, `/themes` |
| `intelligence_events` | SELECT | `/signals` |
| `intelligence_source_health` | SELECT | `/source_status` |
| `intelligence_source_registry` | SELECT | `/source_status` |
| `captured_items` | SELECT, INSERT, UPDATE, DELETE | voice capture, `/note`, capture-confirmation buttons, voice-debrief-decision buttons |
| `health_daily_logs` | SELECT | wellness snapshot |
| `health_insights` | SELECT | wellness snapshot |
| `wellness_reminder_log` | SELECT, INSERT | `/dispatch` dedup ledger |

### Everything else was traced and confirmed to use a *different*, unaffected credential

`/advise`, `/challenge`, `/learning`, `/patterns`, `/captain`, `/pending`, `/operating_picture`, `/daily`, `/debrief_weekly`, and the mission-governance writes (`/mission_create`, `/captain_approve`, `/captain_reject`, `/mission_submit`, `/handoff_engineering`) do **not** go through `SUPABASE_KEY` at all:
- Mission-governance writes go through the LCARS Portal HTTP API (`X-Bot-Secret`), never Supabase directly.
- `/advise`/`/challenge` run `core/advisory/cli.py` as a subprocess; traced its full import tree (`service.py`, `lessons.py`, `metrics.py`, … `tools/supabase/*.py`) — none reads `SUPABASE_KEY`.
- `/learning`/`/captain`/`/pending` (`core/knowledge/outcome_capture.py` / `learning_narrative.py`), `/patterns` (`core/platform/operational_pattern_library.py`), `/operating_picture` (`core/intelligence/operating_picture.py`), `/daily`/`/debrief_weekly` (`intelligence/captains_brief.py`) — all confirmed via direct source read to use `SUPABASE_SERVICE_ROLE_KEY` (via `core/health/supabase_client.py` or `tools/supabase/client.py::CommanderSupabaseClient`), a **separate** env var already present in `telegram-bots/xo/.env` and untouched by this work.
- `core/platform/heartbeat.py` and `core/platform/event_bus.py` (fired from many of the write paths above as best-effort, exception-swallowed side calls) also read `SUPABASE_SERVICE_ROLE_KEY` directly, not `SUPABASE_KEY`.

A repo-wide grep for `"SUPABASE_KEY"` confirmed only two live-runtime files read that exact var: `telegram-bots/xo/app.py` and `telegram-bots/recovery_officer/engagement_dispatcher.py` (whose own `_get_supabase_client()` fallback is never hit from XO — XO always passes its own client explicitly).

`debrief_engine.py` — imported defensively (`try/except ImportError`) by `app.py` for `/debrief_close` and the voice-debrief-decision callback — **does not exist on disk anywhere in this repo** (confirmed via `find` + `git log --all`). Every code path referencing it currently degrades to its `ImportError` branch. Not included in the operation list; if it's added in future, its table footprint needs re-auditing against the `xo_bot` role's grants before it can rely on this credential.

## 2. Migration — applied live, verified correct

`core/infrastructure/supabase/migrations/0135_xo_bot_scoped_role.sql`: creates `xo_bot` (`nologin`, granted to `authenticator`, mirroring `0015_telegram_engineer_ro.sql`'s pattern exactly), with per-table GRANTs + RLS policies scoped to precisely the operation list above. Applied via `apply_migration` (project `cjvrpjwewsrumnbdydgg`) plus one follow-up migration for a bug found during testing (§4).

Two known landmines closed (neither exists for `authenticated` today — confirmed live via `pg_policies` before writing the migration):
- **`captured_items` DELETE** — no `authenticated` policy exists live, but `handle_voice_debrief_decision_callback` deletes a row on the "debrief" decision path. `xo_bot` gets an explicit DELETE policy. **Verified working** (§4).
- **`recovery_pulses` UPDATE** — no `authenticated` policy exists live (migration `0110`'s own comment says so explicitly), but `voice_capture.py::promote_recovery_pulse()` UPDATEs an existing pulse row's notes, and the button-flow `.upsert()` is INSERT-ON-CONFLICT-DO-UPDATE, needing both. `xo_bot` gets an explicit UPDATE policy. **Verified working** (§4).

## 3. Mechanism: the header-override question the prior doc left open — now resolved, negatively then positively

The prior doc flagged as unverified whether `supabase-py`'s `ClientOptions(headers=...)` lets `Authorization` differ from `apikey` (needed because Kong requires a *real* project key in `apikey` while PostgREST needs the *scoped role's* JWT in `Authorization` — two different values, same request).

**Tested directly against `supabase==2.3.4`'s actual source and confirmed empirically:**
- The **public API does not work**. `SyncClient.__init__` does `options.headers.update(self._get_auth_headers())`, and the lazy `.postgrest` property re-applies a fixed `self._auth_token` again on first access — both always derive `Authorization` *and* `apiKey` from the single `supabase_key` argument to `create_client()`, silently discarding anything the caller pre-set in `ClientOptions(headers=...)`. Verified: a deliberately-wrong `Authorization` passed this way was overwritten with the real key and the query still succeeded — proving the override never took effect.
- **What does work**: constructing the client normally with the anon key (`create_client(url, anon_key)`, so Kong's apikey check passes), then patching the client's private `_auth_token` attribute *before* the first `.table()` call. Verified: a deliberately-wrong token patched this way reached PostgREST (not rejected by Kong) and was rejected there with a JWT-format error — proving `apiKey` stayed valid while `Authorization` carried the patched value, independently.

This is implemented in `telegram-bots/xo/scoped_supabase.py::build_scoped_client()`. It is a private-attribute dependency, pinned to `supabase==2.3.4` (already pinned in `requirements.txt`); re-verify against `SyncClient` source if that pin ever moves. Keeps every existing `.table(...).select()/.insert()/.update()/.delete().execute()` call site in `app.py`/`voice_capture.py`/`engagement_dispatcher.py`/`wellness_officer/intelligence.py` completely unchanged — only client *construction* changed.

## 4. Testing performed

### 4a. SQL-level grant/policy verification — comprehensive, all 22 operations pass

Ran every real operation (`SET LOCAL ROLE xo_bot` inside a transaction, `ROLLBACK` at the end — confirmed zero rows leaked into any live table afterward) directly against Postgres, decoupled from the JWT-secret blocker entirely. This is the layer that actually determines whether the role/policies are correct.

**First pass found two real bugs**, both fixed before re-testing:
1. `activity_logs INSERT` and `weight_logs UPSERT` both failed with `permission denied for sequence activity_logs_id_seq` / `weight_logs_id_seq` — their `id` columns are `bigint`/`nextval()`-backed, and `GRANT INSERT` on the table alone doesn't cover the sequence. Fixed with a follow-up migration (`grant usage, select on ... to xo_bot`) and folded into `0135`'s tracked copy.
2. Two of my own test fixtures used invalid enum values (`recovery_pulses.pulse_type`, `wellness_reminder_log.pulse_window` both have `CHECK` constraints) — not a grant bug, just bad test data; corrected.

**Second pass: all 22 operations passed**, including both landmine cases:
- `captured_items DELETE (landmine case)` → `rows deleted: 1` — confirmed working.
- `recovery_pulses UPDATE` → `rows updated: 1` — confirmed working.
- Confirmed separately: `pg_has_role('authenticator', 'xo_bot', 'member')` = `true` — the exact mechanism PostgREST needs to `SET ROLE` into `xo_bot` given a valid JWT role claim is live and correct.

Post-test check confirmed zero residual rows in any of the five tables touched (`recovery_pulses`, `activity_logs`, `weight_logs`, `captured_items`, `wellness_reminder_log`) — the transaction rollback left no trace.

### 4b. Standalone Python test script — written, mechanically proven, run for real (fails — see §6a)

`telegram-bots/xo/test_scoped_role.py` exercises the same 22 operations through the actual `scoped_supabase.build_scoped_client()` path (the real HTTP/JWT mechanism, not the SQL shortcut above). It:
- Degrades cleanly with nothing configured — prints a clear "not runnable yet" message and exits 3, doesn't attempt anything.
- Was first run with a **deliberately wrong** `SUPABASE_JWT_SECRET` (never touching the real `.env`) as a mechanism check: all reachable operations correctly failed with clean PostgREST JWT-decode errors (`PGRST301`), not Kong apikey rejections and not Python crashes — confirming the header-split mechanism reaches PostgREST correctly end-to-end. This run also caught and fixed a real bug in the test script itself (an unguarded cleanup call after a failed upsert crashed the run instead of continuing) — fixed with a `cleanup()` helper that swallows cleanup-only failures.
- **Was then run for real**, once `SUPABASE_JWT_SECRET`/`SUPABASE_ANON_KEY` were added to `telegram-bots/xo/.env` — got the exact same `PGRST301` error on all 18 reachable operations as the deliberately-wrong-secret run above. See §6a: the provided secret itself doesn't verify against this project's live signing key. 0/22 real operations confirmed working with the real token; cutover not performed.

### 4c. Zero-behaviour-change confirmation

With the live, untouched `.env` (no `SUPABASE_ANON_KEY`/`SUPABASE_JWT_SECRET` set), imported `telegram_bots.xo.app` directly and called `_get_supabase()`: it correctly falls through the new scoping branch (logs the "not configured" warning) and falls back to the exact original `service_role` client construction, which then executed a real `missions` SELECT successfully. **The code changes shipped in this pass make zero behavioural difference to the live bot today.**

### 4d. Syntax/compile checks

`python3 -m py_compile` clean on `app.py`, `scoped_supabase.py`, `test_scoped_role.py`, `voice_capture.py`, `pulse_time.py`.

## 5. Why cutover was held back — the one missing input

Mirroring migration `0015`'s mechanism requires `SUPABASE_JWT_SECRET` (the project's legacy JWT signing secret, from Supabase Dashboard → Project Settings → API → JWT Settings) to mint a JWT carrying `role: xo_bot`. This session checked every avenue available to it and found the secret nowhere:
- Not in `telegram-bots/xo/.env`, `platform-runtime/.env`, or any other `.env*` file on the host (grepped all of them).
- No Supabase Management API access token / `SUPABASE_ACCESS_TOKEN` on the host, and no `supabase` CLI installed — no way to call the Management API to fetch it.
- Not exposed via any available Supabase MCP tool (`get_project`, `get_publishable_keys`, etc. — none return the JWT secret; `get_publishable_keys` only returns the anon/publishable key, which was retrievable and used for testing throughout).
- Not exposed as a readable Postgres GUC (`current_setting('pgrst.jwt_secret', true)` → `null`, as expected on Supabase Cloud).

This is a genuine external-input blocker, not a judgment call — per the Chief Engineer escalation discipline, the responsible move is to build and verify everything possible up to that point and stop, not substitute a different, larger-scope mechanism (e.g. switching the bot to direct Postgres/password auth instead of PostgREST+JWT) that wasn't what was authorized.

**Original blocker resolved 2026-08-10 (later same day)** — see §6a for what happened next and why cutover is still held back.

## 6a. Second pass: secret provisioned, but doesn't verify — a real near-miss caught and closed

`SUPABASE_JWT_SECRET` was added to `platform-runtime/.env` and `/opt/starship-endeavour/.env` (chmod 600, gitignored) and copied into `telegram-bots/xo/.env` alongside `SUPABASE_ANON_KEY` (file-to-file copy via `grep`/redirect — the value itself was never printed to any transcript or log at any point in this process; fingerprint-compared via SHA256 across all three files to confirm no transcription drift, also without printing the value).

**Running the real verification (`test_scoped_role.py` against the real secret) failed identically to the earlier deliberately-wrong-secret mechanism check**: `PGRST301 "No suitable key or wrong key type"` on all 18 reachable operations. Independently confirmed the secret itself doesn't match this project's actual live signing key by attempting to *verify* (not mint) the existing, already-working `SUPABASE_ANON_KEY`'s own signature with it — `jwt.decode(anon_key, secret, algorithms=["HS256"])` → `InvalidSignatureError`. Ruled out an encoding/transcription problem on this end: tried the raw value, base64-decoded, and whitespace-stripped variants against the same anon-key-verification test — all fail identically. **The value provisioned is not the correct legacy JWT secret for project `cjvrpjwewsrumnbdydgg`** — wrong value, stale/rotated-but-not-live, or pulled from the wrong place. Not fixable from this session; needs re-verification by whoever has Supabase Dashboard access.

**A real near-miss this exposed, now closed:** before this pass, `build_scoped_client()` returned a client as soon as `SUPABASE_ANON_KEY` + a token were merely *present* in the environment — it never confirmed the token actually verified. Had `tg-xo.service` been restarted with the (wrong) secret in place, every Supabase-backed command handler would have started failing with `PGRST301` on every call — a total outage of the bot's data layer for the Captain, discovered only by the failures themselves rather than caught ahead of time. Fixed in this pass: `build_scoped_client()` now runs one cheap live `missions` query before returning the scoped client; any failure (bad secret, bad token, transient network issue at startup) logs a loud error and returns `None`, and `_get_supabase()`'s existing fallback-to-`service_role` path takes over exactly as it does when scoping isn't configured at all. **This means it is now safe to restart `tg-xo.service` even with the current (non-verifying) secret in `.env` — it will fall back to `service_role` automatically and keep working, not go down.** Confirmed by re-running `_get_supabase()` against the live (broken-secret) `.env`: logs the new error line, falls back, and a real `missions` query succeeds.

`tg-xo.service` was **not** restarted in this pass regardless — the task was to cut over only once every operation is confirmed working with the real token, and 0/22 are. Left exactly as found (`ActiveEnterTimestamp` unchanged from before this session).

**To complete the cutover (updated):**
1. Whoever holds Supabase Dashboard access: re-fetch `SUPABASE_JWT_SECRET` from Project Settings → API → JWT Settings for project `cjvrpjwewsrumnbdydgg` specifically, and confirm it's the *currently live* one (not a value queued for a rotation that hasn't propagated). Update `platform-runtime/.env` / `/opt/starship-endeavour/.env` / `telegram-bots/xo/.env` with the corrected value (same file locations already wired).
2. Run `telegram-bots/xo/.venv/bin/python3 telegram-bots/xo/test_scoped_role.py` — expect `22 passed, 0 failed`.
3. If clean, `systemctl restart tg-xo.service` and watch `journalctl -u tg-xo.service -f` for a few minutes of real Captain traffic — the log line `Supabase client initialised — scoped xo_bot role` confirms the switch took effect (vs. the `service_role (...)` fallback line, which is what a restart would show right now with the current secret).
4. Only then consider removing/rotating `SUPABASE_KEY`/`SUPABASE_SERVICE_ROLE_KEY` from `telegram-bots/xo/.env` — out of scope for this pass; several other in-process modules (§1) still legitimately depend on `SUPABASE_SERVICE_ROLE_KEY` for their own (unrelated, already-narrower-risk) reasons, so that var stays regardless.

## 7. Files changed

- `core/infrastructure/supabase/migrations/0135_xo_bot_scoped_role.sql` — new. Applied live (plus one follow-up migration folded into this tracked copy for the sequence-grant fix).
- `telegram-bots/xo/scoped_supabase.py` — new. JWT minting + scoped client construction, with full mechanism rationale in its docstring.
- `telegram-bots/xo/test_scoped_role.py` — new. Pre-cutover verification script; ran clean at 22/22 in the final pass. Relabelled the `recovery_pulses` cleanup-only DELETE from a pass/fail check to non-fatal cleanup (it's not a real bot operation and `xo_bot` correctly has no DELETE grant there).
- `telegram-bots/xo/app.py` — `_get_supabase()` now prefers the scoped path, falls back to `service_role` when unconfigured or unverifiable. No other line changed.
- `telegram-bots/xo/requirements.txt` — added `pyjwt>=2.13.0` (installed into the live `.venv` already).
- `telegram-bots/xo/.env.example` — documents the new `SUPABASE_ANON_KEY`/`SUPABASE_JWT_SECRET` vars and marks `SUPABASE_KEY` as fallback-only.
- `telegram-bots/xo/.env` — now has a verified-working `SUPABASE_ANON_KEY` + `SUPABASE_JWT_SECRET`. `SUPABASE_KEY`/`SUPABASE_SERVICE_ROLE_KEY` (service_role) left in place, unchanged, as the fallback + for other in-process modules that still use `SUPABASE_SERVICE_ROLE_KEY` directly. Not committed (gitignored, confirmed).

## Mission Status

Implementation authority exercised per Captain's explicit approval to build. **CUT OVER — 2026-08-10, third pass.** Two earlier holds (§ "Bottom line" updates) were correct calls at the time: pass one had no secret at all, pass two had a secret that demonstrably didn't verify. Pass three's secret verified cleanly against the known-good anon key before anything else was touched, then 22/22 real operations passed against the actual JWT/HTTP client-construction path the live bot uses (not a SQL shortcut), including both landmine cases (`captured_items` DELETE, `recovery_pulses` UPDATE). `tg-xo.service` was restarted cleanly — no errors, no crashes, normal startup sequence (`apscheduler` + `telegram.ext.Application` both started) — and monitored via `journalctl -u tg-xo.service -f` for 150 seconds post-restart with zero errors or permission-denied messages. `xo_bot`'s scoped-client construction also now self-verifies with a live query before ever being handed to the bot (added in pass two, after the near-miss it would have prevented), so even an undetected future secret problem degrades to `service_role` instead of an outage. `SUPABASE_KEY`/`SUPABASE_SERVICE_ROLE_KEY` remain in `telegram-bots/xo/.env` as the (now believed inactive, code-path-wise) fallback and for the other in-process modules (§1) that legitimately still use `SUPABASE_SERVICE_ROLE_KEY` directly — untouched, out of scope. Recommended follow-up (not done here, no restart needed): confirm on the Captain's next real interaction that the log shows `Supabase client initialised — scoped xo_bot role` rather than the `service_role (...)` fallback line, as a final live-traffic confirmation beyond the pre-restart testing.
