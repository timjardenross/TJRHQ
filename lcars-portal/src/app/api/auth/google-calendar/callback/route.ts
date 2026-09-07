// Google Calendar OAuth callback. Matches the redirect URI registered on
// the Google Cloud OAuth client (docs/LifeOS-Wall-Tablet-V1-Component-Scope.md
// §2.7): https://usstjros.vercel.app/api/auth/google-calendar/callback.
//
// Exchanges the auth code for tokens and stores the refresh token
// server-side (google-calendar.ts / google_calendar_tokens table). This
// route runs under normal Captain login — the kiosk never reaches it.

import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { exchangeCodeAndStore } from '@/lib/google-calendar';

const STATE_COOKIE = 'gcal_oauth_state';

export async function GET(request: Request) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated.' }, { status: 401 });
  }

  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const oauthError = url.searchParams.get('error');
  const expectedState = request.headers
    .get('cookie')
    ?.split('; ')
    .find((c) => c.startsWith(`${STATE_COOKIE}=`))
    ?.split('=')[1];

  const redirectTo = (status: 'connected' | 'error', detail?: string) => {
    const dest = new URL('/', url.origin);
    dest.searchParams.set('google_calendar', status);
    if (detail) dest.searchParams.set('detail', detail);
    const response = NextResponse.redirect(dest);
    response.cookies.delete(STATE_COOKIE);
    return response;
  };

  if (oauthError) {
    return redirectTo('error', oauthError);
  }
  if (!code || !state || !expectedState || state !== expectedState) {
    return redirectTo('error', 'invalid_state');
  }

  try {
    await exchangeCodeAndStore(code);
  } catch (err) {
    console.error('[google-calendar/callback] token exchange failed:', err);
    return redirectTo('error', 'token_exchange_failed');
  }

  return redirectTo('connected');
}
