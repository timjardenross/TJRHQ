'use client';

import { Card } from '@/components/ui';
import type { LearnedItem } from '@/lib/weeklyReview';

/** Capped at 3 (brief §13), cautious "appears to correlate with" language —
 * never a causal claim. Only rendered when there's genuine evidence-backed
 * signal to point at (buildLearned in synthesis.ts), so an empty state here
 * is expected and honest, not a bug. */
export function WhatLearned({ items }: { items: LearnedItem[] }) {
  return (
    <Card>
      <h2 className="mb-3 font-serif text-[15px] uppercase tracking-[0.1em] text-wb-ink">What HQ Learned</h2>
      {items.length === 0 ? (
        <p className="text-[13px] text-wb-ink2">No defensible new lesson this week.</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {items.map((item, i) => (
            <li key={item.key} className="text-[13px]">
              <span className="font-medium text-wb-ink">{i + 1}. {item.title}</span>
              <p className="mt-0.5 text-wb-ink2">{item.lesson}</p>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
