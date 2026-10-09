-- Revert the out-of-band `0226_decisions_command_memory_columns` change to
-- public.decisions.
--
-- That migration was applied straight to prod (schema_migrations version
-- 20260927074221) with no file in the repo and no sign-off. It was the
-- rejected "Option B" for the /rest/v1/decisions 400s: it changed
-- decisions.id from uuid to text and bolted the original Command Memory
-- columns (statement, rationale, owner, status, created_by, created_at,
-- updated_at, updated_by, alternatives) onto decisions. The approved fix
-- (0224, PR #321) gave those callers their own table,
-- command_memory_records, instead.
--
-- Leaving 0226 in place would mean any key-value caller the #321 repoint
-- missed silently writes into decisions instead of failing loudly, and it
-- repeats the schema drift that caused the 400s in the first place.
--
-- Pre-checks run against prod before writing this (2026-09-27):
--   * 65 rows; none has data in any added column except created_at,
--     which is exactly the 0226 backfill of "timestamp".
--   * every id matches the uuid format, so the cast back is lossless.
--   * no views, functions or foreign keys depend on decisions.
--   * nothing on main reads the added columns: every remaining decisions
--     reader selects id / mission_id / decision_type / reasoning / outcome /
--     timestamp / outcome_quality only.
--
-- Applied to prod 2026-09-27 as schema_migrations version 20260927080834
-- under this file's name. The 0225 prefix is shared with
-- 0225_intelligence_events_canonical_url_index (a concurrent session,
-- applied the same day); the name was kept so the file matches the
-- applied migration exactly.

DROP INDEX IF EXISTS public.idx_decisions_owner;
DROP INDEX IF EXISTS public.idx_decisions_created_at;

ALTER TABLE public.decisions
  DROP COLUMN IF EXISTS statement,
  DROP COLUMN IF EXISTS rationale,
  DROP COLUMN IF EXISTS owner,
  DROP COLUMN IF EXISTS status,
  DROP COLUMN IF EXISTS created_by,
  DROP COLUMN IF EXISTS created_at,
  DROP COLUMN IF EXISTS updated_at,
  DROP COLUMN IF EXISTS updated_by,
  DROP COLUMN IF EXISTS alternatives;

ALTER TABLE public.decisions ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.decisions ALTER COLUMN id TYPE uuid USING id::uuid;
ALTER TABLE public.decisions ALTER COLUMN id SET DEFAULT gen_random_uuid();

NOTIFY pgrst, 'reload schema';
