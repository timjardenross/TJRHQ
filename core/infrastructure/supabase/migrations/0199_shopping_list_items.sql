-- Shopping List Workbench: shopping_list_items — manual-priority wishlist/
-- gift-tracking table for the single-Captain app. Simple CRUD list, same
-- shape as personal_tasks (migration 0090) but for things to buy rather
-- than things to do.
--
-- category is free text, not an enum: personal_tasks.category is a typed
-- union (TaskCategory in lib/personalTasks.ts) but is enforced entirely at
-- the application layer, not a Postgres CHECK/enum — no table in this repo
-- enforces a "category"-shaped free-text field with a DB-level enum, so
-- free text (validated app-side later if it ever needs to be) matches
-- existing convention.
--
-- No dedicated priority/rank/order column exists anywhere else in this repo
-- to mirror (personal_tasks uses a boolean pinned_today + algorithmic
-- scoring in rankToday(), not a manually-dragged integer rank — see
-- lib/personalTasks.ts). priority_rank here is a plain integer manual
-- ordering column, the simplest form for a drag-to-reorder list; the
-- reorder endpoint (lib/shoppingList.ts's reorderItems()) is a new pattern
-- for this repo, not a mirror of an existing one.
--
-- RLS matches current convention (0193_missions_authenticated_rls.sql):
-- enabled, one policy per operation granted to `authenticated` only, no
-- anon access, unrestricted `using (true)`/`with check (true)` since this
-- is a single-Captain app with no per-row ownership to filter by. All
-- access goes through session-gated Next.js API routes
-- (lcars-portal/src/app/api/shopping-list/*, requireSession()).

create table if not exists public.shopping_list_items (
  id             uuid primary key default gen_random_uuid(),
  product_name   text not null,
  vendor         text,
  image_url      text,
  source_url     text,
  cost           numeric not null,
  currency       text not null default 'AUD',
  category       text not null,
  recipient      text,
  priority_rank  integer not null,
  status         text not null default 'wishlist'
                   check (status in ('wishlist', 'saved_for', 'purchased', 'cancelled')),
  target_occasion text,
  notes          text,
  purchased_at   timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

comment on table public.shopping_list_items is 'Shopping List Workbench — single-Captain wishlist/gift tracker. Manual priority via priority_rank; no budget, recurring-payment, or cross-currency logic (deliberately out of scope for v1).';

alter table public.shopping_list_items enable row level security;

create policy "authenticated_select" on public.shopping_list_items
  for select to authenticated
  using (true);

create policy "authenticated_insert" on public.shopping_list_items
  for insert to authenticated
  with check (true);

create policy "authenticated_update" on public.shopping_list_items
  for update to authenticated
  using (true)
  with check (true);

create policy "authenticated_delete" on public.shopping_list_items
  for delete to authenticated
  using (true);

create index if not exists shopping_list_items_priority_rank_idx on public.shopping_list_items (priority_rank);
create index if not exists shopping_list_items_status_idx on public.shopping_list_items (status);
