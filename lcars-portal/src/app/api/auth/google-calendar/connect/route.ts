// Starts the Google Calendar OAuth consent flow. LifeOS Wall Tablet §2.7
// step 1: "done by the Captain, not the kiosk" — this route sits behind
// normal Captain login (requireSession), not the kiosk device identity,
// which doesn't exist yet and never gets Google scope regardless.

import { NextResponse } from 'next/server';
import { randomBytes } from 'crypto';
import { requireSession } from '@/lib/supabase-server';
import { buildGoogleAuthUrl } from '@/lib/google-calendar';

const STATE_COOKIE = 'gcal_oauth_state';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated.' }, { status: 401 });
  }

  const state = randomBytes(24).toString('hex');
  const authUrl = buildGoogleAuthUrl(state);

  const response = NextResponse.redirect(authUrl);
  response.cookies.set(STATE_COOKIE, state, {
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    maxAge: 600, // 10 minutes — long enough for the consent redirect round trip
    path: '/api/auth/google-calendar',
  });
  return response;
}
