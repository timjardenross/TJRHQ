'use client';

import { Card } from '@/components/ui';
import type { WatchItem } from '@/lib/weeklyReview';

/** Known Unknowns / Evidence Gaps feed here (brief §12) — `available: false`
 * means the underlying gap-tracking isn't wired to weekly data yet, and is
 * shown as an honest capability gap rather than a fabricated "no gaps"
 * claim (brief §31). */
export function WatchNextWeek({ items }: { items: WatchItem[] }) {
  return (
    <Card>
      <h2 className="mb-3 font-serif text-[15px] uppercase tracking-[0.1em] text-wb-ink">Watch Next Week</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        {items.map((item) => (
          <div key={item.key} className="rounded-md border border-wb-line bg-wb-bg px-3 py-2">
            <div className="text-[11px] uppercase tracking-[0.08em] text-wb-ink2">{item.label}</div>
            <p className="mt-0.5 text-[12px] text-wb-ink">{item.detail}</p>
            {!item.available && <p className="mt-1 text-[10px] uppercase tracking-[0.06em] text-wb-ink2">Not yet computable</p>}
          </div>
        ))}
      </div>
    </Card>
  );
}
