'use client';

import { Card } from '@/components/ui';
import type { WeekInReview as WeekInReviewData } from '@/lib/weeklyReview';
import { GLYPH_SYMBOL, GLYPH_CLASS } from './glyph';

/** The opening synthesis — "HQ reviewed the week for you," not a metric
 * wall. First thing read, per brief §4/§5. */
export function WeekInReview({ data }: { data: WeekInReviewData }) {
  return (
    <Card>
      <h2 className="mb-1 font-serif text-[15px] uppercase tracking-[0.1em] text-wb-ink">Week in Review</h2>
      <p className="mb-4 text-[14px] text-wb-ink">{data.narrative}</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {data.lines.map((line) => (
          <div key={line.key} className="rounded-md border border-wb-line bg-wb-bg px-3 py-2">
            <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.08em] text-wb-ink2">
              <span className={GLYPH_CLASS[line.glyph]} aria-hidden>{GLYPH_SYMBOL[line.glyph]}</span>
              {line.label}
            </div>
            <div className="mt-0.5 text-[12px] text-wb-ink">{line.detail}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}
