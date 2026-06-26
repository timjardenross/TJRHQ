'use client';

import { createBrowserClient } from '@supabase/ssr';

/**
 * Browser Supabase client.
 *
 * NEXT_PUBLIC_* values are inlined at build time. In a secret-free CI build they
 * are absent, and @supabase/ssr's createBrowserClient throws ("URL and API key
 * are required") during static prerender of any page that constructs the client
 * at render (e.g. /captains-notebook). We fall back to harmless placeholders so
 * the build succeeds; the placeholder client is never exercised during prerender
 * (data calls happen in effects/handlers at runtime), and any env-configured
 * deploy build inlines the real values. (USS-TJR-MSN-0100 deployment-readiness.)
 */
export function createSupabaseBrowserClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? 'http://localhost:54321';
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? 'public-anon-key-placeholder';
  return createBrowserClient(url, key);
}
