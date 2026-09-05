'use client';

import Link from 'next/link';
import { Card } from '@/components/ui';
import type { CarryForwardItem } from '@/lib/weeklyReview';
import { ItemRow } from './SignalRow';

/** "What genuinely deserves to survive the weekly boundary" (brief §14) —
 * an ATTENTION decision, never a lifecycle mutation. Items wrapping a real
 * signal item reuse SignalRow's existing "→ Ready Room" createTask() action
 * verbatim; standalone items (posture, escalation watch) get a plain link. */
export function CarryForward({ items }: { items: CarryForwardItem[] }) {
  return (
    <Card>
      <h2 className="mb-1 font-serif text-[15px] uppercase tracking-[0.1em] text-wb-ink">Carry Forward</h2>
      <p className="mb-3 text-[12px] text-wb-ink2">{items.length} thing{items.length === 1 ? '' : 's'} deserve next-week attention.</p>
      {items.length === 0 ? (
        <p className="text-[13px] text-wb-ink2">Nothing needs to carry forward.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-wb-line/60">
          {items.map((item) => (
            <li key={item.key} className="py-2 text-[13px]">
              <div className="font-medium text-wb-ink">{item.title}</div>
              <div className="text-wb-ink2">{item.detail}</div>
              <div className="mt-0.5 flex items-center justify-between gap-2 text-wb-ink2">
                <span>{item.recommendation}</span>
                {!item.signalItem && item.href && (
                  <Link href={item.href} className="shrink-0 text-wb-sage-deep hover:underline">Open →</Link>
                )}
              </div>
              {item.signalItem && (
                <ul className="mt-1">
                  <ItemRow
                    id={item.signalItem.id}
                    title={item.signalItem.title}
                    href={item.signalItem.href}
                    meta={item.signalItem.meta}
                    sourceLabel={item.signalItem.sourceLabel}
                    signalLabel={item.signalItem.signalLabel}
                    tone={item.signalItem.tone}
                  />
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
