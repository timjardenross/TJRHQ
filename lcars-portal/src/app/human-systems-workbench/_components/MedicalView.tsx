'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui';
import { CollapsibleSection } from './CollapsibleSection';
import { BAND_LABEL, bandStatus, type MedicalPayload } from './types';

const TREND_ENERGY: Record<string, number> = { High: 3, Moderate: 2, Low: 1 };

/** Tiny inline sparkline for a 30-day categorical/numeric trend. Accessible
 *  alternative (the underlying rows) is summarised in text beneath. */
function Sparkline({ values }: { values: (number | null)[] }) {
  const pts = values.map((v, i) => ({ v, i })).filter((p) => p.v != null) as { v: number; i: number }[];
  if (pts.length < 2) return <span className="text-[12px] text-wb-ink2">Not enough data</span>;
  const max = Math.max(...pts.map((p) => p.v));
  const min = Math.min(...pts.map((p) => p.v));
  const span = max - min || 1;
  const w = 160;
  const h = 28;
  const n = values.length - 1 || 1;
  const path = pts
    .map((p, k) => {
      const x = (p.i / n) * w;
      const y = h - ((p.v - min) / span) * h;
      return `${k === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible" aria-hidden="true">
      <path d={path} fill="none" strokeWidth="1.5" className="stroke-wb-sage-deep" />
    </svg>
  );
}

/** Medical tab content. VNext consolidation, updated after finding real
 *  duplication between the two source signal sets: "Sensory" (a Capacity
 *  Domain) and "Sensory load" (a Recovery Condition) were the exact same
 *  capacity_checkins.stimulation_state field rendered twice. Capacity
 *  Domains and Recovery Conditions are now one merged grid — 8 unique
 *  signals — under a single "Capacity & Recovery Conditions" card.
 *  Physical dropped entirely (2026-08-22, Captain directive):
 *  human_systems_daily is dead and capacity_checkins has no substitute
 *  field for it, unlike Cognitive (now sourced from executive_function,
 *  route.ts). Recovery Time moved into the grid (2026-08-22, Captain
 *  directive — 7 tiles read as an odd fit for the 4-column layout); its
 *  separate stat block below was dropped as redundant, leaving Capacity
 *  Debt as the sole remaining stat block. What Helps Me moved to
 *  RecoveryView (next to My REVS Position); this file no longer renders
 *  it. */
export function MedicalView({ data }: { data: MedicalPayload }) {
  const [trendWindow, setTrendWindow] = useState<'7d' | '30d'>('7d');

  const windowedTrends = trendWindow === '7d' ? data.trends.slice(-7) : data.trends;
  const energyTrend = windowedTrends.map((t) => (t.energy ? TREND_ENERGY[t.energy] ?? null : null));
  const painTrend = windowedTrends.map((t) => t.pain_score);

  const debtPct = data.capacity_debt.days_total > 0
    ? Math.round((data.capacity_debt.days_with_debt / data.capacity_debt.days_total) * 100)
    : null;

  // Merge domains + conditions, dropping the one exact duplicate: "sensory"
  // (domain) === "sensory_load" (condition) — same field, keep the
  // condition's version since its `detail` text is more descriptive than
  // the domain's bare value. Recovery Time now included in the grid too
  // (2026-08-22, Captain directive — 7 tiles read as an odd fit for the
  // 4-column layout; Recovery Time was already tile-shaped, just filtered
  // out in favour of the stat block below, which is now redundant and
  // removed).
  const domainSignals = data.capacity_domains
    .filter((d) => d.key !== 'sensory')
    .map((d) => ({ key: d.key, label: d.label, band: d.band, detail: d.value ?? 'Not recorded' }));
  const signals = [...domainSignals, ...data.recovery_conditions];

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <CollapsibleSection title="Capacity & Recovery Conditions" className="md:col-span-2">
        <p className="mb-3 text-[13px] text-wb-ink2">
          Perspectives on capacity and what feeds it — not independent batteries, and not Capacity itself
          (Capacity is the outcome these produce).
        </p>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {signals.map((s) => (
            <div key={s.key} className="flex items-start justify-between gap-2 rounded-md border border-wb-line bg-wb-bg p-3">
              <div>
                <div className="text-[13px] font-medium text-wb-ink">{s.label}</div>
                <div className="text-[12px] text-wb-ink2">{s.detail}</div>
              </div>
              <Badge status={bandStatus(s.band)}>{BAND_LABEL[s.band]}</Badge>
            </div>
          ))}
        </div>

        <div className="mt-4 rounded-md border border-wb-line bg-wb-bg p-3">
          <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Capacity Debt</div>
          <div className="mt-1 font-serif text-2xl text-wb-ink">
            {data.capacity_debt.days_total === 0 ? '—' : `${data.capacity_debt.days_with_debt} of ${data.capacity_debt.days_total} days`}
          </div>
          <p className="mt-1 text-[12px] text-wb-ink2">
            {data.capacity_debt.days_total === 0
              ? 'No evening reflections logged in the last 7 days.'
              : debtPct && debtPct >= 40
                ? 'Maintaining output today appears to be increasing tomorrow’s recovery requirement.'
                : `Last ${data.capacity_debt.window_days} days.`}
          </p>
        </div>

        <div className="mt-4 flex items-center justify-between">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-wb-ink2">Trends</div>
          <div className="flex overflow-hidden rounded-md border border-wb-line text-[11px]">
            <button
              onClick={() => setTrendWindow('7d')}
              className={`px-2.5 py-1 ${trendWindow === '7d' ? 'bg-wb-sage-deep text-white' : 'text-wb-ink2 hover:bg-wb-line/40'}`}
            >7 days</button>
            <button
              onClick={() => setTrendWindow('30d')}
              className={`px-2.5 py-1 ${trendWindow === '30d' ? 'bg-wb-sage-deep text-white' : 'text-wb-ink2 hover:bg-wb-line/40'}`}
            >30 days</button>
          </div>
        </div>
        <div className="mt-2 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Energy</div>
            <Sparkline values={energyTrend} />
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Pain</div>
            <Sparkline values={painTrend} />
          </div>
        </div>
        <p className="mt-3 text-[12px] text-wb-ink2">
          {windowedTrends.length} day{windowedTrends.length === 1 ? '' : 's'} of recorded data in the window.
        </p>
      </CollapsibleSection>

      {data.redesign_candidates.length > 0 && (
        <CollapsibleSection title="Things I Should Change, Not Keep Coping With">
          <p className="mb-3 text-[13px] text-wb-ink2">Loads that recurred on stretched or depleted days in the last 30 days — worth changing rather than repeatedly regulating around.</p>
          <div className="flex flex-col gap-2">
            {data.redesign_candidates.map((r) => (
              <div key={r.load} className="flex items-center justify-between gap-2 rounded-md border border-wb-line bg-wb-bg p-3">
                <div className="text-[13px] text-wb-ink">{r.load}</div>
                <Badge status="warning">{r.stretched_or_depleted_count}/{r.window_days} days</Badge>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}
    </div>
  );
}
