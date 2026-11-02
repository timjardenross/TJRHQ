'use client';

// NOW tab — the default view of the Human Systems redesign (2026-09-06).
// Assembles the primary decision-support flow in the spec's required
// order: TODAY -> WHAT'S CONTRIBUTING -> WHAT MAY HELP NOW -> RECOVERY
// TRAJECTORY -> WHAT MAY NEED TO CHANGE. Deliberately shorter than the
// former single continuous-scroll page it replaces: the two Medical
// collapsibles it borrows (Capacity & Recovery Conditions, Sensory &
// Regulation) start collapsed here (defaultOpen=false) since they're
// supporting detail under WHAT'S CONTRIBUTING, not top-line content.

import { useState } from 'react';
import { useAbortEffect } from '@/hooks/useAbortEffect';
import type { GoodDaysPayload } from '@/app/api/human-systems/good-days-data';
import { DayPlanCard } from './DayPlanCard';
import { GoodDaysCard } from './GoodDaysCard';
import { KpiDashboard } from './KpiDashboard';
import { CapacityTrendCard } from './CapacityTrendCard';
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
import { CollapsibleSection } from './CollapsibleSection';

function GroupHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-2 text-wb-label font-semibold uppercase tracking-[0.14em] text-wb-ink2 md:col-span-2">
      {children}
    </div>
  );
}

export function NowView({ recovery, medical }: { recovery: RecoveryPayload; medical: MedicalPayload | null }) {
  // Good days (last 14 days): one fetch for the card at the top of the tab.
  const [goodDays, setGoodDays] = useState<GoodDaysPayload | null>(null);
  const [goodDaysError, setGoodDaysError] = useState<string | null>(null);
  useAbortEffect((signal, alive) => {
    fetch('/api/human-systems/good-days', { cache: 'no-store', signal })
      .then((r) => r.json())
      .then((d) => {
        if (d?.error) throw new Error(d.error);
        if (alive()) setGoodDays(d as GoodDaysPayload);
      })
      .catch((err) => {
        if (alive() && !(err instanceof Error && err.name === 'AbortError')) {
          setGoodDaysError(err instanceof Error ? err.message : 'Failed to load good days');
        }
      });
  }, []);

  return (
    <div className="flex flex-col gap-4">
      {/* ── GOOD DAYS (the headline) ── */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <GoodDaysCard data={goodDays} error={goodDaysError} />
      </div>

      {/* ── TODAY ── */}
      <KpiDashboard recovery={recovery} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Capacity Trend — mockup panel 3's "Capacity Trend — Last 14
            days" bar chart, placed directly under the 4-tile grid it sits
            beside in the mockup, ahead of "What's Contributing". */}
        <CollapsibleSection title="Capacity trend · 14 days" defaultOpen={false}>
          <CapacityTrendCard />
        </CollapsibleSection>

        <CapacityTodayCard data={recovery} />
        <DayPlanCard data={recovery} />

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
        <CollapsibleSection title="Recovery trajectory" className="md:col-span-2" defaultOpen={false}>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <BurnoutRecoveryCard data={recovery} />
            <RevsPositionSection data={recovery} />
          </div>
        </CollapsibleSection>

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
