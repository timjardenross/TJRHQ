// PATCH /api/content-workbench/[id]/schedule — set/clear a Content Workbench
// item's scheduled publish time (MSN-0363, migration 0185) and keep a real
// Google Calendar event in sync with it.
//
// Captain-confirmed 2026-09-05: GOOGLE_OAUTH_SCOPES widened from
// calendar.readonly to calendar.events specifically for this. Creates a
// new event on first schedule, reschedules the same event (by
// calendar_event_id) on a change, and deletes it on unschedule — never
// more than one event per item, never a second calendar system. If the
// stored token predates the scope widening (still calendar.readonly) or
// is disconnected, the DB write still succeeds — scheduled_for is the
// real source of truth Today's "Coming Up" reads from — but the calendar
// side is skipped and the response says so, rather than failing the whole
// request over a calendar sync problem.
//
// Does not write comms_content.status — advance() stays the only place
// that happens. Scheduling only makes sense pre-publish, so this rejects
// already-published/archived items.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';
import {
  createCalendarEvent,
  updateCalendarEventTime,
  deleteCalendarEvent,
  GoogleCalendarDisconnectedError,
  GoogleCalendarInsufficientScopeError,
} from '@/lib/google-calendar';

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const body = await req.json();
    // null explicitly unschedules; undefined/missing is a no-op error, not
    // a silent clear — a caller must say which it means.
    if (!('scheduled_for' in body)) {
      return NextResponse.json({ error: 'scheduled_for is required (ISO string or null)' }, { status: 400 });
    }
    const scheduledFor = body.scheduled_for === null ? null : new Date(body.scheduled_for).toISOString();

    const sb = serviceClient();
    const { data: row, error: fetchErr } = await sb
      .from('comms_content')
      .select('status, title, calendar_event_id')
      .eq('id', params.id)
      .single();
    if (fetchErr || !row) return NextResponse.json({ error: 'Not found' }, { status: 404 });
    if (row.status === 'published' || row.status === 'archived') {
      return NextResponse.json({ error: `Cannot schedule a '${row.status}' item` }, { status: 400 });
    }

    let calendarEventId: string | null = row.calendar_event_id;
    let calendarSynced = true;
    let calendarWarning: string | null = null;

    try {
      if (scheduledFor === null) {
        if (calendarEventId) await deleteCalendarEvent(calendarEventId);
        calendarEventId = null;
      } else if (calendarEventId) {
        await updateCalendarEventTime(calendarEventId, scheduledFor);
      } else {
        const created = await createCalendarEvent({
          title: `Publish: ${row.title}`,
          startISO: scheduledFor,
          description: 'Scheduled from the Content Workbench (Content Studio).',
        });
        calendarEventId = created.id;
      }
    } catch (calErr) {
      calendarSynced = false;
      calendarEventId = row.calendar_event_id; // leave whatever was there, don't lose a valid id on a transient failure
      calendarWarning =
        calErr instanceof GoogleCalendarDisconnectedError ? 'Google Calendar is not connected — scheduled in Content Workbench only.' :
        calErr instanceof GoogleCalendarInsufficientScopeError ? 'Google Calendar needs reconnecting (new permission) — scheduled in Content Workbench only.' :
        'Could not sync with Google Calendar — scheduled in Content Workbench only.';
      console.error('[content-workbench/schedule] calendar sync failed', calErr);
    }

    const { error: updateErr } = await sb
      .from('comms_content')
      .update({ scheduled_for: scheduledFor, calendar_event_id: calendarEventId, updated_at: new Date().toISOString() })
      .eq('id', params.id);
    if (updateErr) throw updateErr;

    return NextResponse.json({ success: true, scheduled_for: scheduledFor, calendar_synced: calendarSynced, calendar_warning: calendarWarning });
  } catch (err) {
    console.error('[content-workbench/schedule]', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
