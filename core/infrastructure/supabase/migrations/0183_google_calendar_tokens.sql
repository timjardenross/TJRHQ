-- Migration 0183: google_calendar_tokens
--
-- LifeOS Wall Tablet §2.7 (docs/LifeOS-Wall-Tablet-V1-Component-Scope.md):
-- server-side storage for the Google Calendar OAuth refresh token backing
-- the wall-tablet calendar panel. Single-row table (id = 'google_calendar')
-- since this platform has one Captain and one "life calendar" — no per-user
-- keying needed.
--
-- RLS enabled with zero policies for anon/authenticated, matching the
-- core_events pattern documented in src/lib/supabase-service-role.ts:
-- service_role bypasses RLS entirely, so this table is reachable only from
-- the server-side service-role client, never the browser or the SSR
-- cookie-session client. The refresh token is a durable credential — same
-- trust boundary as Home Assistant holding the Kasa/Sensibo vendor secrets
-- instead of the kiosk holding them (§2.3/§2.7).

CREATE TABLE IF NOT EXISTS google_calendar_tokens (
  id                     text        PRIMARY KEY DEFAULT 'google_calendar',
  calendar_id            text        NOT NULL DEFAULT 'primary',
  refresh_token          text        NOT NULL,
  access_token           text,
  access_token_expires_at timestamptz,
  connected_at           timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT google_calendar_tokens_single_row CHECK (id = 'google_calendar')
);

COMMENT ON TABLE google_calendar_tokens IS 'Google Calendar OAuth refresh/access token for the wall-tablet calendar panel (LifeOS Wall Tablet V1 §2.7). Service-role only — never exposed to the browser or the kiosk device identity.';

ALTER TABLE google_calendar_tokens ENABLE ROW LEVEL SECURITY;
