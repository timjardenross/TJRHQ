'use server';

import { createServerClient } from '@supabase/ssr';
import { cookies } from 'next/headers';

export async function createSupabaseServerClient() {
  const cookieStore = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            );
          } catch {}
        },
      },
    }
  );
}

/** Real Captain session or null. Single-tenant app - any authenticated
 * session is the Captain - but a route with no session check at all is
 * reachable by anyone (WORKBENCH-REVIEW.md, 2026-07-18: found on 9 routes
 * that either mutated state, ran an expensive LLM/subprocess call, or read
 * Captain-only content with no gate beyond middleware.ts's page-level
 * redirect, which a direct API hit bypasses entirely). */
export async function requireSession() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;
  const { data: { session } } = await supabase.auth.getSession();
  return session;
}
