-- READ-ONLY verification of the read-only Supabase role posture. Safe to run (SELECT only) with either MCP server.
-- Expected results are in the comment on each line. Re-run after any GRANT, new SECURITY DEFINER function, or Supabase role change.
select 'role_settings' as check, coalesce(array_to_string(s.setconfig, ' ; '), '(none)') as value, 'must contain default_transaction_read_only=on' as expected
from pg_roles r left join pg_db_role_setting s on s.setrole = r.oid where r.rolname = 'supabase_read_only_user'
union all
select 'direct_write_privileges_on_tables', count(*)::text, '0'
from information_schema.role_table_grants g where g.grantee = 'supabase_read_only_user' and g.privilege_type in ('INSERT','UPDATE','DELETE','TRUNCATE')
union all
select 'schemas_it_can_create_in', count(*)::text, '0'
from pg_namespace n where has_schema_privilege('supabase_read_only_user', n.oid, 'create') and n.nspname not like 'pg_%' and n.nspname <> 'information_schema'
union all
-- The residual risk in tests/test_supabase_ro_access.py: a SECURITY DEFINER function it can execute that writes.
select 'secdef_functions_executable_non_system', coalesce(string_agg(n.nspname || '.' || p.proname, ', '), '0'), '0 (empty)'
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where p.prosecdef and n.nspname not in ('pg_catalog','information_schema') and has_function_privilege('supabase_read_only_user', p.oid, 'execute')
union all
select 'is_superuser_or_bypass_via_membership', (rolsuper::text || ' / member_of=' || coalesce((select string_agg(b.rolname, ',' order by b.rolname) from pg_auth_members m join pg_roles b on b.oid = m.roleid where m.member = r.oid), '')), 'false / member_of=pg_monitor,pg_read_all_data'
from pg_roles r where r.rolname = 'supabase_read_only_user'
union all
select 'vault_secrets_rows', (select count(*) from vault.secrets)::text, '0 today (readable through the view if ever non-zero; the scope hook refuses vault.*)';
