'use client';

import Link from 'next/link';
import { Badge, Card } from '@/components/ui';
import type { BadgeStatus } from '@/components/ui';
import type { ReadinessPayload } from './types';

const SESSION_TYPE_LABELS: Record<string, string> = {
  recovery: 'Recovery',
  low_energy_strength: 'Low-energy strength',
  balanced_strength: 'Balanced strength',
  upper_body_strength: 'Upper-body strength',
  lower_body_gentle_strength: 'Lower-body gentle strength',
  cardio_mobility: 'Cardio & mobility',
  minimum_viable: 'Minimum viable',
};

function statusBadge(status: string): BadgeStatus {
  if (status === 'completed') return 'success';
  if (status === 'partially_completed') return 'warning';
  if (status === 'stopped') return 'error';
  return 'info'; // in_progress
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' });
}

/** Readiness tab — adaptive gym decision-support. Start check-in, last session,
 *  weekly cadence, and links into the existing physical-readiness sub-routes. */
export function ReadinessView({ data }: { data: ReadinessPayload }) {
  const s = data.last_session;
  return (
    <div className="flex flex-col gap-4">
      <Card title="Quick links">
        <div className="grid grid-cols-2 gap-3">
          <Link href="/human-systems-workbench/readiness/library" className="rounded-md border border-wb-line px-4 py-3 text-center text-[13px] font-medium text-wb-ink transition hover:border-wb-sage-deep">Exercise library</Link>
          <Link href="/human-systems-workbench/readiness/history" className="rounded-md border border-wb-line px-4 py-3 text-center text-[13px] font-medium text-wb-ink transition hover:border-wb-sage-deep">History</Link>
        </div>
      </Card>

      <Card title="Last session">
        {!s && <p className="text-[13px] text-wb-ink2">No sessions logged yet. Your first check-in starts the record.</p>}
        {s && (
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[14px] font-medium text-wb-ink">{SESSION_TYPE_LABELS[s.type] ?? s.type}</div>
              <div className="text-[12px] text-wb-ink2">
                {fmtDate(s.date)}
                {s.duration ? ` · ${s.duration} min` : ''}
              </div>
            </div>
            <Badge status={statusBadge(s.status)}>{s.status.replace(/_/g, ' ')}</Badge>
          </div>
        )}
        <p className="mt-3 text-[12px] text-wb-ink2">
          {data.weekly_count} session{data.weekly_count === 1 ? '' : 's'} completed in the last 7 days.
        </p>
      </Card>
    </div>
  );
}
