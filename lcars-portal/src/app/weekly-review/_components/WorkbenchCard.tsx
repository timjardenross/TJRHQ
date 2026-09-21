'use client';

import Link from 'next/link';
import { Card } from '@/components/ui';
import { EvidenceMeta } from '@/components/EvidenceMeta';
import { SignalRow } from './SignalRow';
import type { WorkbenchSection } from '@/lib/weeklyReview';

/** One workbench's weekly review — 4-6 signals, skimmable in under a minute.
 * Quiet "nothing to do here" when every countable signal is zero, per the
 * spec's "don't show everything by default" rule. */
export function WorkbenchCard({ section, observedAt }: { section: WorkbenchSection; observedAt?: string | null }) {
  const countable = section.signals.filter((s) => !s.unavailable);
  const isQuiet = countable.length > 0 && countable.every((s) => s.count === 0);
  const anyUnavailable = section.signals.some((s) => s.unavailable);

  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="font-serif text-[14px] text-wb-ink">{section.title}</h3>
        <Link href={section.href} className="text-[11px] text-wb-sage-deep hover:underline">Open →</Link>
      </div>

      {isQuiet ? (
        <p className="py-2 text-[12px] text-wb-ink2">Nothing to review here this week.</p>
      ) : (
        <div className="flex flex-col divide-y divide-wb-line/60">
          {section.signals.map((s) => <SignalRow key={s.key} signal={s} sourceLabel={section.title} />)}
        </div>
      )}
      {anyUnavailable && (
        <p className="text-[10px] text-wb-ink2">Some signals couldn&apos;t be checked this run.</p>
      )}
      {/* Weekly Review WP2: counts above come straight from this workbench's
       * own tables (api/weekly-review/route.ts queries them live, no mirror
       * table) — observedAt is the review's week-end boundary, the real
       * cutoff those counts were computed against. `unavailable` is real:
       * it means that signal's query itself failed this run, not a fake
       * "some data missing" guess. */}
      <EvidenceMeta
        source={section.title}
        observedAt={observedAt}
        state={anyUnavailable ? 'unavailable' : isQuiet ? 'empty' : undefined}
      />
    </Card>
  );
}
