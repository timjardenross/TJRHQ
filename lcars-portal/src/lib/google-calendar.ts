// Google Calendar integration — server-only. LifeOS Wall Tablet §2.7
// (docs/LifeOS-Wall-Tablet-V1-Component-Scope.md).
//
// Trust boundary: the kiosk never holds Google credentials and never talks
// to Google directly. This module is the only thing that does — it reads
// the stored refresh token via the service-role client, exchanges it for a
// short-lived access token when needed, and calls the Calendar API. Callers
// (the /api/calendar/today route) get back normalized events, never a raw
// token.

import { createSupabaseServiceRoleClient as createServiceRoleClient } from '@/lib/supabase-service-role';

const TOKEN_ROW_ID = 'google_calendar';
const OAUTH_TOKEN_URL = 'https://oauth2.googleapis.com/token';
const CALENDAR_EVENTS_URL = (calendarId: string) =>
  `https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(calendarId)}/events`;
const TIMEZONE = 'Australia/Brisbane';

export const GOOGLE_CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.readonly';

export class GoogleCalendarDisconnectedError extends Error {
  constructor(message = 'Google Calendar is not connected.') {
    super(message);
    this.name = 'GoogleCalendarDisconnectedError';
  }
}

interface TokenRow {
  calendar_id: string;
  refresh_token: string;
  access_token: string | null;
  access_token_expires_at: string | null;
}

export interface CalendarEvent {
  time: string | null; // null for all-day events
  title: string;
  location: string | null;
  allDay: boolean;
}

function requireOAuthEnv() {
  const clientId = process.env.GOOGLE_CALENDAR_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_CALENDAR_CLIENT_SECRET;
  const redirectUri = process.env.GOOGLE_CALENDAR_REDIRECT_URI;
  if (!clientId || !clientSecret || !redirectUri) {
    throw new Error(
      'GOOGLE_CALENDAR_CLIENT_ID / GOOGLE_CALENDAR_CLIENT_SECRET / GOOGLE_CALENDAR_REDIRECT_URI not set.'
    );
  }
  return { clientId, clientSecret, redirectUri };
}

export function buildGoogleAuthUrl(state: string): string {
  const { clientId, redirectUri } = requireOAuthEnv();
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: GOOGLE_CALENDAR_SCOPE,
    access_type: 'offline',
    prompt: 'consent',
    state,
  });
  return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

/** Exchanges an OAuth `code` for tokens and stores the refresh token. Called
 * once, from the callback route, under normal Captain login — never from
 * the kiosk. */
export async function exchangeCodeAndStore(code: string): Promise<void> {
  const { clientId, clientSecret, redirectUri } = requireOAuthEnv();

  const res = await fetch(OAUTH_TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      code,
      client_id: clientId,
      client_secret: clientSecret,
      redirect_uri: redirectUri,
      grant_type: 'authorization_code',
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Google token exchange failed (${res.status}): ${body}`);
  }

  const data = (await res.json()) as {
    access_token: string;
    expires_in: number;
    refresh_token?: string;
  };

  if (!data.refresh_token) {
    // Google omits refresh_token on repeat consent unless prompt=consent
    // forced a fresh grant (which buildGoogleAuthUrl always sets) — treat a
    // missing one here as a real failure rather than silently keeping a
    // stale/absent token.
    throw new Error(
      'Google did not return a refresh_token. Revoke prior access at ' +
        'https://myaccount.google.com/permissions and reconnect.'
    );
  }

  const supabase = createServiceRoleClient();
  const expiresAt = new Date(Date.now() + data.expires_in * 1000).toISOString();
  const { error } = await supabase.from('google_calendar_tokens').upsert({
    id: TOKEN_ROW_ID,
    calendar_id: 'primary',
    refresh_token: data.refresh_token,
    access_token: data.access_token,
    access_token_expires_at: expiresAt,
    updated_at: new Date().toISOString(),
  });
  if (error) {
    throw new Error(`Failed to store Google Calendar token: ${error.message}`);
  }
}

async function loadTokenRow(): Promise<TokenRow | null> {
  const supabase = createServiceRoleClient();
  const { data, error } = await supabase
    .from('google_calendar_tokens')
    .select('calendar_id, refresh_token, access_token, access_token_expires_at')
    .eq('id', TOKEN_ROW_ID)
    .maybeSingle();
  if (error) {
    throw new Error(`Failed to read Google Calendar token: ${error.message}`);
  }
  return data as TokenRow | null;
}

async function refreshAccessToken(row: TokenRow): Promise<string> {
  const { clientId, clientSecret } = requireOAuthEnv();

  const res = await fetch(OAUTH_TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      refresh_token: row.refresh_token,
      client_id: clientId,
      client_secret: clientSecret,
      grant_type: 'refresh_token',
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    // invalid_grant means the refresh token was revoked/expired — this is
    // the "reconnect in settings" case §2.7 requires the endpoint to
    // surface explicitly, not mask as an empty panel.
    if (res.status === 400 && body.includes('invalid_grant')) {
      throw new GoogleCalendarDisconnectedError(
        'Google Calendar access was revoked or expired. Reconnect required.'
      );
    }
    throw new Error(`Google token refresh failed (${res.status}): ${body}`);
  }

  const data = (await res.json()) as { access_token: string; expires_in: number };

  const supabase = createServiceRoleClient();
  const expiresAt = new Date(Date.now() + data.expires_in * 1000).toISOString();
  await supabase
    .from('google_calendar_tokens')
    .update({ access_token: data.access_token, access_token_expires_at: expiresAt, updated_at: new Date().toISOString() })
    .eq('id', TOKEN_ROW_ID);

  return data.access_token;
}

async function getValidAccessToken(): Promise<{ accessToken: string; calendarId: string }> {
  const row = await loadTokenRow();
  if (!row) {
    throw new GoogleCalendarDisconnectedError();
  }

  const expiresAt = row.access_token_expires_at ? new Date(row.access_token_expires_at).getTime() : 0;
  const stillValid = row.access_token && expiresAt - Date.now() > 60_000; // 60s safety margin

  const accessToken = stillValid ? row.access_token! : await refreshAccessToken(row);
  return { accessToken, calendarId: row.calendar_id };
}

function todayWindow(): { timeMin: string; timeMax: string } {
  const todayStr = new Date().toLocaleDateString('en-CA', { timeZone: TIMEZONE });
  const start = new Date(`${todayStr}T00:00:00+10:00`); // AEST — Brisbane has no DST
  const end = new Date(`${todayStr}T23:59:59+10:00`);
  return { timeMin: start.toISOString(), timeMax: end.toISOString() };
}

/** Fetches today's events, normalized to §2.7's `{time, title, location}`
 * shape. Throws GoogleCalendarDisconnectedError if no token is stored or
 * the refresh token was revoked — callers must surface that distinctly,
 * not as an empty list. */
export async function fetchTodayEvents(): Promise<CalendarEvent[]> {
  const { accessToken, calendarId } = await getValidAccessToken();
  const { timeMin, timeMax } = todayWindow();

  const params = new URLSearchParams({
    timeMin,
    timeMax,
    singleEvents: 'true',
    orderBy: 'startTime',
    timeZone: TIMEZONE,
  });

  const res = await fetch(`${CALENDAR_EVENTS_URL(calendarId)}?${params.toString()}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (res.status === 401) {
    throw new GoogleCalendarDisconnectedError('Google Calendar access token was rejected. Reconnect required.');
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Google Calendar events fetch failed (${res.status}): ${body}`);
  }

  const data = (await res.json()) as {
    items?: Array<{
      summary?: string;
      location?: string;
      start?: { dateTime?: string; date?: string };
    }>;
  };

  return (data.items ?? []).map((item) => {
    const allDay = !item.start?.dateTime;
    const time = item.start?.dateTime
      ? new Date(item.start.dateTime).toLocaleTimeString('en-AU', {
          hour: '2-digit',
          minute: '2-digit',
          timeZone: TIMEZONE,
        })
      : null;
    return {
      time,
      title: item.summary || '(no title)',
      location: item.location ?? null,
      allDay,
    };
  });
}
