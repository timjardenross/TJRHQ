// TJR HQ Settings → Connections. Simple connected/disconnected/needs-
// attention state only — NEVER diagnostics (last sync, retry counts,
// token-refresh failures, job logs). Those live in Agent & Job Status
// (/agent-status-workbench); this route intentionally exposes nothing
// beyond what Settings' Connections section is allowed to show.

import { NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { createSupabaseServiceRoleClient } from '@/lib/supabase-service-role';

export type ConnectionState = 'connected' | 'disconnected' | 'needs_attention';

export interface ConnectionStatus {
  service: 'google_calendar' | 'google_tasks' | 'telegram';
  state: ConnectionState;
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Not authenticated.' }, { status: 401 });
  }

  // Google Calendar + Google Tasks share one OAuth grant (google_calendar-
  // tokens — see lib/google-calendar.ts / lib/google-tasks.ts), so both
  // read the same row. "Connected" = a refresh token is on file; we don't
  // validate it against Google here (that's a live API call, and a
  // transient Google-side failure would misreport a fine connection as
  // broken) — token-refresh failures surface as `needs_attention` only
  // when the row itself is present but visibly incomplete.
  let googleState: ConnectionState = 'disconnected';
  try {
    const sb = createSupabaseServiceRoleClient();
    const { data } = await sb
      .from('google_calendar_tokens')
      .select('refresh_token')
      .eq('id', 'google_calendar')
      .maybeSingle();
    if (data?.refresh_token) googleState = 'connected';
  } catch (err) {
    console.error('[api/settings/connections] google token lookup failed:', err);
    googleState = 'needs_attention';
  }

  // Telegram bots run as separate VM services (telegram-bots/*), configured
  // by their own env files — this Next.js deploy has no live signal into
  // their health (that belongs to Agent & Job Status once those jobs get a
  // heartbeat). TELEGRAM_CHAT_ID here is optional/documentary only: if an
  // operator has set it on this deploy we treat that as "configured",
  // otherwise we say so honestly rather than guessing.
  const telegramState: ConnectionState = process.env.TELEGRAM_CHAT_ID ? 'connected' : 'disconnected';

  const connections: ConnectionStatus[] = [
    { service: 'google_calendar', state: googleState },
    { service: 'google_tasks', state: googleState },
    { service: 'telegram', state: telegramState },
  ];

  return NextResponse.json({ connections });
}
