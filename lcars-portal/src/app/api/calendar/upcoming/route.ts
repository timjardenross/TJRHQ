// Read-only "upcoming events" endpoint (MSN-0364, Captain's Chair Ahead
// component) — separate from /api/calendar/today (which the wall-tablet
// kiosk panel already owns and this mission doesn't touch) since Ahead
// needs a wider default 24-48h horizon, not just today. Thin wrapper over
// the same lib/google-calendar.ts read path — no new calendar backend.

import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { fetchUpcomingEvents, GoogleCalendarDisconnectedError, type UpcomingCalendarEvent } from '@/lib/google-calendar';

const CACHE_TTL_MS = 5 * 60 * 1000;

let cache: { days: number; events: UpcomingCalendarEvent[]; cachedAt: number } | null = null;

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated.' }, { status: 401 });
  }

  const daysParam = Number(req.nextUrl.searchParams.get('days'));
  const days = Number.isFinite(daysParam) && daysParam > 0 && daysParam <= 14 ? daysParam : 2;

  if (cache && cache.days === days && Date.now() - cache.cachedAt < CACHE_TTL_MS) {
    return NextResponse.json({ status: 'ok', events: cache.events, cached: true });
  }

  try {
    const events = await fetchUpcomingEvents(days);
    cache = { days, events, cachedAt: Date.now() };
    return NextResponse.json({ status: 'ok', events, cached: false });
  } catch (err) {
    if (err instanceof GoogleCalendarDisconnectedError) {
      return NextResponse.json({ status: 'disconnected', message: err.message }, { status: 409 });
    }
    console.error('[calendar/upcoming] fetch failed:', err);
    return NextResponse.json({ status: 'error', message: 'Failed to load calendar.' }, { status: 502 });
  }
}
