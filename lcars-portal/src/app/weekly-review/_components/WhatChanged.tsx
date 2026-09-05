'use client';

import { Card } from '@/components/ui';
import type { ChangeItem } from '@/lib/weeklyReview';
import { GLYPH_SYMBOL, GLYPH_CLASS } from './glyph';

/** Delta, not volume (brief §7) — week-over-week where a prior week exists,
 * explicit "no prior week yet" otherwise. Never silently renders "no
 * change" when there's simply nothing to compare against. */
export function WhatChanged({ items }: { items: ChangeItem[] }) {
  return (
    <Card>
      <h2 className="mb-3 font-serif text-[15px] uppercase tracking-[0.1em] text-wb-ink">What Changed</h2>
      <ul className="flex flex-col gap-2.5">
        {items.map((item) => (
          <li key={item.key} className="flex items-start gap-2 text-[13px]">
            <span className={`mt-0.5 ${GLYPH_CLASS[item.glyph]}`} aria-hidden>{GLYPH_SYMBOL[item.glyph]}</span>
            <span>
              <span className="font-medium text-wb-ink">{item.label}</span>
              <span className="text-wb-ink2"> — {item.detail}</span>
              {item.noHistory && <span className="ml-1 text-[10px] uppercase tracking-[0.08em] text-wb-ink2">no history</span>}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
