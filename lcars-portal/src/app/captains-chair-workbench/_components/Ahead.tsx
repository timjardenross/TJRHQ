'use client';

// Ahead (MSN-0364) — merges the old separate Calendar/Reminders cards into
// one adaptive component. Compact when empty, expands when busy. "Coming
// Up" (beyond today) reads the new /api/calendar/upcoming route
// (fetchUpcomingEvents, read-only) — same Google Calendar connection as
// today's events, no second calendar backend.

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { categoryMeta, type PersonalTask } from '@/lib/personalTasks';
import type { CalendarTodayEvent, CalendarTodayStatus, UpcomingCalendarEvent } from '@/lib/captainsChairData';

function eventLine(event: CalendarTodayEvent, i: number) {
  return (
    <li key={i} className="flex items-baseline gap-2 text-xs">
      <span className="w-14 shrink-0 font-semibold text-wb-ink">{event.allDay ? 'All day' : event.time ?? '—'}</span>
      <span className="text-wb-ink">{event.title}{event.location && <span className="text-wb-ink2"> · {event.location}</span>}</span>
    </li>
  );
}

export function Ahead({
  calendarEvents,
  calendarStatus,
  calendarLoading,
  upcoming,
  upcomingStatus,
  upcomingLoading,
  reminders,
  remindersLoading,
}: {
  calendarEvents: CalendarTodayEvent[];
  calendarStatus: CalendarTodayStatus;
  calendarLoading: boolean;
  upcoming: UpcomingCalendarEvent[];
  upcomingStatus: CalendarTodayStatus;
  upcomingLoading: boolean;
  reminders: PersonalTask[];
  remindersLoading: boolean;
}) {
  const loading = calendarLoading || upcomingLoading || remindersLoading;
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Australia/Brisbane' });
  const comingUp = upcoming.filter((e) => e.dateISO !== today);
  const isBusy = calendarEvents.length > 0 || reminders.length > 0 || comingUp.length > 0;

  return (
    <WorkbenchPanel title="Ahead" eyebrow="Next 24–48 hours">
      {loading ? (
        <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>
      ) : !isBusy && calendarStatus === 'ok' ? (
        <p className="text-sm text-wb-ink2">Nothing scheduled, nothing needs a nudge.</p>
      ) : (
        <div className="space-y-3">
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-wb-ink2">Calendar</p>
            {calendarStatus === 'disconnected' ? (
              <p className="text-xs text-wb-ink2">
                Google Calendar isn&apos;t connected. <a href="/api/auth/google-calendar/connect" className="text-wb-sage-deep hover:underline">Connect it</a>.
              </p>
            ) : calendarStatus === 'error' ? (
              <p className="text-xs text-wb-crit-on">Calendar unavailable — see console for detail.</p>
            ) : calendarEvents.length === 0 ? (
              <p className="text-xs text-wb-ink2">Nothing scheduled today.</p>
            ) : (
              <ul className="space-y-1.5">{calendarEvents.map(eventLine)}</ul>
            )}
          </div>

          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-wb-ink2">Reminders</p>
            {reminders.length === 0 ? (
              <p className="text-xs text-wb-ink2">Nothing requires attention.</p>
            ) : (
              <ul className="space-y-1.5">
                {reminders.map((task) => (
                  <li key={task.id} className="flex items-start gap-2 text-xs">
                    <span className="mt-0.5 text-wb-ink2">{categoryMeta(task.category).glyph}</span>
                    <span className="flex-1 text-wb-ink">
                      {task.title}
                      {task.nudge_count > 3 && <span className="ml-1 text-wb-ink2">(nudged {task.nudge_count}×)</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {comingUp.length > 0 && upcomingStatus === 'ok' && (
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-wb-ink2">Coming Up</p>
              <ul className="space-y-1.5">
                {comingUp.slice(0, 5).map((e, i) => (
                  <li key={i} className="flex items-baseline gap-2 text-xs">
                    <span className="w-24 shrink-0 font-semibold text-wb-ink">
                      {new Date(e.dateISO).toLocaleDateString('en-AU', { weekday: 'short', day: '2-digit', month: 'short' })}
                    </span>
                    <span className="text-wb-ink">{e.title}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="pt-1">
            <Link href="/ready-room" className="text-[11px] text-wb-sage-deep hover:underline">Ready Room →</Link>
          </div>
        </div>
      )}
    </WorkbenchPanel>
  );
}
