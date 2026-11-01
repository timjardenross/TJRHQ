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

## Fixed — follow-up pass (later the same day)

- **auto-deploy.service de-rooted.** Was running full root for git pull +
  npm build + systemctl restart. Now `User=deploy` (new system user, repo
  `chgrp -R deploy` + setgid dirs — additive group grant, root's own
  access from the ~30 other root-run jobs sharing this tree is untouched),
  with the one root-required step (`systemctl restart`) scoped through
  `deploy/scoped-restart.sh` (checks the target unit against
  `auto-deploy-services.conf` before restarting) via
  `/etc/sudoers.d/deploy-restart`, one line, NOPASSWD only for that exact
  script. Verified end-to-end as the `deploy` user (git fetch/status, npm
  build-directory writes, a real dry-run pull cycle) before cutover.
- **auto-deploy.service failure paging disabled.** The `OnFailure=`
  alerting added earlier the same day turned out too aggressive in
  practice — paged every 5-minute retry for as long as the tree was
  legitimately dirty mid-edit (normal during active development), not
  just on a real failure. Commented out per explicit request rather than
  tuned; dirty-tree aborts are still visible via `systemctl status
  auto-deploy.service` / journalctl on demand.
- **~44/51 `useEffect` data-fetch hooks in lcars-portal lacked
  `AbortController`/cleanup.** Added a shared `src/hooks/useAbortEffect.ts`
  and converted 41 of the 45 affected files to it. 3 left unconverted
  (self-improvement-findings, emergency-alert-hub-workbench,
  captains-chair-workbench/notebook) — polling/multi-reuse shapes too
  complex for a safe mechanical diff, noted for a manual pass.
- **`core/governance` had zero real test coverage** (the one existing
  `test_governance_alignment.py` covers an unrelated captain-intelligence
  domain, not `authority_validator.py`/`authority_enforcement.py` at all).
  Writing tests surfaced a much bigger live bug: `governance/authority/` —
  the manifest directory the whole officer-authority gate is built around
  (EXEC-001 WP1, MSN-0326 Waves 3/4) — **never existed in the repo**.
  `load_manifest()` always returned `{}`, so `can_officer()` always hit
  the manifest-gap branch, which (since `AUTHORITY_MANIFEST_GAP_MODE`
  defaults to `"raise"`, Wave 3/4's documented fail-closed-by-default)
  raised `ManifestGapError` on every single check, for every officer,
  everywhere. Both real call sites (`core/coordination/execution_engine.py`,
  `platform-runtime/command_memory_integration.py`) only caught
  `AuthorityError` specifically or a broad `except Exception: log
  non-blocking, proceed` — `ManifestGapError` fell through and was
  silently swallowed. The whole gate was 100% fail-open in practice at
  both its only real call sites, opposite of its documented intent.
  Fixed: added baseline (deliberately unrestricted — matches prior de
  facto behaviour, doesn't invent new policy) manifests for all 13
  officer slugs found in real callers; both call sites now catch
  `ManifestGapError` explicitly and treat it as a denial. 32 tests added,
  covering both modules.
- **`core/command-centre/backend/*.js`** (Node, 19 routes + `app.js`) —
  first pass this session. `api/search.js`'s `_enc()` used
  `encodeURIComponent` alone to build PostgREST `or(...)` filter strings —
  doesn't escape `(` `)` `*`, all three significant in that syntax; a `q`
  containing `)` could prematurely close the filter group. Fixed by
  percent-encoding those three chars after the normal URI-encoding pass.
  `npm audit fix` cleared 3 moderate CVEs (transitive via express) with no
  breaking changes. Separately: the live process turned out to run under
  PM2 (`pm2 start app.js`, ad-hoc, no config file), while the only
  systemd record (`starfleet-backend.service`, disabled/inactive) had a
  drop-in pointing `WorkingDirectory` at an archived, non-live path —
  anyone using `systemctl status/restart` on it would've been acting on
  the wrong thing entirely. Removed the stale unit + drop-in, added
  `core/command-centre/backend/ecosystem.config.js` so the real PM2 setup
  (including the live port, 5000 — not the code's own `5050` fallback,
  confirmed via `ss -tlnp` and cross-checked against Caddy/lcars-portal
  config) is reproducible instead of tribal-knowledge-only.
- **210-file migration sweep** — checked live schema directly
  (`information_schema`, `pg_constraint`) rather than parsing migration
  history, same approach as the earlier RLS pass. Found and fixed real
  orphan-risk gaps on the mission-tracking tables:
  `mission_state_transitions.mission_id` / `mission_execution_events.
  mission_id` had no FK to `missions(mission_id)` (5 live orphan rows —
  test data + one legacy pre-ID-standardization dispatch — deleted, then
  FK added); `missions.status`/`created_at` were nullable despite being
  load-bearing for every status-filtered/ordered query (confirmed zero
  existing NULLs, added `NOT NULL`). Separately found (not a schema gap —
  a real application bug): `captured_items.research_mission_id` had 10
  non-null values, all self-referential (each row's own `id` echoed back
  under a different column name) — traced to
  `core/inbox/orchestrator.py` passing the captured_items row's own id as
  the `mission_id=` seed into `ResearchOrchestrator.run_research_mission()`,
  which only auto-generates a real tracking id when none is given. Fixed
  the call site (stopped passing the seed) and nulled out the 10
  meaningless existing values. See migration `0216_mission_fk_and_not_
  null_constraints.sql`.
- **36 tables with RLS enabled and zero policies** — classified all 36.
  Zero were actually broken: every real caller found uses the
  service-role key (bypasses RLS entirely by design), so these tables
  work fine despite having no PostgREST policies. One related latent-risk
  finding: `lcars-portal/src/lib/ai-context.ts` had the same
  silent-anon-key-fallback pattern already fixed once this session in
  `learning/route.ts` — not currently broken (service-role key is set),
  but would silently degrade AI-console context quality with no visible
  signal if it were ever unset. Fixed the same way (removed the fallback).
  5 of the 36 tables (`daily_health_snapshot`, `external_fetch_usage`,
  `intelligence_health_correlations`, `llm_cost_governance`,
  `system_heartbeat`) have real row counts but no caller found by a repo
  grep — likely written by something outside the searched paths/languages;
  flagged as unresolved rather than confidently dead, not chased further.

## Not fixed — flagged for follow-up

- **lcars-portal.service `User=root`** — needs an ownership audit of the
  build pipeline before a non-root service user is safe (the auto-deploy
  de-rooting above only covers the deploy pipeline, not the service
  itself).
- **3 lcars-portal fetch effects** left unconverted to `useAbortEffect`
  (see above) — polling/multi-reuse shapes, need a manual per-file pass.
- **5 tables with live data but no found caller** (see above) — worth a
  wider grep (other languages/paths) or a live PostgREST access-log check
  to actually identify the writer before deciding dead vs. needs-policies.
