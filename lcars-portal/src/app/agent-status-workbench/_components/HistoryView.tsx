'use client';

/**
 * History tab — a compact operational-health timeline, not a raw log
 * viewer. Renders the down/up transition events emitted by
 * /api/agent-status-workbench/history (itself derived from the raw
 * domain_heartbeats event log, collapsed to transitions only). No polling —
 * this is a look-back view, not a live status board.
 */

import { useEffect, useState } from 'react';
import { Card } from '@/components/ui';
import { stateToneClasses } from '@/lib/departments';
import { relativeTime } from './shared';

type HistoryEvent =
  | { domainKey: string; label: string; at: string; kind: 'down'; detail: string | null }
  | {
      domainKey: string;
      label: string;
      at: string;
      kind: 'up';
      detail: string | null;
      downSinceIso: string;
      durationMinutes: number;
    };

interface HistoryData {
  events: HistoryEvent[];
  windowHours: number;
  fetchedAt: string;
}

/** Groups events by calendar day (local time), preserving the incoming
 *  (descending) order within and across groups. */
function groupByDay(events: HistoryEvent[]): Array<{ dayLabel: string; events: HistoryEvent[] }> {
  const groups: Array<{ dayLabel: string; events: HistoryEvent[] }> = [];
  const indexByDayLabel = new Map<string, number>();

  for (const event of events) {
    const dayLabel = new Date(event.at).toLocaleDateString(undefined, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
    const existingIndex = indexByDayLabel.get(dayLabel);
    if (existingIndex === undefined) {
      indexByDayLabel.set(dayLabel, groups.length);
      groups.push({ dayLabel, events: [event] });
    } else {
      groups[existingIndex].events.push(event);
    }
  }

  return groups;
}

function narrativeText(event: HistoryEvent): string {
  if (event.kind === 'down') {
    return `${event.label} became unavailable`;
  }
  if (event.durationMinutes && event.durationMinutes > 0) {
    return `${event.label} recovered after a ${event.durationMinutes}-minute interruption`;
  }
  return `${event.label} recovered`;
}

function HistoryRow({ event }: { event: HistoryEvent }) {
  const tone = event.kind === 'down' ? 'crit' : 'ok';
  const classes = stateToneClasses(tone);

  return (
    <li className="flex items-start gap-2.5 py-2.5">
      <span className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full ${classes.dot}`} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-[12px] tabular-nums text-wb-ink2">{relativeTime(event.at)}</span>
          <span className="text-[13px] text-wb-ink">{narrativeText(event)}</span>
        </div>
        {event.detail && (
          <p className="mt-0.5 truncate text-[11px] text-wb-ink2" title={event.detail}>
            {event.detail}
          </p>
        )}
      </div>
    </li>
  );
}

export function HistoryView() {
  const [data, setData] = useState<HistoryData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch('/api/agent-status-workbench/history', { cache: 'no-store' });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body?.error ?? `HTTP ${res.status}`);
        }
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Failed to load history');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (isLoading) return <Card><p className="text-[13px] italic text-wb-ink2">Loading history…</p></Card>;
  if (loadError || !data) {
    return (
      <Card>
        <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
          <p className="text-[13px] font-semibold text-wb-crit-on">History unavailable</p>
          <p className="mt-1 text-[12px] text-wb-ink2">{loadError ?? 'No data returned.'}</p>
        </div>
      </Card>
    );
  }

  const dayGroups = groupByDay(data.events);
  const showDayHeaders = dayGroups.length > 1;

  return (
    <Card>
      <p className="mb-3 text-[11px] text-wb-ink2">
        Recent operational changes — last {data.windowHours} hours
      </p>

      {data.events.length === 0 ? (
        <p className="text-[13px] italic text-wb-ink2">
          No failures or recoveries in the last {data.windowHours} hours.
        </p>
      ) : (
        <div className="flex flex-col">
          {dayGroups.map((group) => (
            <div key={group.dayLabel}>
              {showDayHeaders && (
                <p className="mt-3 border-b border-wb-line pb-1 text-[10px] uppercase tracking-wider text-wb-ink2 first:mt-0">
                  {group.dayLabel}
                </p>
              )}
              <ul className="divide-y divide-wb-line">
                {group.events.map((event) => (
                  <HistoryRow key={`${event.domainKey}-${event.at}-${event.kind}`} event={event} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
