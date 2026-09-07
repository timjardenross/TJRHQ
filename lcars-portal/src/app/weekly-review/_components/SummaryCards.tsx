'use client';

import type { SystemSummary } from '@/lib/weeklyReview';

function Stat({ label, value, tone }: { label: string; value: number; tone: 'ok' | 'warn' | 'crit' | 'neutral' }) {
  const toneClass = {
    ok: 'text-wb-ok-on', warn: 'text-wb-warn-on', crit: 'text-wb-crit-on', neutral: 'text-wb-ink',
  }[tone];
  return (
    <div className="rounded-md border border-wb-line bg-wb-surface px-4 py-3 text-center">
      <div className={`font-serif text-[18px] ${toneClass}`}>{value}</div>
      <div className="text-[11px] text-wb-ink2">{label}</div>
    </div>
  );
}

/** Demoted 2026-09-05 (Weekly Review synthesis mission, brief §21) — this
 * used to be the opening experience; it's now a secondary diagnostic
 * rendered inside the collapsed Source Detail section, below the
 * synthesis. "Newly important" (a duplicate of Urgent) and "Safe to ignore"
 * (a miscounted stat, not an evidence-backed ignorable list) were removed
 * entirely rather than carried forward — see lib/weeklyReview.ts's
 * SystemSummary doc comment. */
export function SummaryCards({ summary }: { summary: SystemSummary }) {
  const debtLabel = summary.reviewDebtDays == null
    ? 'First review'
    : summary.reviewDebtDays <= 8 ? 'On track' : `${summary.reviewDebtDays}d since last`;

  return (
    <div>
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Open loops" value={summary.openLoops} tone={summary.openLoops > 0 ? 'warn' : 'ok'} />
        <Stat label="Waiting on" value={summary.waitingOn} tone={summary.waitingOn > 0 ? 'warn' : 'ok'} />
        <Stat label="Urgent this week" value={summary.urgentThisWeek} tone={summary.urgentThisWeek > 0 ? 'crit' : 'ok'} />
      </div>
      <p className="mt-2 text-center text-[11px] text-wb-ink2">{debtLabel}</p>
    </div>
  );
}
