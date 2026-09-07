// Read-only "today's events" endpoint for the wall-tablet calendar panel.
// LifeOS Wall Tablet §2.7 step 3/4: the kiosk calls this, never Google
// directly. Caches server-side for ~5 minutes so kiosk polling never hits
// Google's API on every request.
//
// Gated the same way every other route here is (requireSession, per
// supabase-server.ts's note that middleware.ts's redirect is a page-level
// behavior an API caller can bypass entirely) — once the kiosk device
// identity from §2.5/§4 exists, that identity calls this route too; it
// doesn't change this route's contract, since it's read-only regardless of
// which authenticated caller hits it.

import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { fetchTodayEvents, GoogleCalendarDisconnectedError, type CalendarEvent } from '@/lib/google-calendar';

const CACHE_TTL_MS = 5 * 60 * 1000;

let cache: { day: string; events: CalendarEvent[]; cachedAt: number } | null = null;

function todayKey(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Australia/Brisbane' });
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated.' }, { status: 401 });
  }

  const day = todayKey();
  if (cache && cache.day === day && Date.now() - cache.cachedAt < CACHE_TTL_MS) {
    return NextResponse.json({ status: 'ok', events: cache.events, cached: true });
  }

  try {
    const events = await fetchTodayEvents();
    cache = { day, events, cachedAt: Date.now() };
    return NextResponse.json({ status: 'ok', events, cached: false });
  } catch (err) {
    if (err instanceof GoogleCalendarDisconnectedError) {
      // Explicit disconnected state, not a silently empty/stale panel —
      // required by §2.7's failure-handling note and §5's stale-data
      // principle.
      return NextResponse.json(
        { status: 'disconnected', message: err.message },
        { status: 409 }
      );
    }
    console.error('[calendar/today] fetch failed:', err);
    return NextResponse.json({ status: 'error', message: 'Failed to load calendar.' }, { status: 502 });
  }
}
