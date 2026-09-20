'use client';

import { Badge, KpiCard, type BadgeStatus } from '@/components/ui';
import { CAPACITY_STATE_LABEL, capacityStateStatus, systemPostureStatus, type RecoveryPayload } from './types';

// Energy (recovery.energy, top-level RecoveryPayload field — High/Moderate/
// Low, see route.ts's energyFromCapacityState()/analytics_health_daily
// comparisons) has no existing status-mapping helper elsewhere in this
// workbench, unlike capacity_state/system_posture — added here rather than
// inventing a new shared export for a single call site.
const ENERGY_STATUS: Record<string, BadgeStatus> = { High: 'success', Moderate: 'info', Low: 'warning' };

// Executive Function (recovery.executive_function) — same vocabulary and
// intent as RecoveryView.tsx's local EF_LABEL, kept here rather than
// imported since that file's copy is phrased for a different card
// ("Working well" vs. this tile's plain label) and duplicating a 4-entry
// map is cheaper than forcing one shared string set on two different UIs.
const EF_LABEL: Record<string, string> = {
  good: 'Good', strained: 'Strained', difficult: 'Difficult', very_difficult: 'Very Difficult',
};
const EF_STATUS: Record<string, BadgeStatus> = {
  good: 'success', strained: 'info', difficult: 'warning', very_difficult: 'error',
};

/** Cross-domain KPI strip — always visible above every section so recovery,
 *  readiness, and medical concerns are all legible at a glance (design
 *  proposition §4). Responsive: 2-up tablet, 4-up desktop — 4 tiles now,
 *  not 3 (mission USS-TJR-MSN-0394 §1.1, deep Human Systems mockup
 *  alignment pass, Phase 11): the mockup's Overview panel shows Current
 *  Capacity / Execution Posture / Energy / Focus.
 *
 *  Real-data mapping, not a 1:1 relabel of all four — flagged rather than
 *  silently forced (mission §1's "no fabricated data" discipline, same as
 *  Phase 4/5's own flagged mismatches):
 *   - Current Capacity  -> kpis.latest_capacity_state (was "Capacity Today").
 *   - Execution Posture -> kpis.system_posture (was "System Posture").
 *   - Energy            -> recovery.energy (High/Moderate/Low) — real,
 *     already computed, just not previously surfaced in this strip.
 *   - Focus              -- NOT built as shown. The mockup's exact "Focus —
 *     Moderate / Some distraction" stat has no backing field anywhere in
 *     RecoveryPayload/MedicalPayload/Kpis (checked api/human-systems/
 *     route.ts directly — no focus/distraction concept exists in the data
 *     model at all, unlike Energy which is a real field with a different
 *     display name). The closest real, already-computed signal is
 *     Executive Function (recovery.executive_function — good/strained/
 *     difficult/very_difficult), already shown lower on this same page
 *     (RecoveryView.tsx's CapacityTodayCard). Shown here under its real
 *     name, not relabelled "Focus", so nothing implies a stat that isn't
 *     actually being tracked. A real "Focus" signal would need new
 *     capture, which is out of scope for a presentation-only pass.
 *
 *  Check-ins Today (the former 3rd tile) is kept as this strip's sub-line
 *  rather than dropped — the mockup's 4-tile grid has no room for a 5th
 *  card, but the information itself is still real and worth keeping
 *  visible, not silently removed. */
export function KpiDashboard({ recovery }: { recovery: RecoveryPayload }) {
  const { kpis } = recovery;
  const energyStatus: BadgeStatus = recovery.energy ? ENERGY_STATUS[recovery.energy] ?? 'neutral' : 'neutral';
  const ef = recovery.executive_function;

  return (
    <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        label="Current Capacity"
        value={kpis.latest_capacity_state ? CAPACITY_STATE_LABEL[kpis.latest_capacity_state] ?? kpis.latest_capacity_state : 'No data'}
        badge={<Badge status={capacityStateStatus(kpis.latest_capacity_state)}>{(kpis.latest_capacity_state ?? 'no data').toUpperCase()}</Badge>}
        sub={
          (kpis.checkins_today === 1 ? '1 check-in logged today' : `${kpis.checkins_today} check-ins logged today`) +
          (kpis.has_midday_checkin
            ? ` · midday: ${
                kpis.latest_midday_capacity_state
                  ? CAPACITY_STATE_LABEL[kpis.latest_midday_capacity_state] ?? kpis.latest_midday_capacity_state
                  : 'logged'
              }`
            : ' · no midday check-in yet')
        }
      />
      <KpiCard
        label="Execution Posture"
        value={kpis.system_posture}
        badge={<Badge status={systemPostureStatus(kpis.system_posture)}>{kpis.system_posture}</Badge>}
      />
      <KpiCard
        label="Energy"
        value={recovery.energy ?? 'No data'}
        badge={<Badge status={energyStatus}>{(recovery.energy ?? 'no data').toUpperCase()}</Badge>}
      />
      <KpiCard
        label="Executive Function"
        value={ef ? EF_LABEL[ef] ?? ef : 'No data'}
        badge={<Badge status={ef ? EF_STATUS[ef] ?? 'neutral' : 'neutral'}>{(ef ? EF_LABEL[ef] ?? ef : 'no data').toUpperCase()}</Badge>}
      />
    </div>
  );
}
