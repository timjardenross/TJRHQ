# Knowledge Record — USS-TJR-MSN-0371 (Streams 2-6)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0371 |
| Title | Retire .env as a production secret source — Streams 2-6 |
| Date | 2026-09-12 |
| Follows | Stream 0 (audit), Stream 1 (pilot + runbook) |
| Status | Streams 2-6 complete against the real (38-service) inventory. |

## Stream 0 follow-up: gap list fully closed

Completed the audit files Stream 0 flagged as not-yet-checked
(`telegram-bots/capacitybot/.env`, repo-root `.env`,
`/etc/self-improvement/dashboard.env`) — no new real-secret gaps found
beyond the original 28 keys (only `SUPABASE_KEY` repeated). Pushed to
Infisical prod with explicit go-ahead:
- 6 real secrets (key names only, no values below): `GITHUB_TOKEN`, `GLM_API_KEY`, `BACKEND_API_KEY`,
  `LCARS_API_SECRET`, `SUPABASE_KEY`, `COMMAND_CENTRE_API`.  # pragma: allowlist secret
- 20 of the 21 plain-config keys (`REVS_ADMIN_USER_IDS` was empty on
  disk — Infisical's bulk `--file` mode rejects empty values, nothing to
  migrate there).
- `VERCEL_OIDC_TOKEN` stayed out per the brief's original scope; confirmed
  unused by lcars-portal's own source (`grep` came back empty) so nothing
  was lost dropping it from that service's runtime env.

**Real secret exposure, flagging clearly:** this CLI's `secrets set --file`
and one ad hoc `printenv` test both printed full secret values into this
session's own output — `MISTRAL_API_KEY` once, then all 6 real-secret
values in the bulk push's result table. No quiet/values-hidden mode was
found for this command. **Recommend rotating these 7 values** once this
migration is confirmed stable, since session transcripts persist.

## New architectural finding: bots need per-service secret scoping

`tg-xo`, `tg-revs`, `tg-capacitybot` each need their own distinct
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` — confirmed via SHA-256 hash
comparison (not raw values) that all three differ. Infisical's "prod"
environment is one flat namespace, one value per key — the standard
wrapper would have silently handed all three bots the same (XO's) token,
breaking REVS and capacitybot outright (Telegram API 409s on shared-token
polling, not a subtle degradation). Confirmed with the Captain before
proceeding.

**Fix:** created Infisical folders `/bots/xo`, `/bots/revs`,
`/bots/capacitybot`; moved each bot's divergent keys into its own folder
(deleted the ambiguous root-level copy, which had been XO's value).
Wrote `run-with-infisical-bot.sh` — fetches root (shared) secrets via
`infisical export`, then the bot's own folder second (override), sourced
in order; this CLI has no exposed "secret import" feature to do the merge
server-side, so the merge happens in the script instead. Verified via
hash comparison that each bot gets its own correct token through the new
wrapper before touching any live unit.

## Stream 2 — Bots (done)

`tg-xo.service`, `tg-revs.service`, `tg-capacitybot.service` — all cut
over to `run-with-infisical-bot.sh`, all restarted, all confirmed active
with no missing-var errors. Repo housekeeping: `deploy/xo-bot.service` and
`deploy/revs-bot.service` renamed to match their real live unit names
(`tg-xo.service`/`tg-revs.service` — the stale names were the Stream 0
finding that those two "didn't exist"); `deploy/tg-capacitybot.service`
created fresh (no repo copy existed before).

Noted, not fixed (pre-existing, unrelated to this migration): REVS bot's
own httpx client logs the full Telegram API request URL at INFO level,
which embeds the bot token in the URL path — visible in `journalctl`.
Separate finding, not this mission's scope.

## Stream 3 — Core backend (done)

`model-router.service`, `context-service.service`, `lcars-portal.service`
cut over to the plain `run-with-infisical.sh` wrapper (no per-instance
divergent-value problem, unlike the bots). All three restarted, all
health-checked directly (HTTP 200/307 as expected, no errors in logs).
`model-router.service`'s repo/live drift (Stream 0 finding — repo said
`slack-bot/.env`, live said `platform-runtime/.env`) reconciled in the
same edit.

`lcars-portal.service` caveat, not fully resolved: this only covers
server-side runtime env. `NEXT_PUBLIC_*` values are baked into the client
bundle at `next build` time, not read by `next start` at runtime — a
future rebuild still needs its own env source for those (currently still
`.env.local` at build time, unaddressed by this migration). Documented
in the unit file's own comment.

## Stream 4 — Schedulers/cron/oneshots (done, one exception)

Cut over and individually verified (each manually triggered once,
`systemctl show -p Result` = `success`, no error/traceback/missing-var
lines in the fresh journal output): `mission-registry-sync`,
`deadmans-switch`, `capture-enrichment`, `engineering-batch-sync`,
`health-osint-collection` (3 sequential `ExecStart=` lines, all three
wrapped), `self-improvement-dashboard` (active long-running service,
HTTP 200 confirmed post-restart).

`starfleet-slack-bot.service` migrated (repo + live config) but
deliberately not restarted — it's the already-retired bot referenced in
`mission-registry-sync.service`'s own comment (disabled since 2026-07-07,
MSN-0337); migrated for consistency, not resurrected.

**vm-processing / vm-processing-retry / vm-processing-healthcheck**
(Stream 0's real blocker — `User=claude`, denied on the root-only auth
file): resolved with the Captain's confirmed choice — created
`infisical-readers` group, `chown root:infisical-readers` +
`chmod 640` on `.infisical-auth.env`, added `claude` to the group.
Verified directly (`sudo -u claude test -r ...` → readable) before
touching any unit. `vm-processing-retry` and `vm-processing-healthcheck`
migrated and manually triggered — both `success`, no errors.
`vm-processing.service` itself was mid-run on the *old* config when this
stream reached it (a legitimate long-running batch, not a hang caused by
this migration) — config was deployed but the in-flight run was not
interrupted; **its next natural timer fire is the first real verification
of this specific unit's cutover, not yet observed this session.**

## Stream 5 — Docker/webhook services (no-op, correctly)

Checked `docker-compose.watchlist.yml` directly: zero `env_file:` or
secret-bearing `environment:` entries — changedetection.io and Uptime
Kuma configure themselves via their own UI after first boot, not via
this platform's secrets at all. The two webhook receiver services
(`watchlist-changedetection-webhook`, `watchlist-uptime-kuma-webhook`)
have no `EnvironmentFile=` at all. The mission brief's elaborate
`infisical export --format=dotenv` guidance for this stream turned out
to be unnecessary — there was nothing here to migrate. Confirmed rather
than assumed.

## Stream 6 — Retirement (done)

1. **Repo-wide check:** `grep -n "^EnvironmentFile=" deploy/*.service` →
   zero matches. Every previously-active line is now commented
   (rollback path) or never existed. `intelligence-scheduler.service`'s
   2026-09-05 fallback layering (kept the old `EnvironmentFile=` active
   *alongside* the wrapper, as a safety net for keys not yet in
   Infisical) was fully retired in this pass now that Stream 0's gap-push
   closed that gap — restarted and confirmed clean.
2. **`.env` files' fate:** kept on disk (still referenced as the
   commented rollback path in each unit), but every one — plus the
   out-of-repo `/etc/self-improvement/dashboard.env` — now opens with a
   `NOT READ IN PRODUCTION as of USS-TJR-MSN-0371` comment header naming
   what replaced it. Deliberately not deleted, per the brief's own
   "either is fine, just not silently ambiguous" guidance.
3. **`run-with-infisical.sh` header** rewritten to state current reality
   (live secret source, not aspiration) and to point at
   `run-with-infisical-bot.sh` for the per-bot case; that script also
   documents the `--token=` argv fix from Stream 1 and the auth-file
   permission widening from this stream.
4. **Guardrail:** `tools/check_no_raw_env_secrets.py`, wired into
   `.pre-commit-config.yaml` as a local hook scoped to
   `deploy/*.service`. Tested both directions before trusting it — a
   clean run passes, a synthetic regression (re-enabling a commented
   `EnvironmentFile=`) fails with a clear message. One check, matches the
   brief's "keep it light" instruction.
5. **SUOC Platform Registry:** added a new "Secrets Management" capability
   record (L3 — Operational), including the technical debt this pass
   didn't close (Infisical's own uptime monitoring, `command-centre`'s
   pm2 env path, `lcars-portal`'s build-time gap, the 7 secret values
   exposed to this session's transcript).

## Explicitly not closed by this mission (real, not hidden)

- Infisical instance itself: still no uptime/monitoring (Stream 0 finding,
  unresolved — this mission's own dependency, not necessarily its fix).
- `command-centre` (pm2-managed): entirely separate secret mechanism,
  never investigated at the code level this session.
- `lcars-portal`'s `NEXT_PUBLIC_*` build-time env source.
- 3 retired/dead-reference services (`starship-chief-engineer-build-bot`,
  `starship-eng-bot` referencing nonexistent `.env` files;
  `starfleet-slack-bot` migrated but not restarted) — none actively
  running, so none actively insecure, but none proven clean either.
- `vm-processing.service`'s own cutover — config deployed, verification
  pending its next natural timer fire.
- Rotating the 7 secret values printed to this session's transcript.
- The ~10 "(none found — no EnvironmentFile=)" services from Stream 0's
  inventory were left untouched — this migration only ever covered the
  systemd `EnvironmentFile=` mechanism; whether any of those load secrets
  via code-level `dotenv` instead was flagged in Stream 0 as unchecked
  and remains unchecked.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KTwCophMNST95DQdnh4nQU
