'use client';

import { createBrowserClient } from '@supabase/ssr';

/**
 * Browser Supabase client.
 *
 * Requires NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
 * Pages that call this must handle a null return (data calls happen in
 * effects/handlers, never at static render time).
 * (USS-TJR-MSN-0100 deployment-readiness.)
 */
export function createSupabaseBrowserClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    console.warn('[supabase-browser] NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY not set — Supabase calls will fail.');
    // Return a non-functional placeholder client so pages don't crash at render.
    // All data fetches are in useEffect / event handlers, so this is safe.
    return createBrowserClient('http://localhost:54321', 'placeholder');
  }
  return createBrowserClient(url, key);
}
