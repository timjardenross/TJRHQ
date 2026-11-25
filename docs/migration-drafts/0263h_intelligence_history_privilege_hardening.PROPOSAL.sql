-- PROPOSAL (WP11), NOT APPLIED. Least-privilege hardening for the product-history and delivery-attempt objects.
-- Source of the need: tests/test_wp11_cutover_db.py (effective-permission matrix on the production replica). On the hosted project the
-- default ACLs of the migration role give EVERY new table ALL privileges to authenticated and service_role and SELECT+MAINTAIN to anon;
-- 0263a/0264 revoke from anon/authenticated and then re-grant SELECT, but service_role keeps arwdDxtm (the append-only triggers are
-- then the only barrier), and intelligence_products itself still carries MAINTAIN for anon/authenticated (PostgreSQL 17 privilege that
-- also allows LOCK TABLE). Nothing in the application needs those privileges.
--
-- Minimum application roles (verified against the code that touches each table):
--   intelligence_products              service_role: SELECT, INSERT, UPDATE (writer; UPDATE only for the pre-0263b same-key overwrite)
--                                      authenticated: SELECT (portal, through RLS)            anon: nothing
--   intelligence_products_revisions    service_role: SELECT, INSERT (the archive trigger runs as the caller)   authenticated: SELECT
--   intelligence_product_refreshes     service_role: SELECT, INSERT                                           authenticated: SELECT
--   intelligence_products_current      service_role: SELECT (brief block)                    authenticated: SELECT (portal)
--   intelligence_delivery_attempts     service_role: SELECT, INSERT, UPDATE (conditional PATCH; the guard trigger limits UPDATE)
--                                      authenticated / anon: NOTHING. No portal or bot reads attempts as a signed-in user today (the
--                                      brief rows carry the rollup). Re-grant SELECT in the change that adds such a reader.
--   DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN: no application role, ever. (service_role never deletes a product row.)
--
-- Order-independent with 0263a/0263b/0263r/0264 (each statement is guarded by to_regclass and is idempotent); run it AFTER 0263a and
-- 0264 and re-run it after 0263r if 0263r was used (0263r re-creates the view with create or replace, which keeps grants).
-- Rollback: re-grant the privileges listed in the revoke statements (none is needed by any code path).

begin;
set local lock_timeout = '3s';
do $$
declare
    t text;
begin
    -- base table: signed-in users read only; nobody truncates, deletes or maintains it through the API roles
    if to_regclass('public.intelligence_products') is not null then
        revoke all on table public.intelligence_products from anon;
        revoke truncate, insert, update, delete, references, trigger, maintain on table public.intelligence_products from authenticated;
        revoke delete, truncate, references, trigger, maintain on table public.intelligence_products from service_role;
        grant select on table public.intelligence_products to authenticated;
        grant select, insert, update on table public.intelligence_products to service_role;
    end if;
    -- append-only history tables
    foreach t in array array['intelligence_products_revisions', 'intelligence_product_refreshes'] loop
        if to_regclass('public.' || t) is not null then
            execute format('revoke all on table public.%I from anon, authenticated, service_role', t);
            execute format('grant select on table public.%I to authenticated', t);
            execute format('grant select, insert on table public.%I to service_role', t);
        end if;
    end loop;
    -- current view (explicit grants for both reader roles; the Python brief reader uses service_role)
    if to_regclass('public.intelligence_products_current') is not null then
        revoke all on table public.intelligence_products_current from anon, authenticated, service_role;
        grant select on table public.intelligence_products_current to authenticated, service_role;
    end if;
    -- delivery attempts: service_role only
    if to_regclass('public.intelligence_delivery_attempts') is not null then
        revoke all on table public.intelligence_delivery_attempts from anon, authenticated, service_role;
        grant select, insert, update on table public.intelligence_delivery_attempts to service_role;
        drop policy if exists intel_delivery_attempts_read on public.intelligence_delivery_attempts;
    end if;
end $$;
commit;
