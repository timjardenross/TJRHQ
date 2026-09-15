# Adversarial review remediation — 2026-09-15

Referenced by `id_registry.py`, `tools/alert_on_systemd_failure.py`,
`deploy/self-improving-system.service`, and `deploy/auto-deploy.service` —
those references predated this file (written concurrently by the VM's own
self-improvement automation and this review session on the same day); this
consolidates what both passes found and fixed.

## Fixed

- **tg-revs.service crash-loop (Critical).** `core/llm/provider_chain.py`,
  `core/model-router/app.py`, `platform-runtime/lib/mistral_agent_client.py`
  each did `sys.path.insert(0, platform-runtime/.venv/site-packages)` for
  optional OTel tracing, shadowing the *caller's own* venv packages on any
  name collision. `telegram_bots/revs/app.py` eagerly imports
  `crisis_layer2` → `core.llm.provider_chain` before building its Supabase
  client, so it picked up platform-runtime's newer `supabase`/`httpx`
  instead of its own pinned 2.3.4, crashing on
  `TypeError: Client.__init__() got an unexpected keyword argument 'proxy'`
  every startup (77+ restarts). Changed all three to `sys.path.append(...)`
  so the fallback only fills gaps (opentelemetry) instead of overriding.
  `tg-xo.service` never hit this because its equivalent import
  (`debrief_engine`) is lazy, not eager — same latent risk there until now.

- **debrief_sessions / debrief_logs / debrief_turns / insight_outcomes RLS
  (High).** Live `pg_policies` showed these granted to Postgres role
  `public` (= anon included) with `USING(true)`/`WITH CHECK(true)`, with
  `debrief_turns` and the live policy names having no backing migration at
  all — undocumented drift, same class as the advisory_sessions leak
  reconciled in migration 0100 but in the unsafe direction. debrief_* holds
  voice-transcribed personal content (stressors, open_loops,
  transcript_text); insight_outcomes is the MSN-0210E quality-scoring
  record. Migration `0215_debrief_and_insight_outcomes_rls_reconcile.sql`
  scopes these to `{authenticated, xo_bot}` (debrief_*) and
  `service_role`-write/`authenticated`-read (insight_outcomes), applied
  live and verified via `pg_policies`.

- **Governance cache invalidation dead code (Medium).**
  `core/inbox/event_listeners.py`'s `sweep_expired_governance_cache()` had
  zero callers and no scheduled entrypoint since WP3B — expired governance
  assessments on `captured_items` never got re-queued. Added a
  `__main__` entrypoint plus `deploy/governance-cache-sweep.service`/`.timer`
  (hourly), enabled live.

- **lcars-portal.service hardening (Low-Med).** No `User=`, no systemd
  sandboxing for a service that serves requests directly from the public
  internet via Caddy. Added `NoNewPrivileges`, `ProtectSystem=strict`,
  `ProtectHome`, `PrivateTmp`, scoped `ReadWritePaths` to `.next/cache`.
  Did not change `User=` away from root — the repo tree is root:root and
  `auto-deploy.sh`'s `npm run build` writes `.next/` as root between
  deploys; a non-root service user needs a matching ownership change
  verified against a live deploy cycle first (flagged below, not attempted
  blind against the live dashboard).

- **`lcars-portal/src/app/api/advisory-sessions/route.ts` error leakage
  (Low).** Returned raw Supabase/Postgres error text to an already-session-
  gated client. Now logs server-side, returns a generic `{error: 'internal
  error'}`.

- **`lcars-portal/src/app/api/learning/route.ts` silent anon-key fallback
  (Low).** Silently degraded to the anon key (RLS then quietly returns
  empty/partial `outcome_records`) if `SUPABASE_SERVICE_ROLE_KEY` was
  unset, masking misconfiguration as "no data yet". Now throws at route
  entry instead.

- **auto-deploy.service silent failures (High, found by the concurrent
  self-improvement pass).** Ran every 5 minutes and failed every time for
  3+ days (dirty working tree correctly aborted the pull, but nothing
  alerted). `OnFailure=alert-on-failure@%n.service` +
  `tools/alert_on_systemd_failure.py` added; `self-improving-system.service`
  got the same `StartLimitIntervalSec` circuit-breaker pattern.

- **Mission-ID minting drift (High, found by the concurrent pass).**
  `id_registry.py`'s repo-wide max-ID scan picked up `USS-TJR-MSN-9999`
  false positives from `.cortex/` and `data/` test fixtures. Both
  directories now excluded from the scan, plus a `_MAX_SANE_DRIFT` guard.

- **hq-evolution-timer branch-mismatch (Medium, found by the concurrent
  pass).** The self-improvement orchestrator committed against whatever
  branch happened to be checked out in the shared `/opt/starship-endeavour`
  worktree and never pushed — ~64 cycles' worth of evidence silently
  refused to commit between 2026-09-12 and the fix. Moved to a dedicated
  worktree (`/opt/starship-endeavour-self-improvement`, branch
  `self-improvement`) plus an operator-visible alert if a commit still
  fails.

- **451 orphaned self-improvement run directories (Low).** Stranded by the
  branch-mismatch bug above, in the shared checkout's
  `data/self-improvement/runs/`. Reconciled by committing them (tracked
  evidence by design, per this repo's own `.gitignore` comment).

## Not fixed — flagged for follow-up

- **auto-deploy.service / self-improving-system.service run as full root**
  for git pull + npm build + systemctl restart. Scripts themselves are
  well-guarded (dirty-tree abort, ff-only, no push) but have no privilege
  scoping. Needs a sudoers-scoped non-root deploy user restricted to the
  exact `systemctl restart <unit>` / `npm` commands needed — not attempted
  here since it changes how every deploy on this VM runs and needs a live
  deploy-cycle test to verify before cutover.
- **lcars-portal.service `User=root`** — see above; needs an ownership
  audit of the build pipeline before a non-root service user is safe.
- **~44/51 `useEffect` data-fetch hooks in lcars-portal lack
  `AbortController`/cleanup** — silent stale UI on fast navigation, not a
  crash. Fix via one shared `useFetch` hook rather than touching each file.
- **`core/governance`** (`authority_validator.py`'s fail-open default
  included) has one test file for 483 lines — thin coverage on a
  safety-critical module.
- **`core/command-centre/backend/*.js`** (Node, ~20 routes) untouched by
  this review — Python-focused tooling skipped it; needs a JS-focused pass.
- **210-file migration constraint audit** not completed — this review
  checked live `pg_policies`/`get_advisors` directly rather than every
  historical migration file, which is more reliable for *current* state
  but doesn't rule out missing `NOT NULL`/FK constraints elsewhere.
- **36 tables with RLS enabled and zero policies** (`get_advisors`
  security lint) — default-deny, safe, but likely means some intended
  feature silently can't read/write these tables via PostgREST. Worth a
  pass to confirm which are dead vs. broken.
