-- pause_github_status_20261124.sql  --  NOT EXECUTED. Optional DB-level pause of the "GitHub Status" source.
-- The pause already works without this: intelligence/config.py DEFAULT_PAUSED_SOURCE_NAMES makes collect_all() skip
-- the source. Run this only if the Captain also wants active=false in the registry. No rows are deleted.
--
-- Pause:
begin;
create table if not exists intelligence_source_registry_backup_20261124 (like intelligence_source_registry including defaults);
alter table intelligence_source_registry_backup_20261124 enable row level security;
insert into intelligence_source_registry_backup_20261124
select * from intelligence_source_registry where source_name = 'GitHub Status';
update intelligence_source_registry set active = false where source_name = 'GitHub Status';
commit;

-- Reinstate (restores the exact prior value from the backup):
--   update intelligence_source_registry r set active = b.active
--   from intelligence_source_registry_backup_20261124 b where r.source_name = b.source_name;
-- The backup table is safe to drop once the source is reinstated.
-- Note: tools/intelligence/seed_source_registry.py still lists the row active=True and was left unchanged.
