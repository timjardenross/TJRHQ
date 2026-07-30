import { createClient, type SupabaseClient } from '@supabase/supabase-js';

/**
 * Service-role Supabase client — SERVER-ONLY. Never import this from a
 * 'use client' file or any code path reachable from the browser.
 *
 * Required for any core_events write: that table has RLS enabled with zero
 * anon/authenticated policies (migration 0055, "service_role bypasses; no
 * public read/write") — the browser anon client and the cookie-based SSR
 * client from supabase-server.ts are both silently denied.
 *
 * Throws if SUPABASE_SERVICE_ROLE_KEY is missing rather than degrading to
 * the anon key. Callers publishing to core_events should go through
 * publishEventServerSide()/publishMissionEventServerSide() in core-events.ts,
 * which catch this and log it — a misconfigured env var becomes an
 * observable log line, not a second copy of the silent-failure bug this
 * module exists to fix.
 */
export function createSupabaseServiceRoleClient(): SupabaseClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error(
      'createSupabaseServiceRoleClient: SUPABASE_SERVICE_ROLE_KEY or NEXT_PUBLIC_SUPABASE_URL not set.',
    );
  }
  return createClient(url, key);
}
