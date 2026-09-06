'use client';

import { Card } from '@/components/ui';
import type { PriorWeekContext } from '@/lib/weeklyReview';

/** Feedback loop closing (brief §34/§38): what was accepted last time the
 * week was closed, shown as read-only prior context — never merged into or
 * allowed to override this week's live synthesis above/below it. If last
 * week's plan and today's evidence disagree (e.g. planned STEADY, Human
 * Systems now reads PROTECT), that disagreement is exactly the point —
 * current evidence is what the rest of this page acts on (brief §34's
 * Sunday/Monday example). */
export function PriorWeekNote({ data }: { data: PriorWeekContext }) {
  if (!data.posture && !data.reflection) return null;
  return (
    <Card>
      <h2 className="mb-1 font-serif text-[13px] uppercase tracking-[0.1em] text-wb-ink2">Last week&apos;s plan</h2>
      {data.posture && (
        <p className="mb-1 text-[13px] text-wb-ink">
          Planned posture: <span className="font-medium">{data.posture}</span>
          {data.carryForward.length > 0 && ` — focused on ${data.carryForward.slice(0, 2).join(', ')}.`}
        </p>
      )}
      {data.reflection && (
        <p className="text-[13px] italic text-wb-ink2">&ldquo;{data.reflection}&rdquo;</p>
      )}
      <p className="mt-2 text-[11px] text-wb-ink2">
        This week&apos;s synthesis below uses today&apos;s own evidence — a plan made last week doesn&apos;t override it.
      </p>
    </Card>
  );
}
