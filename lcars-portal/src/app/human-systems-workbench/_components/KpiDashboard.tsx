'use client';

import { Badge } from '@/components/ui';
import { BAND_LABEL, CAPACITY_STATE_LABEL, bandStatus, capacityStateStatus, systemPostureStatus, type Kpis } from './types';

function KpiCard({
  label,
  value,
  sub,
  badge,
}: {
  label: string;
  value: string;
  sub?: string;
  badge?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-wb-line bg-wb-surface p-4">
      <div className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">{label}</div>
      <div className="mt-1.5 flex items-center gap-2">
        {badge ?? <span className="font-serif text-[20px] leading-none text-wb-ink">{value}</span>}
      </div>
      {sub && <div className="mt-1 text-[12px] text-wb-ink2">{sub}</div>}
    </div>
  );
}

/** Cross-domain KPI strip — always visible above every section so recovery,
 *  readiness, and medical concerns are all legible at a glance (design
 *  proposition §4). Responsive: 3-up desktop, 2-up tablet, 1-up mobile.
 *  Card order is mobile-priority first (spec §25/§33: Capacity Today,
 *  then System Posture, are the two most prominent items) — on a 1-column
 *  mobile stack DOM order IS visual order, which the doc's desktop-only
 *  ASCII layout doesn't have to account for. */
export function KpiDashboard({ kpis }: { kpis: Kpis }) {
  const lp = kpis.lp_score;
  return (
    <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <KpiCard
        label="Capacity Today"
        value={kpis.latest_capacity_state ? CAPACITY_STATE_LABEL[kpis.latest_capacity_state] ?? kpis.latest_capacity_state : 'No data'}
        badge={<Badge status={capacityStateStatus(kpis.latest_capacity_state)}>{(kpis.latest_capacity_state ?? 'no data').toUpperCase()}</Badge>}
      />
      <KpiCard
        label="System Posture"
        value={kpis.system_posture}
        badge={<Badge status={systemPostureStatus(kpis.system_posture)}>{kpis.system_posture}</Badge>}
      />
      <KpiCard
        label="Life Participation"
        value={lp == null ? '—' : String(lp)}
        sub={BAND_LABEL[kpis.lp_band]}
        badge={
          <span className="flex items-baseline gap-2">
            <span className="font-serif text-[20px] leading-none text-wb-ink">{lp == null ? '—' : lp}</span>
            <Badge status={bandStatus(kpis.lp_band)}>{BAND_LABEL[kpis.lp_band]}</Badge>
          </span>
        }
      />
      <KpiCard
        label="Sleep Last Night"
        value={kpis.sleep_hours == null ? '—' : `${kpis.sleep_hours}h`}
        sub={kpis.sleep_hours == null ? 'not recorded' : undefined}
      />
      <KpiCard
        label="Check-ins Today"
        value={String(kpis.checkins_today)}
        sub={kpis.checkins_today === 1 ? '1 check-in logged' : `${kpis.checkins_today} check-ins logged`}
      />
    </div>
  );
}
