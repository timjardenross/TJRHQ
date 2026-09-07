'use client';

import { Card } from '@/components/ui';

/** Explicit permission not to process everything (brief §15) — only ever
 * populated from evidence-backed counts (synthesis.ts's buildYouCanIgnore),
 * never a fabricated "all clear." */
export function YouCanIgnore({ lines }: { lines: string[] }) {
  return (
    <Card>
      <h2 className="mb-3 font-serif text-[15px] uppercase tracking-[0.1em] text-wb-ink">You Can Ignore</h2>
      {lines.length === 0 ? (
        <p className="text-[13px] text-wb-ink2">Nothing material to set aside this week.</p>
      ) : (
        <ul className="flex flex-col gap-2 text-[13px] text-wb-ink2">
          {lines.map((line, i) => <li key={i}>{line}</li>)}
        </ul>
      )}
      <p className="mt-3 text-[12px] font-medium text-wb-ok-on">✓ No action required.</p>
    </Card>
  );
}
