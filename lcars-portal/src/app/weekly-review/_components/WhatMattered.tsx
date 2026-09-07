'use client';

import Link from 'next/link';
import { Card } from '@/components/ui';
import type { MatteredItem } from '@/lib/weeklyReview';

const DOT_CLASS: Record<MatteredItem['tone'], string> = {
  ok: 'bg-wb-ok', warn: 'bg-wb-warn', crit: 'bg-wb-crit', neutral: 'bg-wb-ink2',
};

/** Capped at 5 (brief §8) — genuinely meaningful items only, not "everything
 * that happened." */
export function WhatMattered({ items }: { items: MatteredItem[] }) {
  return (
    <Card>
      <h2 className="mb-3 font-serif text-[15px] uppercase tracking-[0.1em] text-wb-ink">What Mattered</h2>
      {items.length === 0 ? (
        <p className="text-[13px] text-wb-ink2">Nothing crossed the bar this week.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li key={item.key} className="flex items-start gap-2 text-[13px]">
              <span aria-hidden className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${DOT_CLASS[item.tone]}`} />
              <span>
                <span className="font-medium text-wb-ink">
                  {item.href ? <Link href={item.href} className="hover:underline">{item.title}</Link> : item.title}
                </span>
                <span className="text-wb-ink2"> — {item.why}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
