create table if not exists public.pain_recovery_consents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade unique,
  version text not null default '1.0',
  status text not null default 'withdrawn' check (status in ('granted','withdrawn')),
  main_consent boolean not null default false,
  free_text_consent boolean not null default false,
  medications_consent boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.pain_recovery_consents enable row level security;
drop policy if exists pain_recovery_consents_select_own on public.pain_recovery_consents;
drop policy if exists pain_recovery_consents_insert_own on public.pain_recovery_consents;
drop policy if exists pain_recovery_consents_update_own on public.pain_recovery_consents;
create policy pain_recovery_consents_select_own on public.pain_recovery_consents for select using (auth.uid() = user_id);
create policy pain_recovery_consents_insert_own on public.pain_recovery_consents for insert with check (auth.uid() = user_id);
create policy pain_recovery_consents_update_own on public.pain_recovery_consents for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
