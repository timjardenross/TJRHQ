'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui';
import { CollapsibleSection } from './CollapsibleSection';
import {
  BAND_LABEL,
  bandStatus,
  NATURAL_REGULATION_LABEL,
  SENSORY_CHANNEL_LABEL,
  SENSORY_RESPONSE_LABEL,
  sensoryResponseStatus,
  type MedicalPayload,
} from './types';

// Coarse stimulation_state ('low'|'balanced'|'high') display labels — same
// vocabulary RecoveryView.tsx's own local STIMULATION_LABEL uses, kept as
// a separate local const here rather than promoted to a shared types.ts
// export to avoid touching RecoveryView.tsx (a peer agent's file this
// mission) for an unrelated rename.
const STIMULATION_STATE_LABEL: Record<string, string> = {
  low: 'Not enough', balanced: 'Balanced', high: 'Too much',
};

const TREND_ENERGY: Record<string, number> = { High: 3, Moderate: 2, Low: 1 };
// Ordinal mapping for nervous_system_state, the other 30-day trend field
// the route already fetches but wasn't rendering. sleep_quality (also
// fetched) is NOT added here — checked live 2026-08-27: 0 of 7 recent
// analytics_health_daily rows have it populated. Its only two writers
// (health_daily_logs, captains_log_entries) are already retired and the
// capacity_checkins backfill above never covered it either — a
// structurally dead field, not just sparse, so a sparkline for it would
// permanently read "Not enough data" rather than fill in over time.
// Values are case-inconsistent across writers (migrations 0134/0016 use
// lowercase 'calm'/'activated'/'dysregulated'), looked up lowercase.
// Higher = calmer.
const TREND_NS: Record<string, number> = { dysregulated: 1, activated: 2, calm: 3 };

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
  const nsTrend = windowedTrends.map((t) => (t.nervous_system_state ? TREND_NS[t.nervous_system_state.toLowerCase()] ?? null : null));

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
          <div>
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Nervous System</div>
            <Sparkline values={nsTrend} />
          </div>
        </div>
        <p className="mt-3 text-[12px] text-wb-ink2">
          {windowedTrends.length} day{windowedTrends.length === 1 ? '' : 's'} of recorded data in the window.
        </p>
      </CollapsibleSection>

      <CollapsibleSection title="Sensory & Regulation" className="md:col-span-2">
        <p className="mb-3 text-[13px] text-wb-ink2">
          Detail underneath the Stimulation reading above — an optional deeper layer (V3 doc §10/§11), not asked
          on every check-in, so it may be empty even on days with a lot recorded elsewhere.
        </p>

        <div className="rounded-md border border-wb-line bg-wb-bg p-3">
          <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Sensory profile</div>
          <div className="mt-1 flex items-center gap-2">
            <span className="text-[13px] text-wb-ink">Overall stimulation</span>
            <Badge status="neutral">
              {data.sensory_profile.stimulation_state
                ? STIMULATION_STATE_LABEL[data.sensory_profile.stimulation_state] ?? data.sensory_profile.stimulation_state
                : 'Not recorded'}
            </Badge>
          </div>
          {data.sensory_profile.channels && Object.keys(data.sensory_profile.channels).length > 0 ? (
            <div className="mt-2 flex flex-col gap-1.5">
              {(Object.entries(data.sensory_profile.channels) as [keyof typeof SENSORY_CHANNEL_LABEL, keyof typeof SENSORY_RESPONSE_LABEL][]).map(
                ([channel, response]) => (
                  <div key={channel} className="flex items-center justify-between gap-2">
                    <span className="text-[13px] text-wb-ink">{SENSORY_CHANNEL_LABEL[channel]}</span>
                    <Badge status={sensoryResponseStatus(response)}>{SENSORY_RESPONSE_LABEL[response]}</Badge>
                  </div>
                ),
              )}
            </div>
          ) : (
            <p className="mt-2 text-[12px] text-wb-ink2">No specific channel recorded as standing out.</p>
          )}
        </div>

        <div className="mt-3 rounded-md border border-wb-line bg-wb-bg p-3">
          <div className="text-[11px] uppercase tracking-wide text-wb-ink2">What my system seems to want</div>
          <div className="mt-1">
            <Badge status="neutral">
              {data.natural_regulation.response ? NATURAL_REGULATION_LABEL[data.natural_regulation.response] : 'Not recorded'}
            </Badge>
          </div>
          {data.natural_regulation.suppressed === true && (
            <p className="mt-2 text-[12px] text-wb-ink2">
              Flagged as something being held back because it feels inappropriate, inconvenient, or noticeable —
              this feeds compensation-cost learning, not a prompt to correct it.
            </p>
          )}
        </div>
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
