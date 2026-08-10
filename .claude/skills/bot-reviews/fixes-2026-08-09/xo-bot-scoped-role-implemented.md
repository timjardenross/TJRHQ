# XO Telegram Bot — Scoped `xo_bot` Role: Implementation Record

USS TJR — Registry USS-TJR-003, Engineering Division, Advisory + (Captain-approved) implementation authority
Date: 2026-08-10
Prior decision doc: `xo-bot-service-role-decision.md` (Option C spec'd, not implemented)
Migration: `core/infrastructure/supabase/migrations/0135_xo_bot_scoped_role.sql`

## Bottom line

**Migration applied to the live database and verified correct at the SQL/RLS level. Application code written, wired, and safe-by-default. Cutover NOT performed — held back on one missing input: `SUPABASE_JWT_SECRET`, which is not obtainable through any tool or file this session has access to.** `tg-xo.service` was not touched and still runs on `service_role`, exactly as before this pass. No behaviour change shipped to the live bot today.

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

### 4b. Standalone Python test script — written, mechanically proven, cannot complete without the real secret

`telegram-bots/xo/test_scoped_role.py` exercises the same 22 operations through the actual `scoped_supabase.build_scoped_client()` path (the real HTTP/JWT mechanism, not the SQL shortcut above). It:
- Degrades cleanly today (`SUPABASE_JWT_SECRET`/`XO_BOT_SCOPED_TOKEN` both unset) — prints a clear "not runnable yet" message and exits 3, doesn't attempt anything.
- Was run with a **deliberately wrong** `SUPABASE_JWT_SECRET` (never touching the real `.env`) as a mechanism check: all reachable operations correctly failed with clean PostgREST JWT-decode errors (`PGRST301`), not Kong apikey rejections and not Python crashes — confirming the header-split mechanism reaches PostgREST correctly end-to-end. This run also caught and fixed a real bug in the test script itself (an unguarded cleanup call after a failed upsert crashed the run instead of continuing) — fixed with a `cleanup()` helper that swallows cleanup-only failures.
- **Cannot be run to a real PASS today** — needs the actual `SUPABASE_JWT_SECRET`, which this session has no way to obtain (see §5).

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

**To complete the cutover:**
1. Get `SUPABASE_JWT_SECRET` from Supabase Dashboard → project `cjvrpjwewsrumnbdydgg` → Settings → API → JWT Settings (legacy secret).
2. Add to `telegram-bots/xo/.env`: `SUPABASE_ANON_KEY=<the anon key, already used read-only for testing this session — see platform-runtime/.env>` and `SUPABASE_JWT_SECRET=<the secret>`.
3. Run `telegram-bots/xo/.venv/bin/python3 telegram-bots/xo/test_scoped_role.py` — expect `22 passed, 0 failed` (all 22 real operations, not the 18 reachable under the deliberately-wrong-secret mechanism check).
4. If clean, `systemctl restart tg-xo.service` and watch `journalctl -u tg-xo.service -f` for a few minutes of real Captain traffic — the log line `Supabase client initialised — scoped xo_bot role` confirms the switch took effect (vs. the `service_role (...)` fallback line).
5. Only then consider removing/rotating `SUPABASE_KEY`/`SUPABASE_SERVICE_ROLE_KEY` from `telegram-bots/xo/.env` — out of scope for this pass; several other in-process modules (§1) still legitimately depend on `SUPABASE_SERVICE_ROLE_KEY` for their own (unrelated, already-narrower-risk) reasons, so that var stays regardless.

## 6. Files changed

- `core/infrastructure/supabase/migrations/0135_xo_bot_scoped_role.sql` — new. Applied live (plus one follow-up migration folded into this tracked copy for the sequence-grant fix).
- `telegram-bots/xo/scoped_supabase.py` — new. JWT minting + scoped client construction, with full mechanism rationale in its docstring.
- `telegram-bots/xo/test_scoped_role.py` — new. Ready-to-run pre-cutover verification script.
- `telegram-bots/xo/app.py` — `_get_supabase()` now prefers the scoped path, falls back to the unchanged `service_role` path when unconfigured. No other line changed.
- `telegram-bots/xo/requirements.txt` — added `pyjwt>=2.13.0` (installed into the live `.venv` already).
- `telegram-bots/xo/.env.example` — documents the new `SUPABASE_ANON_KEY`/`SUPABASE_JWT_SECRET` vars and marks `SUPABASE_KEY` as fallback-only.
- `telegram-bots/xo/.env` — **unchanged**. Still `service_role`. Not committed (gitignored, confirmed).

## Mission Status

Implementation authority exercised per Captain's explicit approval to build. **Not cut over.** Database migration is live and verified safe/correct (both at SQL level and as a zero-behaviour-change confirmation against the running bot's actual code path). Application code is written, tested for mechanism correctness, and safe to merge as-is (no behavior change until the secret is supplied). Single blocking item: `SUPABASE_JWT_SECRET`, needs Captain or whoever holds Supabase Dashboard access to retrieve and add to `.env` — then `test_scoped_role.py` plus a `journalctl` watch after restart closes this out.
