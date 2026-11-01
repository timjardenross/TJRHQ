-- Migration 0196: user_settings (renumbered from 0189 by HQ V1 Integration QA §I10 —
-- see docs/architecture/HQ-V1-INTEGRATION-CONTRACTS.md; a second, unrelated file
-- also claimed 0189 first (0189_source_expansion_coverage_gap.sql, applied earlier
-- the same day) so this one moved to the next free number. Cosmetic only: Supabase
-- tracks the applied migration by its own timestamped version, not this filename.
--
-- TJR HQ Settings Page Redesign mission ("Settings vs Agent & Job Status"):
-- server-side storage for persistent HQ-behaviour preferences — the things
-- Settings answers ("How should HQ work for me?") as opposed to current
-- workbench state or job diagnostics. Single-row table (id = 'hq') since
-- this platform has one Captain — same reasoning as google_calendar_tokens
-- (migration 0183): no per-user keying needed for a single-tenant app.
--
-- One JSONB `data` column rather than a typed column per setting: Settings
-- is expected to grow/reshape section by section (mission phases 3-8), and
-- a JSONB blob lets the UI evolve without a migration per field. Consumers
-- (Next.js API routes, and the Python intelligence pipeline for the
-- Intelligence section's monitoring-category overlay) treat missing keys
-- as "use the default", never as an error — see lib/settings.ts and
-- intelligence/settings_store.py.
--
-- RLS enabled with zero policies for anon/authenticated, matching the
-- google_calendar_tokens / core_events pattern: service_role bypasses RLS
-- entirely, so this table is reachable only from the server-side
-- service-role client (Next.js API routes gated by requireSession(), and
-- the Python ingestion pipeline via SUPABASE_SERVICE_ROLE_KEY) — never the
-- browser or the SSR cookie-session client directly.

CREATE TABLE IF NOT EXISTS user_settings (
  id         text        PRIMARY KEY DEFAULT 'hq',
  data       jsonb       NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT user_settings_single_row CHECK (id = 'hq')
);

COMMENT ON TABLE user_settings IS 'Persistent Settings-page preferences (Appearance/HQ Behaviour/Follow-through/Intelligence monitoring/AI & Automation/Data & Privacy) for the single-Captain TJR HQ app. Service-role only. Current workbench state, connection credentials, and job diagnostics live elsewhere (google_calendar_tokens, domain_heartbeats, etc.) — this table is preferences only.';

ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;
