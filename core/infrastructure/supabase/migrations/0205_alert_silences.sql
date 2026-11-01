-- 0205_alert_silences.sql
--
-- Alertmanager-style temporary suppression (core/platform/alert_silences.py).
-- Nothing on this platform currently lets the Captain say "I know about
-- this, stop notifying me for the next N hours" without permanently
-- disabling a whole source (alert_sources.active, migration 0174) — a
-- silence is scoped and time-bounded instead. Concrete first use: a
-- planned hazard-reduction burn generates expected, non-actionable
-- Emergency Alert Hub alerts for a known jurisdiction/alert_type for a
-- known window.
--
-- Matching (see alert_silences.py's _matches()) is a plain "every set
-- match_* field equals the corresponding alerts column" AND, mirroring
-- alerts' own flat column shape (migration 0174) rather than a jsonb query
-- language this single-user platform has no second consumer for yet.
-- match_* columns are intentionally NOT foreign keys to alerts/alert_sources
-- columns (e.g. match_source_key -> alert_sources.source_key): a silence is
-- a pattern that can pre-date or outlive any specific alert row, and this
-- table is written to support other future notification paths
-- (core/coordination/command_bus.py's own alerting) beyond just the
-- alerts table this migration ships alongside.
--
-- RLS write access: the Emergency Alert Hub workbench's own Silences panel
-- (lcars-portal/src/app/api/emergency-alerts/silences/) creates/expires
-- silences through the Captain's own authenticated session
-- (createSupabaseServerClient() — anon key + user cookies, NOT service
-- role), so `authenticated` needs real insert/update/delete grants here,
-- not just the service_role policy a backend-job-only table would need.
-- Same convention as shopping_list_items (migration 0199 / 0193's
-- authenticated-RLS precedent): single-Captain app, no per-row ownership
-- to filter by, so `using (true)`/`with check (true)`.

create table if not exists alert_silences (
  id                 uuid primary key default gen_random_uuid(),
  reason             text not null check (length(trim(reason)) > 0),
  starts_at          timestamptz not null default now(),
  ends_at            timestamptz not null,
  match_jurisdiction text,
  match_alert_type   text,
  match_severity     text,
  match_source_key   text,
  created_at         timestamptz not null default now(),
  check (ends_at > starts_at)
);

create index if not exists idx_alert_silences_active_window on alert_silences(starts_at, ends_at);

comment on table alert_silences is
  'Time-bounded suppression rules (core/platform/alert_silences.py). A silence matches an alert when every non-null match_* column equals the alert''s corresponding field; all-null matches everything (a deliberate full-mute window). Always has a required reason and end time — no open-ended/permanent silences, same discipline as Prometheus Alertmanager''s own silences.';

alter table alert_silences enable row level security;

drop policy if exists alert_silences_read on alert_silences;
create policy alert_silences_read on alert_silences for select using (true);
drop policy if exists alert_silences_service_write on alert_silences;
create policy alert_silences_service_write on alert_silences
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

drop policy if exists alert_silences_authenticated_insert on alert_silences;
create policy alert_silences_authenticated_insert on alert_silences
  for insert to authenticated with check (true);
drop policy if exists alert_silences_authenticated_update on alert_silences;
create policy alert_silences_authenticated_update on alert_silences
  for update to authenticated using (true) with check (true);
