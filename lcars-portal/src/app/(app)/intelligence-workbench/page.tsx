'use client';

// Phase B — Intelligence Workbench · Screen 1 (Overview, routine mode).
// Warm brand palette (wb.* tokens). Read-only; bound to real Phase A columns.

import { useEffect, useState } from 'react';

type Brief = {
  brief_id: string;
  overall_risk: string | null;
  approval_status: string | null;
  executive_snapshot: string | null;
  signal_ids: string[] | null;
};
type Signal = {
  event_id: string;
  raw_title: string;
  sector: string | null;
  geography: string | null;
  risk_rating: string | null;
  rank_score: number | null;
  source_tier: number | null;
};
type Payload = {
  kpis: { signals_7d?: number; briefs_pending?: number; red_active?: number };
  briefs: Brief[];
  hotSignals: Signal[];
};

const riskBadge = (r: string | null) => {
  const v = (r ?? '').toUpperCase();
  if (v === 'RED' || v === 'HIGH') return 'bg-wb-crit/15 text-wb-crit';
  if (v === 'AMBER' || v === 'MEDIUM') return 'bg-wb-warn/15 text-wb-warn';
  if (v === 'GREEN' || v === 'LOW') return 'bg-wb-ok/15 text-wb-ok';
  return 'bg-wb-line text-wb-ink2';
};

export default function IntelligenceWorkbenchOverview() {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/intelligence-workbench')
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ kpis: {}, briefs: [], hotSignals: [] }))
      .finally(() => setLoading(false));
  }, []);

  const k = data?.kpis ?? {};
  const briefTitle = (b: Brief) =>
    (b.executive_snapshot ?? '').split('.')[0]?.slice(0, 80) || `Brief ${b.brief_id.slice(0, 8)}`;

  return (
    <div className="min-h-[100dvh] bg-wb-bg text-wb-ink px-6 py-8 font-sans">
      <div className="mx-auto max-w-4xl">
        <h1 className="font-serif text-[26px] tracking-tight">Intelligence Workbench</h1>
        <p className="mb-8 text-[13px] text-wb-ink2">Operational Resilience · routine mode · last 7 days</p>

        {/* KPIs */}
        <div className="mb-8 grid grid-cols-2 gap-3.5 sm:grid-cols-4">
          {[
            { n: k.signals_7d ?? 0, l: 'Signals collected (7d)', red: false },
            { n: k.briefs_pending ?? 0, l: 'Briefs pending approval', red: false },
            { n: k.red_active ?? 0, l: 'RED incidents active', red: true },
          ].map((c) => (
            <div key={c.l} className="rounded border border-wb-line bg-wb-surface p-4">
              <div className={`font-serif text-3xl ${c.red && c.n > 0 ? 'text-wb-crit' : ''}`}>{c.n}</div>
              <div className="text-[12px] text-wb-ink2">{c.l}</div>
            </div>
          ))}
          <div className="rounded border border-wb-line bg-wb-surface p-4">
            <div className="font-serif text-3xl text-wb-sage-deep">Live</div>
            <div className="text-[12px] text-wb-ink2">Pipeline status</div>
          </div>
        </div>

        {/* Briefs by gate status */}
        <section className="mb-6 rounded border border-wb-line bg-wb-surface p-6 shadow-sm">
          <h2 className="mb-3 border-b border-wb-line pb-3 font-serif text-lg">Briefs — gate status</h2>
          {loading ? (
            <p className="text-[13px] text-wb-ink2">Loading…</p>
          ) : (data?.briefs.length ?? 0) === 0 ? (
            <p className="text-[13px] text-wb-ink2">No pending briefs.</p>
          ) : (
            data!.briefs.map((b) => (
              <div key={b.brief_id} className="flex items-center gap-3 border-b border-wb-line py-2.5 text-sm last:border-0">
                <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${riskBadge(b.overall_risk)}`}>
                  {b.overall_risk ?? '—'}
                </span>
                <span className="flex-1">{briefTitle(b)}</span>
                <span className="text-[12px] text-wb-ink2">{b.approval_status ?? 'IN_REVIEW'}</span>
                <button className="rounded border border-wb-sage bg-wb-sage px-3 py-1.5 text-[13px] text-white transition hover:-translate-y-px">
                  Review Brief →
                </button>
              </div>
            ))
          )}
        </section>

        {/* Hot incidents */}
        <section className="rounded border border-wb-line bg-wb-surface p-6 shadow-sm">
          <h2 className="mb-3 border-b border-wb-line pb-3 font-serif text-lg">Hot incidents — by operational relevance</h2>
          {loading ? (
            <p className="text-[13px] text-wb-ink2">Loading…</p>
          ) : (data?.hotSignals.length ?? 0) === 0 ? (
            <p className="text-[13px] text-wb-ink2">No signals in the last 7 days.</p>
          ) : (
            data!.hotSignals.map((s) => (
              <div key={s.event_id} className="flex items-center gap-3 border-b border-wb-line py-2.5 text-sm last:border-0">
                <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${riskBadge(s.risk_rating)}`}>
                  {s.risk_rating ?? '—'}
                </span>
                <span className="flex-1">{s.raw_title}</span>
                <span className="text-[11px] text-wb-ink2">
                  {s.source_tier ? `Tier ${s.source_tier}` : '—'} · {s.sector ?? '—'}
                </span>
                <span className="font-serif text-[15px]">{s.rank_score != null ? Math.round(s.rank_score) : '—'}</span>
              </div>
            ))
          )}
        </section>
      </div>
    </div>
  );
}
