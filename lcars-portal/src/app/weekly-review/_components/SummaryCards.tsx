'use client';

import type { SystemSummary } from '@/lib/weeklyReview';

function Stat({ label, value, tone }: { label: string; value: number; tone: 'ok' | 'warn' | 'crit' | 'neutral' }) {
  const toneClass = {
    ok: 'text-wb-ok-on', warn: 'text-wb-warn-on', crit: 'text-wb-crit-on', neutral: 'text-wb-ink',
  }[tone];
  return (
    <div className="rounded-md border border-wb-line bg-wb-surface px-4 py-3 text-center">
      <div className={`font-serif text-[22px] ${toneClass}`}>{value}</div>
      <div className="text-[11px] text-wb-ink2">{label}</div>
    </div>
  );
}

/** System-wide scan — the first thing read, before any per-workbench detail. */
export function SummaryCards({ summary }: { summary: SystemSummary }) {
  const debtLabel = summary.reviewDebtDays == null
    ? 'First review'
    : summary.reviewDebtDays <= 8 ? 'On track' : `${summary.reviewDebtDays}d since last`;

  return (
    <div className="mb-6">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Stat label="Open loops" value={summary.openLoops} tone={summary.openLoops > 0 ? 'warn' : 'ok'} />
        <Stat label="Waiting on" value={summary.waitingOn} tone={summary.waitingOn > 0 ? 'warn' : 'ok'} />
        <Stat label="Urgent this week" value={summary.urgentThisWeek} tone={summary.urgentThisWeek > 0 ? 'crit' : 'ok'} />
        <Stat label="Newly important" value={summary.newlyImportant} tone={summary.newlyImportant > 0 ? 'crit' : 'ok'} />
        <Stat label="Safe to ignore" value={summary.noiseToIgnore} tone="neutral" />
      </div>
      <p className="mt-2 text-center text-[11px] text-wb-ink2">{debtLabel}</p>
    </div>
  );
}
