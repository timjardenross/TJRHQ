-- Migration 0030: Quick Capture
-- MSN-C: Global rapid-entry captured_items table.
-- Supports note | mission | idea | health | decision routes.

CREATE TABLE IF NOT EXISTS public.captured_items (
  id           uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  text         text         NOT NULL,
  item_type    text         NOT NULL DEFAULT 'note'
                            CHECK (item_type IN ('note', 'mission', 'idea', 'health', 'decision')),
  source       text         NOT NULL DEFAULT 'command-centre',
  status       text         NOT NULL DEFAULT 'unrouted'
                            CHECK (status IN ('unrouted', 'routed', 'dismissed')),
  routed_to    text         NULL,   -- e.g. 'missions', 'decision_records', 'captains_log_entries'
  routed_id    uuid         NULL,   -- FK to the routed destination row
  captured_at  timestamptz  NOT NULL DEFAULT now(),
  routed_at    timestamptz  NULL,
  created_at   timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS captured_items_status_idx      ON public.captured_items (status);
CREATE INDEX IF NOT EXISTS captured_items_item_type_idx   ON public.captured_items (item_type);
CREATE INDEX IF NOT EXISTS captured_items_captured_at_idx ON public.captured_items (captured_at DESC);

-- RLS: Captain-only access
ALTER TABLE public.captured_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "captured_items_service_role_all"
  ON public.captured_items
  FOR ALL
  USING (auth.role() = 'service_role');
