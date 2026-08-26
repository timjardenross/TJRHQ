'use client';

import type { TaskCounts } from '@/lib/personalTasks';

/** Curated counts only — "3 need attention today, 2 waiting on others" —
 * not a raw-number dashboard. A captain-facing summary should read as the
 * worst/most-pressing thing right now, not a tile grid of totals. */
export function KpiDashboard({ counts, loading }: { counts: TaskCounts | null; loading: boolean }) {
  if (loading) {
    return <div className="mb-6 h-14 animate-pulse rounded-md bg-wb-line/40" />;
  }
  if (!counts) return null;

  const total = counts.now + counts.upcoming + counts.waiting;
  if (total === 0) {
    return (
      <p className="mb-6 rounded-md border border-wb-line bg-wb-surface px-4 py-3 text-[13px] text-wb-ink2">
        Nothing needs you right now.
      </p>
    );
  }

  const parts: string[] = [];
  if (counts.now > 0) parts.push(`${counts.now} need${counts.now === 1 ? 's' : ''} attention today`);
  if (counts.waiting > 0) parts.push(`${counts.waiting} waiting on someone else`);
  if (counts.now === 0 && counts.waiting === 0 && counts.upcoming > 0) parts.push(`${counts.upcoming} upcoming, nothing urgent`);

  return (
    <p className="mb-6 rounded-md border border-wb-line bg-wb-surface px-4 py-3 text-[13px] text-wb-ink">
      {parts.join(' · ')}
    </p>
  );
}
