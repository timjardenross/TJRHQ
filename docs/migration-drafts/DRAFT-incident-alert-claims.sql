-- DRAFT, NOT APPLIED. Do not run without Captain approval. Applies AFTER DRAFT-incident-alert-state.sql (already in production).
-- Adds what intelligence/alert_store.py needs: per-kind claim columns for atomic claim-before-send, a test-send column, and the 'test'
-- ledger mode used by `python -m intelligence.alert_dispatcher --controlled-test`.
-- Rollback: alter table public.incident_alert_state drop column ...(each below); restore the original mode check.
-- Number is deliberately not assigned: take the next free one in core/infrastructure/supabase/migrations/ when approved.

alter table public.incident_alert_state
    add column if not exists alert_claimed_at         timestamptz,
    add column if not exists alert_claim_token        text,
    add column if not exists restoration_claimed_at   timestamptz,
    add column if not exists restoration_claim_token  text,
    add column if not exists test_sent_at             timestamptz,   -- controlled-test alert only (key 'test-alert-path'); never a real incident
    add column if not exists test_claimed_at          timestamptz,
    add column if not exists test_claim_token         text;

alter table public.incident_alert_sends drop constraint if exists incident_alert_sends_mode_check;
alter table public.incident_alert_sends add constraint incident_alert_sends_mode_check check (mode in ('real','dry','test'));
