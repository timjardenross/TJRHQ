-- Migration 0237: allow source_type 'tjr_life_ios' on captured_items
--
-- Additive only. Needed by POST /api/integrations/tjr-life/v1/captures
-- (TJR-Life-iOS capture ingest, contract tjr-life-capture.v1). Without it every
-- insert from that route fails the CHECK and the route returns 503.
--
-- Fails closed: if the live constraint is not exactly the five values observed
-- on 2026-10-19, the migration aborts instead of silently widening or narrowing
-- an unexpected definition. Not run automatically; the owner decides when.

DO $$
DECLARE
  def text;
BEGIN
  SELECT pg_get_constraintdef(c.oid) INTO def
  FROM pg_constraint c
  WHERE c.conrelid = 'public.captured_items'::regclass
    AND c.conname = 'captured_items_source_type_check';

  IF def IS NULL THEN
    RAISE EXCEPTION '0237: captured_items_source_type_check not found; refusing to guess';
  END IF;

  IF def !~ 'channel_message' OR def !~ 'channel_file' OR def !~ 'telegram_voice'
     OR def !~ 'command_centre' OR def !~ 'portal_quick_capture'
     OR (length(def) - length(replace(def, '''::text', ''))) / length('''::text') <> 5 THEN
    RAISE EXCEPTION '0237: captured_items_source_type_check is not the expected five-value definition: %', def;
  END IF;

  ALTER TABLE public.captured_items DROP CONSTRAINT captured_items_source_type_check;
  ALTER TABLE public.captured_items
    ADD CONSTRAINT captured_items_source_type_check
    CHECK (source_type IN (
      'channel_message',
      'channel_file',
      'telegram_voice',
      'command_centre',
      'portal_quick_capture',
      'tjr_life_ios'
    ));
END $$;
