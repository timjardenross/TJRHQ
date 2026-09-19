'use client';

// Remember (Mission 3, Capture/Remember/Follow-Through) — answers "what
// have I told you that matters again now?" Deliberately a thin
// presentation of context_service.py's GET /remember — this component
// does not decide what belongs here (that's the Personal Task Attention
// Adapter + unresolved-capture query, both capacity-aware, entirely
// backend-owned via useRemember()). It is not another task list, not
// another Attention State, not a notification centre: no "mark done",
// no priority re-sorting, no scoring — just "here's what's worth
// bringing back to your attention", with a link out to where it's
// actually actioned (Ready Room / Capture Workbench).
//
// Empty state is enforced strictly, same posture as NeedsYou.tsx: if
// there's nothing to remember, this panel says so and stops — it never
// manufactures content to avoid looking empty.

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import type { RememberData } from '@/lib/captainsChairData';

export function Remember({ data, error }: { data: RememberData | null; error: string | null }) {
  const loading = data === null && error === null;
  const tasks = data?.resurfacing_tasks ?? [];
  const captures = data?.unresolved_captures ?? [];
  const total = tasks.length + captures.length;

  return (
    <WorkbenchPanel
      title="Remember"
      eyebrow={total > 0 ? `${total} item${total === 1 ? '' : 's'}` : undefined}
    >
      {loading ? (
        <p className="text-sm text-wb-ink2 animate-pulse">Checking…</p>
      ) : total === 0 ? (
        <p className="text-sm font-medium text-wb-ink2">Nothing waiting to come back to you.</p>
      ) : (
        <ul className="space-y-2">
          {tasks.slice(0, 5).map((item) => (
            <li key={item.id} className="rounded-lg border border-wb-line bg-wb-surface p-3">
              <p className="text-sm font-semibold text-wb-ink">{item.title}</p>
              <p className="mt-0.5 text-xs text-wb-ink2">{item.capacity_adjusted_reason ?? item.reason}</p>
              {item.ref && (
                <Link href="/ready-room" className="mt-1.5 inline-block text-[11px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                  Open in Ready Room →
                </Link>
              )}
            </li>
          ))}
          {captures.slice(0, 5).map((item) => (
            <li key={item.id} className="rounded-lg border border-wb-line bg-wb-surface p-3">
              <p className="text-sm font-semibold text-wb-ink">{item.title}</p>
              <p className="mt-0.5 text-xs text-wb-ink2">{item.reason}</p>
              <Link href="/capture-workbench" className="mt-1.5 inline-block text-[11px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                Review in Capture Workbench →
              </Link>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p className="mt-3 text-[10px] text-wb-ink2">Unavailable right now: {error}.</p>
      )}
    </WorkbenchPanel>
  );
}
