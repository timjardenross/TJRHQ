-- Shopping List Workbench: shopping_list_saved_views — server-backed saved
-- filter/sort views for the Shopping List page.
--
-- Deferred item from the VM activation handoff: the existing "Saved views"
-- control on the Shopping List page (src/app/shopping-list-workbench/
-- page.tsx) only ever wrote to localStorage (`tjr-shopping-saved-views`),
-- so a saved view was per-browser, lost on a new device/profile, and never
-- reload-safe against anything the server could validate. This table (plus
-- lcars-portal/src/app/api/shopping-list/views/*) makes the server the
-- authoritative source; the client may still cache for UX but must not
-- treat localStorage as the source of truth.
--
-- Ownership: unlike shopping_list_items (migration 0199, unrestricted
-- `using (true)` policies — genuinely no per-row ownership concept there),
-- this table is explicitly asked to support "user can only read/mutate
-- their own views" and an ownership-isolation regression test. This repo
-- is single-Captain today (requireSession() note: "any authenticated
-- session is the Captain"), so in practice owner_id will only ever equal
-- one auth.users.id — but the column and the auth.uid()-scoped RLS policies
-- below are real, not decorative, and make the isolation test meaningful
-- rather than vacuous. Deliberate deviation from 0199's simpler
-- unrestricted-authenticated convention, called out here so it isn't
-- mistaken for a copy/paste slip.
--
-- filters/sort are jsonb rather than typed columns: the Shopping List page
-- already has four free-text-ish filter dimensions (category, status,
-- recipient, occasion) plus an unshipped sort control this mission adds
-- the contract for — jsonb avoids a schema migration every time a filter
-- dimension is added, matching how this repo already treats similarly
-- open-ended payload shapes (e.g. capacity_interventions.evidence_metadata,
-- migration 0159). The API route is the one place that validates the
-- shape before it's ever trusted back out (see
-- lib/shoppingListViewsServer.ts's isValidFilterPayload/isValidSortPayload)
-- — malformed/obsolete jsonb already sitting in a row must fail closed
-- there, not be silently reinterpreted.
--
-- is_default doubles as "the view to auto-select on load" (POST .../select
-- sets it true on exactly one row per owner and false on the rest,
-- transactionally) — this is what makes the selected view reload-safe
-- without any client-side storage being authoritative.

create table if not exists public.shopping_list_saved_views (
  id         uuid primary key default gen_random_uuid(),
  owner_id   uuid not null references auth.users(id) on delete cascade,
  name       text not null check (length(trim(name)) > 0),
  filters    jsonb not null default '{}'::jsonb,
  sort       jsonb not null default '{}'::jsonb,
  is_default boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint shopping_list_saved_views_owner_name_unique unique (owner_id, name)
);

comment on table public.shopping_list_saved_views is 'Shopping List Workbench — server-backed saved filter/sort views, one Captain-owned set per owner_id. Supersedes the old client-only localStorage saved-views control.';

-- At most one default (auto-selected) view per owner.
create unique index if not exists shopping_list_saved_views_one_default_per_owner
  on public.shopping_list_saved_views (owner_id)
  where is_default;

create index if not exists shopping_list_saved_views_owner_id_idx
  on public.shopping_list_saved_views (owner_id);

alter table public.shopping_list_saved_views enable row level security;

-- Ownership-scoped policies (deliberately narrower than 0199's `using
-- (true)` — see header comment above).
create policy "own_select" on public.shopping_list_saved_views
  for select to authenticated
  using (owner_id = auth.uid());

create policy "own_insert" on public.shopping_list_saved_views
  for insert to authenticated
  with check (owner_id = auth.uid());

create policy "own_update" on public.shopping_list_saved_views
  for update to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

create policy "own_delete" on public.shopping_list_saved_views
  for delete to authenticated
  using (owner_id = auth.uid());
