-- Fix: comms_content_revisions has RLS enabled (migration 0095_content_
-- workflow_extensions) with zero SELECT policies. Every write to that
-- table goes through the service-role client, but the read path
-- (content-workbench/[id]/revisions/route.ts) uses the session-scoped
-- anon-key client, which is subject to RLS. With RLS on and no policy,
-- authenticated reads silently return an empty set (no error) even
-- though real rows exist — "Show Revision History" always rendered
-- "No revisions yet." in the UI. Confirmed live: 10 rows across 5
-- distinct content items were invisible before this policy existed.
--
-- Matches the auth_read pattern already used on comms_content,
-- intelligence_events, intelligence_briefs, and
-- intelligence_source_registry: authenticated-only read, no anon.
-- Chief Engineer review (content workbench), 2026-08-09.

create policy auth_read on comms_content_revisions
  for select
  to authenticated
  using (true);
