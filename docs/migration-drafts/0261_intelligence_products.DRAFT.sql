-- DRAFT, NOT APPLIED. Lives outside core/infrastructure/supabase/migrations on purpose so no deploy path picks it up.
-- Persistence for the weekly intelligence products (recurring provider, systemic view, forward watch).
-- Written by intelligence/intel_products_job.py (service role) only when INTEL_PRODUCTS_ENABLED=1.
-- Read by lcars-portal /api/intelligence-workbench/products through the signed-in user's client.
-- Check the number 0261 is free before filing (grep core/infrastructure/supabase/migrations).

create table if not exists public.intelligence_products (
    product_key   text        not null check (product_key in ('recurring_provider','systemic_risk','forward_watch')),
    generated_for date        not null,
    as_of         timestamptz not null,
    title         text        not null,
    summary       text        not null,
    -- {confirmed_evidence:[], analytical_inference:[], potential_exposure:[], unknowns:[]}
    sections      jsonb       not null,
    -- [{dedupe_key, title, detail, severity, evidence_ids, due_date?}]; dedupe_key is stable per ISO week / event
    exceptions    jsonb       not null default '[]'::jsonb,
    body_md       text        not null,
    created_at    timestamptz not null default now(),
    primary key (product_key, generated_for)
);

alter table public.intelligence_products enable row level security;

-- Single-user platform: authenticated users read; only the service role writes (no insert/update policy).
create policy intelligence_products_read on public.intelligence_products
    for select to authenticated using (true);

-- Rollback: drop table public.intelligence_products;
