'use client';

import Link from 'next/link';
import { Badge, Card } from '@/components/ui';
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

/** Medical tab — "How am I doing? Trends? Components?" LP score hero, four energy
 *  domains, the four clinical recovery indexes, and 30-day trends. */
export function MedicalView({ data }: { data: MedicalPayload }) {
  const lp = data.life_participation;
  const c = lp.components;
  const sittingPct = Math.min(Math.round((c.sitting_minutes / c.sitting_baseline) * 100), 100);

  const energyTrend = data.trends.map((t) => (t.energy ? TREND_ENERGY[t.energy] ?? null : null));
  const painTrend = data.trends.map((t) => t.pain_score);

  const signals: { label: string; value: string; met: boolean }[] = [
    { label: 'Movement', value: c.movement ? 'Done' : 'Not recorded', met: c.movement },
    { label: 'Pleasure / creativity', value: c.pleasure ?? 'Not recorded', met: !!c.pleasure },
    { label: 'Social noted', value: c.social ? 'Present' : 'Not recorded', met: c.social },
    { label: 'Sitting tolerance', value: `${c.sitting_minutes} min (${sittingPct}% of ${c.sitting_baseline})`, met: sittingPct >= 50 },
    { label: 'Workload', value: c.workload, met: c.workload === 'none' || c.workload === 'light' },
  ];

  return (
    <div className="flex flex-col gap-4">
      <Card title="Quick actions">
        <div className="flex flex-wrap gap-3">
          <Link href="/human-systems-workbench/medical/check-in" className="rounded-md bg-wb-sage-deep px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90">Check-in</Link>
          <Link href="/human-systems-workbench/medical/log-activity" className="rounded-md border border-wb-line px-4 py-2 text-[13px] font-medium text-wb-ink transition hover:border-wb-sage-deep">Log activity</Link>
          <Link href="/human-systems-workbench/medical/pulse" className="rounded-md border border-wb-line px-4 py-2 text-[13px] font-medium text-wb-ink transition hover:border-wb-sage-deep">Recovery pulse</Link>
        </div>
      </Card>

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

      <Card title="Energy Domains">
        <p className="mb-3 text-[13px] text-wb-ink2">Four-domain capacity snapshot from today&rsquo;s Human Systems row.</p>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {data.energy_domains.map((d) => (
            <div key={d.key} className="rounded-md border border-wb-line bg-wb-bg p-3">
              <div className="text-[11px] uppercase tracking-wide text-wb-ink2">{d.label}</div>
              <div className="mt-1"><Badge status={bandStatus(d.band)}>{BAND_LABEL[d.band]}</Badge></div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Recovery Indexes">
        <p className="mb-3 text-[13px] text-wb-ink2">Four clinical indicators derived from today&rsquo;s check-in.</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {data.recovery_indexes.length === 0 && (
            <div className="text-[13px] text-wb-ink2">No check-in recorded for today.</div>
          )}
          {data.recovery_indexes.map((idx) => (
            <div key={idx.key} className="flex items-start justify-between gap-2 rounded-md border border-wb-line bg-wb-bg p-3">
              <div>
                <div className="text-[13px] font-medium text-wb-ink">{idx.label}</div>
                <div className="text-[12px] text-wb-ink2">{idx.detail}</div>
              </div>
              <Badge status={bandStatus(idx.band)}>{BAND_LABEL[idx.band]}</Badge>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Trends · Last 30 days">
        <div className="grid gap-4 sm:grid-cols-2">
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
          {data.trends.length} day{data.trends.length === 1 ? '' : 's'} of recorded data in the window.
        </p>
      </Card>

    </div>
  );
}
