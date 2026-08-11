-- Fix: source_registry_by_tier view ran as SECURITY DEFINER (view owner),
-- bypassing the anon_read RLS policy on intelligence_source_registry
-- (migration 0035) for the querying user. Flip to SECURITY INVOKER so the
-- view enforces the underlying table's RLS instead of the owner's grants.
-- Flagged by Supabase security advisor (rule 0010_security_definer_view).

ALTER VIEW source_registry_by_tier SET (security_invoker = true);
