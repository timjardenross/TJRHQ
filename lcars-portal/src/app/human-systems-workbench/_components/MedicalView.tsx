'use client';

import { useState } from 'react';
import { Badge, Card } from '@/components/ui';
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

const OUTCOME_LABEL: Record<string, string> = { better: 'Better', same: 'Same', worse: 'Worse', not_completed: "Didn't do it" };

/** Medical tab content — VNext consolidation (Human_Systems_Workbench_
 *  VNext_Consolidation_Mission_Scope.md WP05-08): Life Participation
 *  (unchanged, already non-productivity-framed), Capacity Domains
 *  (renamed from Energy Domains, +Sensory), Patterns & Recovery (Recovery
 *  Conditions + Capacity Debt + Recovery Duration + 7D/30D trends), and
 *  What Helps Me (intervention effectiveness). Sessions·7D moved out of
 *  the KPI hero (WP05) — ReadinessView, rendered just above this in
 *  page.tsx, already carries that content. */
export function MedicalView({ data }: { data: MedicalPayload }) {
  const [trendWindow, setTrendWindow] = useState<'7d' | '30d'>('7d');
  const lp = data.life_participation;
  const c = lp.components;
  const sittingPct = Math.min(Math.round((c.sitting_minutes / c.sitting_baseline) * 100), 100);

  const windowedTrends = trendWindow === '7d' ? data.trends.slice(-7) : data.trends;
  const energyTrend = windowedTrends.map((t) => (t.energy ? TREND_ENERGY[t.energy] ?? null : null));
  const painTrend = windowedTrends.map((t) => t.pain_score);

  const signals: { label: string; value: string; met: boolean }[] = [
    { label: 'Movement', value: c.movement ? 'Done' : 'Not recorded', met: c.movement },
    { label: 'Pleasure / creativity', value: c.pleasure ?? 'Not recorded', met: !!c.pleasure },
    { label: 'Social noted', value: c.social ? 'Present' : 'Not recorded', met: c.social },
    { label: 'Sitting tolerance', value: `${c.sitting_minutes} min (${sittingPct}% of ${c.sitting_baseline})`, met: sittingPct >= 50 },
    { label: 'Workload', value: c.workload, met: c.workload === 'none' || c.workload === 'light' },
  ];

  const debtPct = data.capacity_debt.days_total > 0
    ? Math.round((data.capacity_debt.days_with_debt / data.capacity_debt.days_total) * 100)
    : null;

  const qualified = data.intervention_effectiveness.filter((r) => r.meets_sample_threshold);
  const unqualified = data.intervention_effectiveness.filter((r) => !r.meets_sample_threshold);

  return (
    <div className="flex flex-col gap-4">
      <Card title="Life Participation">
        <p className="mb-3 text-[13px] text-wb-ink2">
          Measures participation in life — not productivity. Recovery follows when the conditions for
          life are present; pain reduction is a downstream effect.
        </p>
        <div className="flex items-center gap-4 rounded-md border border-wb-line bg-wb-bg p-4">
          <span className="font-serif text-5xl text-wb-ink">{lp.score ?? '—'}</span>
          <div>
            <Badge status={bandStatus(lp.band)}>{BAND_LABEL[lp.band]}</Badge>
            <div className="mt-1 text-[12px] text-wb-ink2">out of 100 · today</div>
          </div>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {signals.map((s) => (
            <div key={s.label} className="flex items-start gap-2 rounded-md border border-wb-line bg-wb-surface p-3">
              <span className={`mt-0.5 text-[12px] ${s.met ? 'text-wb-ok-on' : 'text-wb-ink2'}`}>{s.met ? '●' : '○'}</span>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-wb-ink2">{s.label}</div>
                <div className="text-[13px] capitalize text-wb-ink">{s.value}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <CollapsibleSection title="Capacity Domains">
        <p className="mb-3 text-[13px] text-wb-ink2">Five perspectives on available capacity — not independent batteries.</p>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {data.capacity_domains.map((d) => (
            <div key={d.key} className="rounded-md border border-wb-line bg-wb-bg p-3">
              <div className="text-[11px] uppercase tracking-wide text-wb-ink2">{d.label}</div>
              <div className="mt-1"><Badge status={bandStatus(d.band)}>{BAND_LABEL[d.band]}</Badge></div>
            </div>
          ))}
        </div>
      </CollapsibleSection>

      <CollapsibleSection title="Patterns & Recovery">
        <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-wb-ink2">Recovery Conditions</div>
        <p className="mb-3 mt-1 text-[13px] text-wb-ink2">Inputs that influence replenishment — not Capacity itself, which is the outcome these produce.</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {data.recovery_conditions.map((idx) => (
            <div key={idx.key} className="flex items-start justify-between gap-2 rounded-md border border-wb-line bg-wb-bg p-3">
              <div>
                <div className="text-[13px] font-medium text-wb-ink">{idx.label}</div>
                <div className="text-[12px] text-wb-ink2">{idx.detail}</div>
              </div>
              <Badge status={bandStatus(idx.band)}>{BAND_LABEL[idx.band]}</Badge>
            </div>
          ))}
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-wb-line bg-wb-bg p-3">
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
          <div className="rounded-md border border-wb-line bg-wb-bg p-3">
            <div className="text-[11px] uppercase tracking-wide text-wb-ink2">Recovery Time</div>
            <div className="mt-1 font-serif text-2xl text-wb-ink">
              {data.recovery_duration.sample_size < 3 ? '—' : data.recovery_duration.most_common}
            </div>
            <p className="mt-1 text-[12px] text-wb-ink2">
              {data.recovery_duration.sample_size < 3
                ? 'Not enough deep-check records yet.'
                : `Most common of ${data.recovery_duration.sample_size} records (last 30 days).`}
            </p>
          </div>
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

      <CollapsibleSection title="What Helps Me">
        {data.intervention_effectiveness.length === 0 ? (
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
