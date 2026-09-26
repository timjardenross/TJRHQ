'use client';

import { createBrowserClient } from '@supabase/ssr';

// buildClient()'s body is the ORIGINAL, unmodified createSupabaseBrowserClient()
// implementation from before this file cached anything — kept as its own
// function specifically so `ReturnType<typeof buildClient>` below infers
// from ITS two concrete `createBrowserClient(...)` call sites, exactly as
// TypeScript did for the exported function before. Referencing
// `ReturnType<typeof createBrowserClient>` directly (the generic library
// function itself, uncalled) was tried first and silently changed that
// inferred type — with no explicit arguments to infer generics from, it
// resolves differently than an actual call does, which cascaded into
// ~30 new "implicitly has an 'any' type" errors across every file whose
// Supabase query result types trace back through this client (search,
// timeline, ask.ts, personalTasks.ts, etc.) — caught by `npm run build`'s
// full type-check, not by `next build`'s narrower/cached one. Keeping the
// type derived from an actual call, as here, reproduces the pre-existing
// inference exactly.
function buildClient() {
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

// Module-level singleton (2026-09-21, workbench-lag investigation): this
// used to construct a brand-new client on every call, and it's called
// fresh from a useEffect in ~64 places across the app — every workbench
// mount/navigation was creating its own GoTrueClient from scratch (its
// own session bootstrap/localStorage read/auto-refresh timer) before that
// component's first query could even fire, on top of supabase-js's own
// "Multiple GoTrueClient instances detected in the same browser context"
// warning for exactly this pattern. That's the "page shell loads, then a
// real wait before data starts coming in" lag reported live across
// workbenches. `createBrowserClient` is documented as safe, and intended,
// to be created once and reused (it's a thin wrapper holding one
// GoTrueClient + one PostgREST client) — caching it here doesn't change
// auth/session semantics or any call site's behaviour, every existing
// caller keeps the same signature.
//
// Not cached when env vars are missing (falls through to `buildClient()`
// again next call): a page hit before env vars are ready shouldn't poison
// every later call in the same tab if they do resolve.
let cachedClient: ReturnType<typeof buildClient> | undefined;

/**
 * Browser Supabase client.
 *
 * Requires NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
 * Pages that call this must handle a null return (data calls happen in
 * effects/handlers, never at static render time).
 * (USS-TJR-MSN-0100 deployment-readiness.)
 *
 * Returns the same cached instance on every call within this browser tab
 * — see the module-level comment above for why that matters for
 * navigation latency, not just tidiness.
 */
export function createSupabaseBrowserClient() {
  if (process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) {
    if (!cachedClient) cachedClient = buildClient();
    return cachedClient;
  }
  return buildClient();
}
