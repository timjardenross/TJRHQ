'use client';

import { useState } from 'react';
import type { SystemSummary, WorkbenchSection } from '@/lib/weeklyReview';
import { SummaryCards } from './SummaryCards';
import { WorkbenchCard } from './WorkbenchCard';

/** The original per-workbench cards, demoted to a collapsed drill-down
 * (brief §22) — not deleted. Collapsed by default so the primary review
 * doesn't require reading eight domain cards to be complete. */
export function SourceDetail({ summary, sections }: { summary: SystemSummary; sections: WorkbenchSection[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-md border border-wb-line bg-wb-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-[13px] font-medium text-wb-ink"
        aria-expanded={open}
      >
        Source Detail
        <span className="text-[11px] text-wb-ink2">{open ? 'Hide ▲' : 'Show ▼'}</span>
      </button>
      {open && (
        <div className="flex flex-col gap-4 border-t border-wb-line px-4 py-4">
          <SummaryCards summary={summary} />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {sections.map((section) => <WorkbenchCard key={section.key} section={section} />)}
          </div>
        </div>
      )}
    </div>
  );
}
