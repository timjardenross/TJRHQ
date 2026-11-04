# Timers and command-bus follow-up — 2026-11-05

Read-only except for opening PR #580. Nothing started, stopped, installed or restarted. Snapshot ~09:00 AEDT. VERIFIED = observed this session; UNKNOWN = not observed.

## 1. Timers with `Requires=` on a service

Exactly the 11 timers you listed have `Requires=<service>` (VERIFIED by grep of `/etc/systemd/system/*.timer`); the other 10 timers do not.

| Timer | Enabled | Active | Next run | Last run | Note |
|---|---|---|---|---|---|
| capture-enrichment | enabled | active | 09:00:17 today | 08:45:31 | every 15 min |
| daily-ops-cycle | enabled | active | Fri 06:51:34 | Thu 06:51:31 | 06:50 Sydney |
| deadmans-switch | enabled | active | within ~2 min (monotonic) | 08:49:38 | `OnUnitActiveSec=10min`; no realtime "next" because monotonic |
| engineering-batch-sync | enabled | active | monotonic, within ~30 min | 08:56:15 | `OnUnitActiveSec=30min` |
| hq-evolution | enabled | active | Fri 03:02:49 | Thu 03:00:31 | 03:00 + random delay |
| **mission-engineering-dispatch** | enabled | **inactive** | **none (infinity)** | Wed 2026-10-28 20:43:09 | **EXPECTED**: intentionally paused. Timer stopped 2026-10-28 20:57:55 ("Deactivated successfully"); service last ran 21:49:28 the same day. Unit file is a symlink into `deploy/`. |
| self-improving-system | enabled | active | Fri 07:04:25 | Thu 07:03:45 | restored this morning, see below |
| verification-engine | enabled | active | monotonic, within ~5 min | 08:53:04 | `OnUnitActiveSec=5min` |
| vm-processing-healthcheck | enabled | active | 09:00:05 | 08:30:16 | every 30 min |
| vm-processing-retry | enabled | active | 09:01:10 | 08:00:31 | hourly |
| vm-processing | enabled | active | 09:00:10 | 08:50:06 | every 10 min |

All services are `inactive` (oneshots between runs). **Enabled-but-inactive or no-next-run, excluding the expected one: none.** The three monotonic timers show no realtime "next"; their next elapse is minutes away and each ran in the last hour, so they are healthy (VERIFIED from `NextElapseUSecMonotonic` against uptime).

### When each stopped (journal, 7 days)

- Ten of the eleven timers: **0** stop events in 7 days (VERIFIED).
- self-improving-system.timer: **11** stop events, last `Stopped` 2026-11-05 07:56:21; `Started` again 08:49:56. The stops on 11-04/11-05 07:08-07:29 were paired with an immediate `Started` (the service's failed-restart cycle restarted the timer each time). The 07:56:21 stop was mine and was **not** followed by a start: the timer sat dead for ~53 min until I restored it. It would have stayed dead through the 07:00 run. Already documented in the installs report.
- mission-engineering-dispatch.timer: stopped 2026-10-28 20:57:55 (older than 7 days), no events since (expected).

## 2. Who stopped these services (7 days)

| Source | Result | Status |
|---|---|---|
| `journalctl -t sudo --since -7d` for `systemctl` on any of the 11 services | 8 commands, **all `self-improving-system` on 2026-11-05 07:53-07:56 and all mine** (`reset-failed`, `start`, one `stop`) | VERIFIED |
| All sudo `systemctl stop/disable/kill/mask`, any unit, 7 days | exactly one: `stop self-improving-system.service` at 07:56:21 | VERIFIED |
| `/root/.bash_history`, `/home/codex/`, `/home/jarvis-user/` | no `systemctl stop/disable/kill/mask` of any of the 11 services. Caveat: root history is capped at 2000 lines and has **no timestamps**, so it cannot prove "last 7 days" | VERIFIED (no match) / UNKNOWN (coverage) |
| systemd journal, per service, `Stopping`/`Stopped` in 7 days | 0 for ten services; self-improving-system 1 (that stop) with 13 failures and 10 scheduled restarts (the llmsec outage) | VERIFIED |

Did each timer survive? **Ten survived with no interruption. self-improving-system's timer did not survive the 07:56 stop** and was restored at 08:49. mission-engineering-dispatch stayed paused as expected.

## 3. command-bus: which source the running process has

Process pid 2800257, started 2026-11-01 13:14:38. Sources: `.env` (43 names), `platform-runtime/.env` (51), Infisical via `run-with-infisical-bot.sh xo` in an empty environment (112). `telegram-bot/.env` does not exist. 10 variables differ across the sources. No values shown.

| Variable | Present in | Running process equals | Result |
|---|---|---|---|
| BRIEF_CHANNEL | env, platform, infisical | env, infisical | MATCH Infisical |
| BRIGHTDATA_API_KEY | env, platform, infisical | infisical | MATCH |
| BRIGHTDATA_ZONE | env, platform, infisical | platform, infisical | MATCH |
| EMBEDDING_PROVIDER | env, platform, infisical | env, infisical | MATCH |
| GEMINI_API_KEY | env, platform, infisical | infisical | MATCH |
| GEMINI_BILLING_API_KEY | env, platform, infisical | infisical | MATCH |
| MISTRAL_API_KEY | env, platform, infisical | infisical | MATCH |
| MISTRAL_BATCH_API_KEY | env, infisical | infisical | MATCH |
| SUPABASE_ANON_KEY | platform, infisical | infisical | MATCH |
| TELEGRAM_BOT_TOKEN | platform, infisical | infisical | MATCH |

All 10 match Infisical (VERIFIED). No name in either `.env` file is absent from Infisical (VERIFIED). So: **draft PR #580** removes the three `EnvironmentFile=` lines from `deploy/command-bus.service` (the repo had them as commented rollback lines plus a comment; replaced with a "do not re-add" note). `pytest tests/test_infisical_unit_ordering.py -q`: 2 passed; `tools/check_no_raw_env_secrets.py`: exit 0; diff vs installed unit: only those 3 lines. **Not installed.** Installing needs `daemon-reload` and a command-bus restart. Caveat: the process has run since 11-01, so whether Infisical changed since is UNKNOWN (it matches today).

## 4. EMBEDDING_PROVIDER by running service

Read from `/proc/<pid>/environ` for every process in each running service's cgroup (39 services). Provider names only.

| Value | Services |
|---|---|
| `mistral` | chatterbox-tts, command-bus, context-service, human-systems-scheduler, intelligence-scheduler, lcars-portal, model-router, self-improvement-dashboard, tg-capacitybot, tg-resiliencebot, tg-xo |
| `ollama` | **none** |
| any other value | **none** |
| unset | the other 28 (caddy, command-centre, containerd, cron, dbus, docker, fail2ban, getty, mint-server, multipathd, number-one-exporter, ollama, phoenix, polkit, rsyslog, snapd, ssh, starship-meilisearch, systemd-*, unattended-upgrades, watchlist-* ...). Embedding code defaults to `mistral` when unset (`tools/supabase/embedding_client.py` `DEFAULT_PROVIDER = "mistral"`), so unset behaves as mistral. Whether any of the unset ones embed at all: UNKNOWN |

All VERIFIED. **Nothing running uses ollama, and nothing disagrees with `document_chunks` (mistral, 1024).**

Things that could still use `ollama` (not running services; UNKNOWN whether any ever run): `platform-runtime/.env` still says `EMBEDDING_PROVIDER=ollama`; two tools call `load_dotenv` on it (`tools/intelligence/backfill_cps230_cyber.py`, `tools/validate_ai_context_schema.py`), and anyone sourcing it by hand would get ollama (768) against a 1024 column. Only `command-bus.service` loads it by unit, and its live value is mistral. Consider fixing the value in that file.

Separate by design, not a mismatch: `vm-processing` (a timer, not in the running list) writes `nomic-embed-text` (ollama, 768) into `processing_chunks` with its hard-coded model name, independent of `EMBEDDING_PROVIDER`.

## 5. Live column types (read-only `SELECT`)

Connected with `SUPABASE_DB_URL` from Infisical in a throwaway `postgres:17` container with `default_transaction_read_only=on`; catalog and `SELECT` only. VERIFIED.

| Column | Live type | Populated |
|---|---|---|
| `public.document_chunks.embedding` | **vector(1024)** | 1,206 rows labelled `mistral:mistral-embed` + 4 labelled `mistral-embed`, all dim 1024; 34 rows with no embedding |
| `public.research_memory.embedding` | vector(768) (legacy, migration 0162) | 0 rows in the table |
| `public.research_memory.embedding_mistral` | **vector(1024)** | 0 rows in the table |
| `public.processing_chunks.embedding` | vector(768) | 938 rows, `nomic-embed-text` |
| `unified_memory` | **no table or view of that name exists** (`pg_class` search) | n/a |

The column-listing query found exactly four vector columns in tables/views (the four rows above). A separate count over `pg_attribute` returned 6 because that catalog also includes index columns; the two extra are most likely vector indexes on these tables. Not itemised: UNKNOWN.

`unified_memory`: `core/platform/unified_memory.py` is a routing layer over many stores, and for semantic recall uses Graphiti/mem0 with a Qdrant vector store configured for **768-dim Gemini embeddings** (not a Postgres column and not driven by `EMBEDDING_PROVIDER`). I did not query Qdrant: UNKNOWN.

## 6. Tomorrow (not yet possible)

- **After 02:45 Fri 2026-11-06: run `/root/verify-backup-after-0245.sh`.** Not run: the first run of the new `backup.sh` has not happened. UNKNOWN.
- **After the 07:04:25 run: report whether self-improving-system completed and whether the router wait fired.** Not observable yet. How to tell: `journalctl -u self-improving-system --since "2026-11-06 07:00"` for `Finished`/`success: true`; the router wait is silent when the router is healthy (instant), and prints `model-router not healthy after 30s, continuing` only on timeout, so "fired" means the `ExecStartPre` ran: check `systemctl show self-improving-system -p ExecStartPre` start/exit timestamps (`status=0/SUCCESS`). UNKNOWN.

These two need a follow-up session at those times.
