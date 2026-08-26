-- 0170_domain_registry_platform_health_cleanup.sql
--
-- Captain-confirmed 2026-08-25 triage of 3 Platform Health domains that
-- kept surfacing as degraded, same soft-delete/reword convention as
-- migrations 0112/0117 (domain_registry.active flag).

-- physical_readiness (migration 0071): zero writer anywhere in the repo,
-- confirmed via repo-wide search this session — not a broken job, a
-- capability that was never built. Retiring from Platform Health rather
-- than inventing a synthetic writer; re-activate if a real capture path
-- (manual log, device data, etc.) is ever wired up.
update domain_registry
set
  active = false,
  notes  = notes || ' -- RETIRED 2026-08-25: no write path found anywhere in the repo (Python or TypeScript); Captain-confirmed removal from Platform Health rather than building a placeholder writer. Re-activate if a real Physical Readiness capture path is ever built.'
where domain_key = 'physical_readiness';

-- wellness-coaching (migration 0083): its real automated writer was
-- intentionally retired 2026-08-13 (commit 6d4b68e4, "Retire duplicate
-- automated Recovery Telegram alerts") citing platform-runtime/
-- human_systems_scheduler.py as the successor. CORRECTION (verified this
-- session, not assumed): that successor is not live either — its only
-- invoker, start_in_process(), is called solely from platform-runtime/
-- app.py, which now exists only in a backup directory
-- (USSTJROS.backup-20260719/), not the live repo; its sole live trigger
-- path, starfleet-slack-bot.service, has been disabled since 2026-07-07.
-- human_systems itself is already registered as inactive for this exact
-- reason (migration 0114, 2026-08-10). So this is not a repoint to a live
-- signal — wellness-coaching simply has no live automated writer of any
-- kind, same root cause/class as physical_readiness above.
update domain_registry
set
  active = false,
  notes  = notes || ' -- RETIRED 2026-08-25: automated writer (engagement_dispatcher.py) was retired 2026-08-13; its named successor, platform-runtime/human_systems_scheduler.py, has no live invoker either (start_in_process() is only called from platform-runtime/app.py, which exists solely in a backup directory, not the live repo; its sole live trigger, starfleet-slack-bot.service, has been disabled since 2026-07-07) -- confirmed by human_systems itself already being retired for this identical reason (migration 0114, 2026-08-10). No live automated writer exists for this signal under any domain key. Re-activate only if a real live writer is built.'
where domain_key = 'wellness-coaching';

-- captured_items (migration 0071): NOT retired — this domain is real and
-- alive, just genuinely bursty (fires only on a voice message or /note,
-- confirmed this session: tg-xo.service healthy, writers intact, simply no
-- capture in 3 days). Its original 60/60 cadence+grace (barely 2 hours
-- total) was too tight for "Captain-paced, event-driven" from day one,
-- turning ordinary idle periods into false "degraded" alarms. Loosened to
-- match how the domain actually behaves; infra_narrative.py (this
-- migration's companion code change) also now reads this domain's notes
-- directly so the Platform Health narrative reflects "usage-driven, not
-- broken" instead of alarmed language regardless of the exact threshold.
update domain_registry
set
  expected_cadence_minutes = 1440,
  grace_period_minutes = 10080,
  notes = 'Event-driven on capture (voice message or /note via XO Telegram bot); async classification. Genuinely bursty — the Captain may go several days without capturing anything, which is normal idle behaviour, not a fault. Generous grace reflects that (loosened from 60/60 min 2026-08-25 — that cadence was never realistic for a usage-driven domain).'
where domain_key = 'captured_items';
