'use client';

import { Badge } from '@/components/ui';
import { CollapsibleSection } from './CollapsibleSection';
import type { InterventionEffectiveness } from './types';

const OUTCOME_LABEL: Record<string, string> = { better: 'Better', same: 'Same', worse: 'Worse', not_completed: "Didn't do it" };

/** Extracted from MedicalView so it can render next to My REVS Position in
 *  RecoveryView instead — same intervention-effectiveness data (spec §18),
 *  just relocated. Data still comes from MedicalPayload; page.tsx passes
 *  it down as a prop since RecoveryView only otherwise sees RecoveryPayload. */
export function WhatHelpsMeCard({ data }: { data: InterventionEffectiveness[] }) {
  const qualified = data.filter((r) => r.meets_sample_threshold);
  const unqualified = data.filter((r) => !r.meets_sample_threshold);

  return (
    <CollapsibleSection title="What Helps Me">
      {data.length === 0 ? (
        <p className="text-[13px] text-wb-ink2">No interventions tried yet. Use /capacity, /helpme, or /guide on the Capacity Bot to start building a track record.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {qualified.map((r) => {
            const completed = r.better + r.same + r.worse;
            return (
              <div key={r.intervention_id} className="flex items-center justify-between gap-2 rounded-md border border-wb-line bg-wb-bg p-3">
                <div>
                  <div className="text-[13px] font-medium text-wb-ink">{r.title}</div>
                  <div className="text-[12px] text-wb-ink2">
                    {r.attempts} attempts
                    {r.common_context && <> · most often used for {r.common_context}</>}
                  </div>
                </div>
                <Badge status={r.better > r.worse ? 'success' : r.worse > r.better ? 'warning' : 'neutral'}>
                  {completed === 0 ? 'No reassessments yet' : `${r.better}/${completed} ${OUTCOME_LABEL.better}`}
                </Badge>
              </div>
            );
          })}
          {unqualified.length > 0 && (
            <p className="mt-1 text-[12px] text-wb-ink2">
              {unqualified.length} more strateg{unqualified.length === 1 ? 'y' : 'ies'} tried fewer than 3 times — not enough data yet.
            </p>
          )}
        </div>
      )}
    </CollapsibleSection>
  );
}
