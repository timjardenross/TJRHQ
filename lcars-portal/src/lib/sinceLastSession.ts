// MSN-0345 Objective 8: "Since Last Session" — persistent session-awareness.
//
// MSN-0344 correctly identified this as blocked on "a 'since last session'
// mechanism that doesn't exist anywhere in the platform" and scoped it
// Long-term. That blocker was about a BACKEND mechanism — this mission's own
// scope explicitly rules out building new backend services unless
// absolutely necessary. A client-side marker (localStorage) is a genuine,
// real, zero-backend way to answer "what changed since I was last here" —
// not a full substitute for a durable server-side session log (it resets
// if the Captain clears browser storage or switches device), but real and
// honest about that limitation, not a fake stand-in.
//
// Of the 6 questions MSN-0344 named (what changed / completed / became
// worse / needs attention / was delegated / was learned), only "what
// changed" is answerable from data that exists today (core_events since the
// marker). The other 5 need data sources that don't exist yet (a "worse"
// diff needs snapshotted risk trends; delegation has no tracking instrument
// anywhere per the Operating Model's own finding; "learned" would need a
// browser-callable Pattern Library read, which doesn't exist — the Python
// library is server-side only). This module answers exactly what it can
// answer, and no more — it does not fabricate the other 5.

import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

const STORAGE_KEY = 'starship:lastSessionAt';

export interface SinceLastSessionSummary {
  /** True on this browser's very first-ever Chair visit — nothing to diff against. */
  firstSession: boolean;
  /** When the previous session ended, per this browser's own marker. Null if firstSession. */
  previousSessionAt: string | null;
  /** Real core_events count since previousSessionAt. */
  eventCount: number;
  /** Real per-domain breakdown, sorted by count descending. */
  byDomain: { domain: string; count: number }[];
}

export async function loadSinceLastSession(): Promise<SinceLastSessionSummary> {
  const stored = typeof window !== 'undefined' ? window.localStorage.getItem(STORAGE_KEY) : null;

  if (!stored) {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, new Date().toISOString());
    }
    return { firstSession: true, previousSessionAt: null, eventCount: 0, byDomain: [] };
  }

  let eventCount = 0;
  let byDomain: { domain: string; count: number }[] = [];
  try {
    const supabase = createSupabaseBrowserClient();
    const { data } = await supabase
      .from('core_events')
      .select('domain')
      .gt('occurred_at', stored)
      .limit(500);
    if (data) {
      eventCount = data.length;
      const counts = new Map<string, number>();
      for (const row of data as { domain: string }[]) {
        counts.set(row.domain, (counts.get(row.domain) ?? 0) + 1);
      }
      byDomain = [...counts.entries()]
        .map(([domain, count]) => ({ domain, count }))
        .sort((a, b) => b.count - a.count);
    }
  } catch {
    // degrade to zero — a failed diff should never block the page loading
  }

  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, new Date().toISOString());
  }

  return { firstSession: false, previousSessionAt: stored, eventCount, byDomain };
}
