# Knowledge Record — USS-TJR-MSN-0371 (Stream 0)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0371 |
| Title | Retire .env as a production secret source — Stream 0 (audit) |
| Date | 2026-09-12 |
| Status | Stream 0 only. Streams 1-6 NOT started — audit findings require the brief's own scope to be revised before Stream 1 can safely begin. |

## Headline finding: the mission brief's service inventory is stale

The brief's list of 21 services (from `deploy/*.service` in the repo) does
not match the live system in three distinct ways:

1. **Repo/live drift on 3 of the 21 named units.** `model-router.service`'s
   live `EnvironmentFile=` points at `platform-runtime/.env`; the repo copy
   says `slack-bot/.env` (a file that does not exist — see below).
   `intelligence-scheduler.service` and `intelligence-source-validation.service`
   also differ (see next point).
2. **`intelligence-scheduler.service` was already cut over to
   `run-with-infisical.sh`, live, on 2026-09-05 — a week before this
   mission — and never committed back to the repo.** The live unit's
   `ExecStart` wraps the command through the script; the repo's copy still
   shows the old bare `ExecStart`. So the brief's own claim ("zero services
   invoke the wrapper") is false for this one service, and there is an
   uncommitted production change sitting live right now with no rollback
   commit to revert to.
3. **Two of the brief's named services don't exist under those names.**
   `xo-bot.service` / `revs-bot.service` are not installed; the real live
   units are `tg-xo.service` / `tg-revs.service`. There is also a live
   `tg-capacitybot.service` — the brief explicitly said no matching unit
   was found for capacitybot; one exists and is active.

**Consequence:** I re-ran the audit against `/etc/systemd/system/*.service`
(the actual live inventory) rather than trusting `deploy/*.service`, and
found the live app-level service count is **38, not 21** — the brief's
list is a subset. Full inventory below.

## A live process already bypasses everything being audited

Independent of the systemd units, `ps aux` shows two long-running processes
invoking `infisical run` **directly**, with a pre-minted access token passed
as a plain CLI argument:

- PID 455997 — `chatterbox-tts.service`'s TTS process
  (`core/voice/tts_chatterbox.py`)
- PID 2369200 — the `intelligence-scheduler.service` process above

Passing `--token=<JWT>` on the command line means that token is visible to
any local process/user via `/proc/<pid>/cmdline` or `ps aux` — the exact
"secret's real value visible somewhere it shouldn't be" failure mode this
mission exists to close, just via a different mechanism than a `.env` file.
`chatterbox-tts.service`'s unit file wraps `run-with-infisical.sh` twice
(`wraps=2` — once in a comment, once in `ExecStart`), so it's already
"migrated" in the sense the brief means, but the token-on-cmdline exposure
should be treated as a new, separate finding for Stream 6's guardrail (the
wrapper script itself does this — `TOKEN="$(infisical login ...)"` then
`exec infisical run --token="$TOKEN"` — so every service that adopts the
documented wrapper inherits this exposure, not just these two ad hoc ones).

## Full live-service audit (38 app-level units, OS/system units excluded)

| Service | Active | Runs as | Already wraps infisical | EnvironmentFile(s) |
|---|---|---|---|---|
| capture-enrichment | inactive | root | no | platform-runtime/.env |
| chatterbox-tts | **active** | root | **yes** | (none — infisical run only) |
| command-bus | active | root | no | `.env`, platform-runtime/.env, telegram-bot/.env |
| control-engine | inactive | root | no | (none found) |
| engineering-batch-sync | inactive | root | no | platform-runtime/.env |
| health-osint-collection | inactive | root | no | `.env` (repo root) |
| number-one-exporter | active | root | no | (none found) |
| self-improvement-dashboard | active | root | no | **`/etc/self-improvement/dashboard.env`** (outside repo) |
| starfleet-backend | inactive | root | no | (none found) |
| starfleet-slack-bot | inactive | root | no | platform-runtime/.env |
| starship-chief-engineer-build-bot | inactive | root | no | telegram-eng-bot/.env, slack-bot/.env |
| starship-eng-bot | inactive | root | no | telegram-eng-bot/.env |
| starship-meilisearch | active | root | no | (none found) |
| tg-capacitybot | active | root | no | platform-runtime/.env, telegram-bots/capacitybot/.env |
| tg-revs | active | root | no | platform-runtime/.env, telegram-bots/revs/.env |
| tg-xo | active | root | no | platform-runtime/.env, telegram-bots/xo/.env |
| vm-processing-healthcheck | inactive | **claude** | no | `.env` (repo root) |
| vm-processing-retry | inactive | **claude** | no | `.env` (repo root) |
| vm-processing | activating | **claude** | no | `.env` (repo root) |
| auto-deploy | **failed** | root | no | (none found) |
| context-service | active | root | no | platform-runtime/.env |
| deadmans-switch | inactive | root | no | platform-runtime/.env |
| delivery-reconciler | inactive | root | no | (none found) |
| health-intelligence-weekly | inactive | root | no | (none found) |
| hq-evolution | inactive | root | no | (none found) |
| intelligence-scheduler | **active** | root | **yes (live-only, uncommitted)** | platform-runtime/.env |
| intelligence-source-validation | inactive | root | no | (none found) |
| lcars-portal | active | root | no | lcars-portal/.env.local |
| mint-server | active | root | no | (none found) |
| mission-engineering-dispatch | inactive | root | no | (none found) |
| mission-registry-sync | inactive | root | no | platform-runtime/.env |
| model-router | active | root | no | platform-runtime/.env (live; repo says slack-bot/.env — drift) |
| phoenix | active | root | no | (none found) |
| self-improving-system | inactive | root | no | (none found) |
| verification-engine | inactive | root | no | platform-runtime/.env |
| watchlist-changedetection-webhook | active | root | no | (none found) |
| watchlist-docker | active | root | no | (none found) |
| watchlist-uptime-kuma-webhook | active | root | no | (none found) |
| command-centre | active (**pm2**, not systemd) | root | no | pm2-managed, own env — not covered by any systemd audit |

Services showing "(none found)" either take no secrets, read them another
way (inline `Environment=`, hardcoded, or dotenv-in-code — not verified
per-service here, would need a code read per service, out of Stream 0's
grep-level scope), or are currently failed/inactive and unauditable live
(`auto-deploy` is in `failed` state independent of this mission — worth a
separate look, not this mission's to fix).

## Deduplicated .env file inventory (8 files, not 5)

The brief anticipated `platform-runtime/.env`, `slack-bot/.env`,
`telegram-bots/revs/.env`, `telegram-bots/xo/.env`, `lcars-portal/.env.local`.
Actual set in play:

- `/opt/starship-endeavour/platform-runtime/.env` — exists, 53 keys
- `/opt/starship-endeavour/.env` (repo root) — exists (4594 bytes), read by
  `command-bus`, `health-osint-collection`, and all 3 `vm-processing*`
  units. **Not in the brief's list at all.**
- `/opt/starship-endeavour/telegram-bots/revs/.env` — exists, 2 keys
- `/opt/starship-endeavour/telegram-bots/xo/.env` — exists, 9 keys
- `/opt/starship-endeavour/telegram-bots/capacitybot/.env` — referenced by
  `tg-capacitybot.service`; existence not yet checked (flagging, not
  verified this pass)
- `/opt/starship-endeavour/lcars-portal/.env.local` — exists, 18 keys
- `/opt/starship-endeavour/telegram-eng-bot/.env` — referenced by 2
  inactive services; existence not checked this pass
- `/etc/self-improvement/dashboard.env` — exists (77 bytes), **outside the
  repo entirely**, read by `self-improvement-dashboard.service` (active)
- `/opt/starship-endeavour/slack-bot/.env` — **referenced by 2 service
  files but does not exist on disk.** `model-router.service`'s repo copy
  and `starship-chief-engineer-build-bot.service` both reference it with
  the optional (`-`) prefix, so its absence is silently swallowed — those
  services (when using this file) load nothing from it and are either
  getting those values elsewhere or running without them.
- `/opt/starship-endeavour/telegram-bot/.env` (singular, no `-s`) —
  referenced by `command-bus.service`; not checked for existence.

## Gap list: keys in the checked .env files but not in Infisical prod

Checked `platform-runtime/.env`, `telegram-bots/revs/.env`,
`telegram-bots/xo/.env`, `lcars-portal/.env.local` (79 keys currently in
Infisical prod, confirmed via `infisical secrets --env=prod`). Did **not**
yet check the repo-root `.env`, `dashboard.env`, or the 3 unverified files
above — real gap in this pass, needed before Stream 1 touches any service
that reads one of those.

28 keys present on disk, absent from Infisical prod:

**Real secrets, need pushing before any cutover of a service that reads them:**
`GITHUB_TOKEN`, `GLM_API_KEY`, `BACKEND_API_KEY`, `LCARS_API_SECRET`,
`SUPABASE_KEY`, `COMMAND_CENTRE_API`

**Plain config, not secrets — candidates to leave as `Environment=` lines
in the unit rather than round-tripping through Infisical:**
`ADHD_NUDGE_ENABLED`, `ADHD_NUDGE_INTERVAL_MINUTES`, `BOT_NAME`,
`CAPTAINS_INBOX_CHANNEL_ID`, `CAPTAIN_SLACK_USER_ID`,
`COMMANDER_SYNTHESIS_MODEL`, `COMMANDER_SYNTHESIS_PROVIDER`,
`CONTENT_INTEL_PUSH_ENABLED`, `GITHUB_REPO`, `GLM_BASE_URL`, `GLM_MODEL`,
`HUMAN_SYSTEMS_CHANNEL`, `HUMAN_SYSTEMS_SCHEDULER`,
`LIFECYCLE_RECS_ENABLED`, `LLM_PROVIDER`, `NEXT_PUBLIC_API_BASE_URL`,
`OLLAMA_MODEL`, `REPO_ROOT`, `REVS_ADMIN_USER_IDS`, `USSTJROS_ROOT`,
`XO_SCHEDULED_BRIEFS_ENABLED`

**Explicitly out of scope per the brief:** `VERCEL_OIDC_TOKEN` (Vercel's
own env store).

**Not pushed to Infisical yet** — that's a write to the prod secret store,
holding for explicit go-ahead before executing, especially since some of
the "real secrets" above are live credentials.

## Item 4 — user/permission check

All 38 live units run as `root` **except** `vm-processing`,
`vm-processing-retry`, `vm-processing-healthcheck`, which run as user
`claude`. Verified directly: `sudo -u claude cat .infisical-auth.env` →
`Permission denied` (file is `chmod 600 root:root`, as the wrapper's header
claims). **This is a real Stream 0 blocker**, exactly as the brief
anticipated in the abstract — these 3 units cannot use
`run-with-infisical.sh` as-is. Needs either a group-readable ACL on the
auth file scoped to `claude`, a separate Infisical machine identity for
that user, or leaving these 3 on `.env` intentionally with that decision
documented (not silently skipped).

## Item 5 — Infisical instance monitoring

Self-hosted Infisical runs as 3 Docker containers
(`infisical-infisical-1`, `infisical-db-1`, `infisical-redis-1`, all up 6
days) behind `docker-proxy` on `127.0.0.1:8446`, answers `/api/status` with
200 right now. **No systemd unit, no uptime-kuma monitor, no repo
reference to it exists anywhere searched.** Confirmed real gap — every
service migrated in Streams 1-5 becomes dependent on this container stack
being up at boot, and nothing currently watches it. Flagging per the
brief's own instruction (not necessarily this mission's to fix, but must
be raised, not silently accepted).

## Recommendation before Stream 1 starts

The brief's Streams 2-5 grouping (by the original 21-service list) needs
revision against the real 38-service inventory above, and against the two
already-partially-migrated services (`intelligence-scheduler`,
`chatterbox-tts`) needing their own reconciliation step (commit the live
`intelligence-scheduler.service` drift back to repo; audit
`chatterbox-tts`'s token-on-cmdline exposure before calling it "done").
Recommend confirming scope revision with the Captain before Stream 1's
pilot, since the pilot's chosen service and procedure assumptions may
change once the full inventory is accounted for.

## Not done this pass (flagging, not hiding)

- Did not check `telegram-bots/capacitybot/.env`, `telegram-eng-bot/.env`,
  `telegram-bot/.env` (singular) for existence/contents.
- Did not audit `/opt/starship-endeavour/.env` (repo root, 4 services read
  it) or `/etc/self-improvement/dashboard.env` against Infisical — gap
  list above is therefore a floor, not the full picture.
- Did not investigate `command-centre`'s pm2-managed env source at all —
  entirely separate mechanism, out of systemd's reach, not covered by
  anything in the brief.
- Did not investigate the ~10 "(none found)" services' actual secret
  source (inline `Environment=`, hardcoded, or code-level dotenv) —
  would need a source read per service.
- Did not push any missing key to Infisical, touch any systemd unit, or
  restart any service. Nothing live was changed this pass.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KTwCophMNST95DQdnh4nQU
