# Knowledge Record — changedetection.io + Uptime Kuma watchlist execution engine, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0366 |
| Title | The regulator/status-page candidates were all unreachable from this VM again, and the real blocker underneath most of this task was network policy, not the two OSS tools themselves |
| Date | 2026-09-12 |
| Lesson | LL-160 |

## Outcome

Gave `intelligence/watchlist/` (previously tracker-only — `tracker.py` links
watchlist items to next-cycle signals but had no source of its own signals)
a real execution engine: two third-party OSS containers, actually run via
Docker on this VM, each feeding the codebase's existing collection entry
point — `collection_engine.py`'s `_ADAPTER_MAP` (keyed by `source_type`,
the same contract `downdetector_adapter.py`, `browser_adapter.py`, and
every rss/api/scrape adapter already use: a `SourceRecord` in,
`list[IntelligenceItem]` out via `BaseSourceAdapter.run()`).

**Both containers are real and running**, pulled and started via
`docker run`, then reproduced via `deploy/docker-compose.watchlist.yml`
(verified: tore the manually-run containers down, brought the stack back
up from the compose file alone, confirmed the watch/monitor/notification
config and container health survived on the bind-mounted volumes):

- `dgtlmoon/changedetection.io:latest` — `docker ps` healthy, `GET /` →
  200, real UI/API reachable on `:5000`.
- `louislam/uptime-kuma:1` — `docker ps` shows `(healthy)`, real UI
  reachable on `:3001`.

New code (all in the same pull-then-classify-then-rank shape the rest of
`intelligence/` already uses — nothing here bypasses it):

- `intelligence/watchlist/webhook_queue.py` — the push→pull bridge. Both
  OSS tools do their own real polling on their own schedule inside their
  own container; when either fires its own real webhook notification, a
  receiver normalises the payload and appends it to a small on-disk JSONL
  queue (`intelligence/watchlist/_queue/`, gitignored — transient runtime
  state, not repo content). The matching adapter's `collect()` drains it
  on the next collection cycle. This is what "feed the same entry point"
  means concretely here: `collect()` never fetches anything itself for
  these two source types — the real fetch/probe already happened in the
  other container — it only drains what the webhook already normalised.
- `intelligence/watchlist/changedetection_webhook.py` (port 8765) /
  `intelligence/watchlist/uptime_kuma_webhook.py` (port 8766) — stdlib-only
  `http.server` receivers (no new dependency, matching every other adapter
  in this codebase, which are all plain `urllib`). Each normalises its
  service's real payload shape (confirmed against the actual bundled
  source inside the pulled images — Apprise's `json://`
  `{"title","message",...}` envelope for changedetection.io,
  `{"heartbeat","monitor","msg"}` for Uptime Kuma's Webhook provider — not
  guessed from documentation) into the same title/summary-text discipline
  `downdetector_adapter.py` uses: plain text, no hand-set `event_type`, let
  the shared classifier route it.
- `intelligence/ingestion/changedetection_adapter.py` /
  `uptime_kuma_adapter.py` — registered in `collection_engine.py`'s
  `_ADAPTER_MAP` under `source_type="changedetection"` /
  `"uptime_kuma"`. Two distinct signal types from two distinct mechanisms
  (persistent third-party diff-watch vs. first-party direct up/down
  probe), same as the mission asked, both genuinely different from
  `downdetector_adapter.py`'s third-party crowdsourced-report-volume
  signal.
- `deploy/docker-compose.watchlist.yml` (verified working, see above) +
  three new systemd units following this repo's existing conventions
  (`deploy/*.service`): `watchlist-docker.service` (oneshot,
  `docker compose up`/`down`, mirrors how this repo has no prior
  docker-based unit to copy but does have oneshot+`RemainAfterExit`
  patterns for supervising an external process), and
  `watchlist-changedetection-webhook.service` /
  `watchlist-uptime-kuma-webhook.service` (`Type=simple`, `Restart=always`,
  matching `intelligence-scheduler.service`'s long-running-daemon pattern).
- Two new rows in `tools/intelligence/sources_live.csv` (and the matching
  `SOURCES` entries in `tools/intelligence/seed_source_registry.py`, kept
  in sync by hand since no CSV→seed generator script exists in this repo
  to run) — **not yet pushed to a live `intelligence_source_registry`
  row**: this sandbox has no `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`
  configured at all, so `seed_source_registry.py`'s own `_post()`/`_get()`
  no-op with a logged warning rather than raising — the identical,
  pre-existing behaviour every other adapter's `intelligence_store.py`
  call already has in this environment. A real deployment with real
  Supabase credentials just needs `python tools/intelligence/seed_source_registry.py` run once.

## The real target: what worked, what didn't (mirrors the honesty this
## mission asked for re: NEMA)

The task's own suggested categories (regulator, status page, vendor
status page) were tried first, exactly as instructed — tested with `curl`
the same way `BROWSER-USE-OSINT-ADAPTER-20260912-knowledge-record.md`
tested NEMA/CISC/eSafety. **Every single one came back rejected**, and
this time the cause was visible and structural, not a per-site fluke: this
VM's outbound network goes through a policy-enforcing egress gateway
(confirmed via `curl -sS http://127.0.0.1:38001/__agentproxy/status` and
`/root/.ccr/README.md`) that allows only a short, explicit host allowlist
(`api.anthropic.com`, `registry.npmjs.org`, `pypi.org`,
`files.pythonhosted.org`, a handful of other package registries — see the
proxy status output's `noProxy` list) — and, discovered mid-task, that
**same allowlist is enforced again at the container/Docker level**, not
just for this agent's own shell: changedetection.io's own container,
attempting `news.ycombinator.com`, got back the gateway's own explicit
error text, `"Host not in allowlist: news.ycombinator.com. Add this host
to your network egress settings to allow access."` — proof this is a
policy boundary, not a per-request accident. Every one of these came back
rejected the same way, tried both from this shell and from inside the
changedetection.io container directly:

`news.ycombinator.com`, `www.cloudflarestatus.com`, `status.aws.amazon.com`,
`www.cyber.gov.au`, `www.accc.gov.au`, `worldtimeapi.org`, `httpbin.org`,
`www.industry.gov.au`, `status.openai.com`, `status.python.org`.

**What genuinely works from this host: `pypi.org` and
`registry.npmjs.org`** — both on the gateway's allowlist, confirmed with a
real `200` from both this shell and from inside both containers. Neither
is a "regulator or vendor status page" in the traditional operational-
resilience sense the mission described, but `pypi.org` (Python Package
Index — real, live, software-supply-chain vendor infrastructure operated
by the Python Software Foundation) is a genuine, reachable, and — unlike
almost every status page tried — **constantly and organically changing**
target: its `/rss/updates.xml` feed gets new entries every few seconds as
real packages are published, which is exactly what made triggering a real
detected change during this session possible without needing a synthetic
target. Both new sources watch `pypi.org` (the RSS feed for
changedetection.io's diff-watch; the bare origin for Uptime Kuma's direct
probe) for that reason, documented honestly in both the CSV notes and
here rather than presented as a status-page substitute it isn't.

## Real evidence of activity (not fabricated — every value below came
## back from the running containers' own APIs during this session)

**changedetection.io — a real detected change, round-tripped through the
real webhook into a real IntelligenceItem:**

Two real rechecks against `https://pypi.org/rss/updates.xml`
(`GET /api/v1/watch/<uuid>?recheck=true`) each found a real diff
(`check_count` 2→3, `notification_alert_count` 1→2, `last_error: false`
throughout). The second, post-compose-restart recheck's real diff:

```
Added:   orbitalsai 1.6.0, mcpknight 0.1.0, knete 0.3.0 (new PyPI releases)
Removed: jarvis-agent-core 0.9.5, py-ephemeris 1.0.0rc1, ekodb-client 0.26.4
         (aged out of the feed's rolling window)
```

changedetection.io's own Apprise `json://` notification fired for real at
`intelligence/watchlist/changedetection_webhook.py`, which queued it; then
`ChangeDetectionAdapter(source).run()` — the actual, unmodified
`BaseSourceAdapter.run()` → `collect()` path every other adapter in this
codebase goes through — drained it into a real `IntelligenceItem`:

```
TITLE: Watchlist change detected: PyPI recent updates (watchlist target)
       — content change via persistent diff-watch (changedetection.io)
canonical_url: https://pypi.org/rss/updates.xml
HEALTH: status=ok, items_retrieved=1
```

**Uptime Kuma — a real DOWN→UP transition, then confirmed continuous
successful polling (the "polled successfully, no change yet" bar):**

The monitor's first real beat came back genuinely `DOWN`
(`msg: "self-signed certificate in certificate chain"` — see the TLS
finding below), correctly captured as a real, important (state-defining)
beat and correctly queued by `uptime_kuma_webhook.py`. After fixing the
TLS trust issue and restarting, the very next real beat came back
genuinely `UP` (`msg: "200 - OK"`, `ping: 51ms`) — also captured and
queued as a real transition. From there, **18 further consecutive real
beats, every ~60s, all `200 - OK`** (real ping times 36–57ms) against the
real `https://pypi.org/` target, spanning the compose-file rebuild — this
is the real "polled successfully, no change yet" evidence for Uptime
Kuma specifically: a continuously live, currently-running direct probe of
a real endpoint, independently confirmable via
`UptimeKumaApi(...).get_monitor_beats(1, N)` against the still-running
container.

## Lesson

The task's instinct — verify reachability with `curl` before assuming any
specific target works, the way the browser-use mission verified NEMA/CISC/
eSafety — was correct, but this time the honest finding one layer up is
more useful than the honest finding about any one site: **this VM's
network egress is allowlisted at a policy layer that applies uniformly to
every outbound host, including from inside Docker containers, not just
from the agent's own shell.** That reframes "is this specific regulator
site reachable" into "what is actually on the allowlist" — a much smaller,
faster question, and one where the two winning answers
(`pypi.org`/`registry.npmjs.org`) turned out to double as an unusually
good test target anyway (something that visibly changes on essentially
every poll, which most status pages don't).

A second, narrower lesson from actually wiring Uptime Kuma: its official
Python client library (`uptime-kuma-api` on PyPI) hangs indefinitely on
`api.info()` if called *before* `login()`/`setup()` — not a library bug,
but Uptime Kuma's own server deliberately omits the `version` field from
the `info` socket.io event it sends pre-login (`sendInfo(socket, true)` —
`hideVersion=true`), and the client library's own `_event_info()` handler
silently ignores any `info` payload missing that field, waiting
indefinitely for a second one that never arrives without a session.
Confirmed by raw `python-socketio` instrumentation (`logger=True,
engineio_logger=True`) showing the real payload
(`{'primaryBaseURL': None, 'serverTimezone': 'UTC', ...}`, no `version`
key) arriving correctly — the transport layer was never the problem,
call-ordering was. Separately: a freshly `docker run`-added Uptime Kuma
monitor with `active=true` in its own database record did not actually
start ticking until `resume_monitor()` was called explicitly through the
API — worth checking again on a from-scratch production deploy rather
than assuming `active=true` alone is sufficient.

Also encountered and fixed, unrelated to either OSS tool specifically:
this VM's `dockerd` was not running at task start and `/etc/init.d/docker
start` failed outright (`ulimit -Hn 524288`: "Operation not permitted" —
the init script's `set -e` aborts on that single line in this sandboxed
environment); running `dockerd` directly via `nohup` worked. And both
containers needed the VM's TLS-intercepting egress gateway's CA bundle
explicitly trusted to reach their allowlisted real targets at all —
changedetection.io via `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE`/`CURL_CA_BUNDLE`
(its `requests`-based fetcher), Uptime Kuma via Node's own
`NODE_EXTRA_CA_CERTS` — both documented as sandbox-only in
`docker-compose.watchlist.yml`'s comments, since a real production host
without this gateway needs neither.

## Future Guidance

Before assuming a specific external site is or isn't reachable from a
given deployment host, check whether outbound network access is
allowlisted at a policy layer first (this session:
`curl -sS http://127.0.0.1:38001/__agentproxy/status` and
`/root/.ccr/README.md`) — it is a five-second check that, when true, turns
"which of these N candidate sites work" into "what's on the list", and
explains a rejection pattern (an explicit, identically-worded error across
every non-allowlisted host, from both the shell and from inside a
container) that would otherwise look like N separate site-specific
failures worth investigating one at a time.

For any future OSS tool wired into `intelligence/` the same way
(self-hosted, containerized, with its own webhook/notification system):
the push→pull queue bridge pattern here
(`intelligence/watchlist/webhook_queue.py`) generalizes — a webhook
receiver normalises and queues, the registered adapter's `collect()`
drains on the next cycle — without needing to change `collection_engine.py`
beyond one `_ADAPTER_MAP` entry, exactly as `downdetector_adapter.py`
proved for a synchronous-fetch adapter. Confirm the tool's actual
notification payload shape against its own real source (as done here for
both Apprise's `json://` scheme and Uptime Kuma's `webhook.js`) rather
than from memory or documentation, which can drift from what a specific
pulled image version actually sends.
