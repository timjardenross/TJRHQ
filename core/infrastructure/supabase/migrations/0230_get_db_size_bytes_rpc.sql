-- 0230_get_db_size_bytes_rpc.sql
-- USS-TJR-MSN-0412 Stream 4, step 3. The weekly report line and the 450 MB
-- warning need the database size, and pg_database_size() is not reachable
-- through PostgREST tables. This is a read-only RPC that returns one number.
--
-- Locked down: security definer with an empty search_path, executable by
-- service_role only (the key intelligence/ already uses), not by anon or
-- authenticated.
--
-- ROLLBACK:
--   drop function if exists public.get_db_size_bytes();

create or replace function public.get_db_size_bytes()
returns bigint
language sql
stable
security definer
set search_path = ''
as $$
  select pg_catalog.pg_database_size(pg_catalog.current_database());
$$;

revoke all on function public.get_db_size_bytes() from public, anon, authenticated;
grant execute on function public.get_db_size_bytes() to service_role;
