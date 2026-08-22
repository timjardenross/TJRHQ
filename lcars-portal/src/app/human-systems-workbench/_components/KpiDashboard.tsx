'use client';

import { Badge } from '@/components/ui';
import { BAND_LABEL, bandStatus, systemPostureStatus, type Kpis } from './types';

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

/** Cross-domain KPI strip — always visible above the active tab so recovery,
 *  readiness, and medical concerns are all legible at a glance (design
 *  proposition §4). Responsive: 3-up desktop, 2-up tablet, 1-up mobile. */
export function KpiDashboard({ kpis }: { kpis: Kpis }) {
  const lp = kpis.lp_score;
  return (
    <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
        label="Capacity Today"
        value={BAND_LABEL[kpis.capacity_band]}
        badge={<Badge status={bandStatus(kpis.capacity_band)}>{BAND_LABEL[kpis.capacity_band]}</Badge>}
      />
      <KpiCard label="Sessions · 7d" value={String(kpis.sessions_7d)} sub={kpis.sessions_7d === 1 ? 'completed session' : 'completed sessions'} />
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
