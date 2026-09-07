'use client';

// NOW tab — the default view of the Human Systems redesign (2026-09-06).
// Assembles the primary decision-support flow in the spec's required
// order: TODAY -> WHAT'S CONTRIBUTING -> WHAT MAY HELP NOW -> RECOVERY
// TRAJECTORY -> WHAT MAY NEED TO CHANGE. Deliberately shorter than the
// former single continuous-scroll page it replaces: the two Medical
// collapsibles it borrows (Capacity & Recovery Conditions, Sensory &
// Regulation) start collapsed here (defaultOpen=false) since they're
// supporting detail under WHAT'S CONTRIBUTING, not top-line content.

import { KpiDashboard } from './KpiDashboard';
import {
  BurnoutRecoveryCard,
  CapacityTodayCard,
  MyNextMoveCard,
  RevsPositionSection,
  WhatIsDrivingItCard,
  WhatMySystemNeedsCard,
} from './RecoveryView';
import { CapacityConditionsSection, SensoryRegulationSection, WhatMayNeedToChangeSection } from './MedicalView';
import type { MedicalPayload, RecoveryPayload } from './types';

function GroupHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-wb-ink2 md:col-span-2">
      {children}
    </div>
  );
}

export function NowView({ recovery, medical }: { recovery: RecoveryPayload; medical: MedicalPayload | null }) {
  return (
    <div className="flex flex-col gap-4">
      {/* ── TODAY ── */}
      <KpiDashboard kpis={recovery.kpis} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <CapacityTodayCard data={recovery} />

        {/* ── WHAT'S CONTRIBUTING ── */}
        <GroupHeading>What&rsquo;s Contributing</GroupHeading>
        <WhatIsDrivingItCard data={recovery} />
        {medical && <CapacityConditionsSection data={medical} defaultOpen={false} />}
        {medical && <SensoryRegulationSection data={medical} defaultOpen={false} />}

        {/* ── WHAT MAY HELP NOW ── */}
        <GroupHeading>What May Help Now</GroupHeading>
        <WhatMySystemNeedsCard data={recovery} />
        <MyNextMoveCard data={recovery} />

        {/* ── RECOVERY TRAJECTORY (kept a separate labelled block, never
             folded into WHAT'S CONTRIBUTING) ── */}
        <GroupHeading>Recovery Trajectory</GroupHeading>
        <BurnoutRecoveryCard data={recovery} />
        <RevsPositionSection data={recovery} className="md:col-span-2" />

        {/* ── WHAT MAY NEED TO CHANGE ── */}
        {medical && medical.redesign_candidates.length > 0 && (
          <>
            <GroupHeading>What May Need to Change</GroupHeading>
            <WhatMayNeedToChangeSection data={medical} />
          </>
        )}
      </div>
    </div>
  );
}
