'use client';

// PATTERNS tab (Human Systems redesign Phase 7, 2026-09-06) — flesh-out
// pass beyond the Phase 2 placeholder. The former "System Learning"
// user-facing label is retitled to "Patterns" (RecoveryView.tsx's
// SystemLearningSection, shared with the retired RecoveryView composite).
// Adds two more real-data-backed pattern surfaces below it — Capacity Debt
// and Recurring Loads (both already computed by the API for MedicalView,
// medical.capacity_debt / medical.redesign_candidates) — worded as
// association/trend language throughout, never causal certainty or a
// fixed rule (spec §22-24). Nothing here is fabricated: every number
// traces to a field the API already returns; "What May Need to Change" on
// the NOW tab keeps its own copy of redesign_candidates unchanged (that
// placement was locked in by an earlier phase) — this is an additional,
// pattern-framed view of the same real data, not a relocation.

import { Badge } from '@/components/ui';
import { CollapsibleSection } from './CollapsibleSection';
import { SystemLearningSection } from './RecoveryView';
import type { MedicalPayload, RecoveryPayload } from './types';

/** Spec §19/§23 — capacity_debt (evening 'yes'/'maybe' debt flags over the
 *  last window_days) is a trend signal, not a hard prediction about
 *  tomorrow — "may already be partly spoken for" language keeps it
 *  qualitative, not a stated fact. */
function CapacityDebtNote({ debt }: { debt: MedicalPayload['capacity_debt'] }) {
  if (debt.days_total === 0) return null;
  return (
    <div className="rounded-md border border-wb-line bg-wb-bg p-3">
      <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Capacity Debt</div>
      <p className="mt-1 text-[13px] leading-relaxed text-wb-ink">
        {debt.days_with_debt} of {debt.days_total} evening reflections in the last {debt.window_days} days flagged
        possible next-day debt. On days like that, tomorrow&rsquo;s capacity may already be partly spoken for before
        the day even starts — an association worth watching, not a guarantee.
      </p>
    </div>
  );
}

/** Spec §23 — redesign_candidates as a pattern: a load that keeps
 *  co-occurring with stretched/depleted days, presented explicitly as an
 *  association rather than a proven trigger. */
function RecurringLoadsNote({ candidates }: { candidates: MedicalPayload['redesign_candidates'] }) {
  if (candidates.length === 0) return null;
  return (
    <div className="rounded-md border border-wb-line bg-wb-bg p-3">
      <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Recurring Loads</div>
      <div className="mt-2 flex flex-col gap-2">
        {candidates.map((r) => (
          <div key={r.load} className="flex items-center justify-between gap-2">
            <span className="text-[13px] text-wb-ink">{r.load}</span>
            <Badge status="warning">{r.stretched_or_depleted_count}/{r.window_days} days</Badge>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[12px] leading-relaxed text-wb-ink2">
        This is an association, not a cause — these loads co-occur with stretched or depleted days often enough
        to be worth watching, not a proven trigger.
      </p>
    </div>
  );
}

export function PatternsView({ recovery, medical }: { recovery: RecoveryPayload; medical: MedicalPayload | null }) {
  const hasNarrativePattern = !!(
    recovery.wellness.narrative ||
    recovery.wellness.risk_flags.length > 0 ||
    recovery.wellness.positive_flags.length > 0
  );
  const hasLongerRunSignal = !!medical && (medical.capacity_debt.days_total > 0 || medical.redesign_candidates.length > 0);

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <SystemLearningSection data={recovery} className="md:col-span-2" />
      {hasNarrativePattern && (
        <p className="text-[11px] italic text-wb-ink2 md:col-span-2">
          Possible Pattern above is an association, not a cause — a co-occurrence worth watching, not a diagnosis.
        </p>
      )}

      {hasLongerRunSignal && medical && (
        <CollapsibleSection title="Longer-Run Signals" className="md:col-span-2">
          <div className="flex flex-col gap-3">
            <CapacityDebtNote debt={medical.capacity_debt} />
            <RecurringLoadsNote candidates={medical.redesign_candidates} />
          </div>
        </CollapsibleSection>
      )}
    </div>
  );
}
