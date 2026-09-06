'use client';

// WHAT HELPS tab (Human Systems redesign Phase 6, 2026-09-06) — houses
// WhatHelpsMeCard (personal intervention-effectiveness track record) plus,
// when one exists, the current personal experiment (capacity_experiments,
// migration 0159, V3 doc §15). WhatHelpsMeCard.tsx itself is left untouched
// (its own sample-size gating and __tests__/WhatHelpsMeCard.test.tsx keep
// exercising it directly) — this file only adds framing and the experiment
// surface around it.
//
// No new experiment CRUD here: the API route has no POST/PATCH for
// capacity_experiments (all writes go through the Capacity Bot's
// /experiment command, per route.ts's own header comment), so there is no
// in-workbench "stop experiment" button to wire up — the existing
// "stop it anytime with /experiment on the Capacity Bot" copy is the real,
// already-supported action. Day-count is computed from the experiment's
// real started_at timestamp; "observations so far" surfaces the real
// (free-text) `notes` field rather than inventing a distinct early-
// observation field the data model doesn't have.

import { Badge } from '@/components/ui';
import { CollapsibleSection } from './CollapsibleSection';
import { WhatHelpsMeCard } from './WhatHelpsMeCard';
import { EXPERIMENT_STATUS_LABEL, type CapacityExperiment, type MedicalPayload, type RecoveryPayload } from './types';

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  if (!Number.isFinite(ms) || ms < 0) return null;
  return Math.floor(ms / 86_400_000);
}

/** The one currently proposed/active experiment, if any — same
 *  newest-first selection SystemLearningSection uses. */
function CurrentExperimentCard({ experiment: e }: { experiment: CapacityExperiment }) {
  const days = daysSince(e.started_at);
  return (
    <div className="rounded-md border border-wb-line bg-wb-bg p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-wb-ink2">Current Experiment</div>
        <Badge status={e.status === 'active' ? 'info' : 'neutral'}>{EXPERIMENT_STATUS_LABEL[e.status]}</Badge>
      </div>
      {days !== null && (
        <p className="mt-1 text-[12px] text-wb-ink2">Day {days + 1} since starting.</p>
      )}
      <p className="mt-2 text-[13px] leading-relaxed text-wb-ink">
        <span className="font-medium">Hypothesis — </span>
        {e.hypothesis}
      </p>
      <p className="mt-2 text-[13px] leading-relaxed text-wb-ink2">
        <span className="font-medium text-wb-ink">Trying — </span>
        {e.proposed_change}
      </p>
      {e.notes && (
        <p className="mt-2 text-[12px] leading-relaxed text-wb-ink2">
          <span className="font-medium text-wb-ink">Observations so far — </span>
          {e.notes}
        </p>
      )}
      <p className="mt-3 text-[11px] italic text-wb-ink2">
        Worth testing, not a commitment — stop it anytime with /experiment on the Capacity Bot if it makes things worse.
      </p>
    </div>
  );
}

export function WhatHelpsView({ recovery, medical }: { recovery: RecoveryPayload; medical: MedicalPayload | null }) {
  const currentExperiment = recovery.experiments.find((e) => e.status === 'proposed' || e.status === 'active') ?? null;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[12px] leading-relaxed text-wb-ink2">
        Based only on your own recorded experience — what you&rsquo;ve tried and what happened afterward, not
        general or published evidence. Any general-evidence context shown alongside a strategy below is kept
        separate from your own personal track record.
      </p>

      {currentExperiment && (
        <CollapsibleSection title="Current Experiment">
          <CurrentExperimentCard experiment={currentExperiment} />
        </CollapsibleSection>
      )}

      <WhatHelpsMeCard data={medical?.intervention_effectiveness ?? []} />
    </div>
  );
}
