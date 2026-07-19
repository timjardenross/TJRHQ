import type { SupabaseClient } from '@supabase/supabase-js';

export interface SessionBoundary {
  /** ISO timestamp of the Captain's previous Home visit, or null if this is the first ever. */
  lastViewedAt: string | null;
  isFirstSessionToday: boolean;
  /** Whole days since the previous visit, 0 if same-day, null if no prior visit. */
  daysSinceLastSession: number | null;
}

/** Reads the prior visit boundary, then records this visit. Order matters -
 * read before write, so "since" never includes the current page load. */
export async function recordAndGetLastSession(supabase: SupabaseClient): Promise<SessionBoundary> {
  let lastViewedAt: string | null = null;
  try {
    const { data } = await supabase
      .from('home_sessions')
      .select('viewed_at')
      .order('viewed_at', { ascending: false })
      .limit(1);
    lastViewedAt = data?.[0]?.viewed_at ?? null;
  } catch {
    lastViewedAt = null;
  }

  try {
    await supabase.from('home_sessions').insert({});
  } catch {
    // Best-effort - a failed session write must not block Home from rendering.
  }

  if (!lastViewedAt) {
    return { lastViewedAt: null, isFirstSessionToday: true, daysSinceLastSession: null };
  }

  const last = new Date(lastViewedAt);
  const now = new Date();
  const lastDay = new Date(last.getFullYear(), last.getMonth(), last.getDate());
  const nowDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const daysSinceLastSession = Math.round((nowDay.getTime() - lastDay.getTime()) / 86_400_000);

  return {
    lastViewedAt,
    isFirstSessionToday: daysSinceLastSession >= 1,
    daysSinceLastSession,
  };
}
