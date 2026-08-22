'use client';

import { Badge } from '@/components/ui';
import { CollapsibleSection } from './CollapsibleSection';
import type { InterventionEffectiveness } from './types';

const OUTCOME_LABEL: Record<string, string> = { better: 'Better', same: 'Same', worse: 'Worse', not_completed: "Didn't do it" };

/** V3 doc §16/§27 — general-evidence labels, deliberately not phrased as
 *  clinical certainty. 'unknown' has no entry here on purpose: it means
 *  nobody has reviewed this intervention's evidence yet, not "checked and
 *  found nothing", so it renders nothing rather than a noisy badge on all
 *  30 catalogue rows (see the `evidence_strength !== 'unknown'` guard
 *  below). */
const EVIDENCE_LABEL: Record<string, string> = {
  established_guideline_aligned: 'Evidence-informed · guideline-aligned',
  moderate: 'Evidence-informed · moderate support',
  emerging: 'Evidence-informed · emerging, worth testing',
  lived_experience_informed: 'Evidence-informed · lived-experience pattern',
  personal_only: 'Evidence-informed · personal pattern only',
};

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
                  {/* Secondary, muted, and deliberately separate from the personal
                   *  better/same/worse Badge to the right — spec §16: general evidence
                   *  and personal outcome data must never be blended into one score.
                   *  Suppressed entirely for 'unknown' (the default for all 30 seeded
                   *  rows until a human reviews them) so this doesn't read as "checked,
                   *  found nothing" on every row. */}
                  {r.evidence_strength !== 'unknown' && (
                    <div className="mt-0.5 text-[11px] italic text-wb-ink2/70" title={r.evidence_basis ?? undefined}>
                      {EVIDENCE_LABEL[r.evidence_strength]}
                    </div>
                  )}
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
