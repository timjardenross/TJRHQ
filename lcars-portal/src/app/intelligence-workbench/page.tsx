'use client';

// Phase B — Intelligence Workbench · Screen 1 (Overview). Standalone brand surface.
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, RiskPill, Shell } from './_components/Shell';

type Brief = {
  brief_id: string; overall_risk: string | null; approval_status: string | null;
  executive_snapshot: string | null; signal_ids: string[] | null;
};
type Signal = {
  event_id: string; raw_title: string; sector: string | null; geography: string | null;
  risk_rating: string | null; rank_score: number | null; source_tier: number | null;
};
type Payload = {
  kpis: { signals_7d?: number; briefs_pending?: number; red_active?: number };
  briefs: Brief[]; hotSignals: Signal[];
};

export default function Overview() {
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
    <Shell title="Intelligence Workbench" right="Routine mode · last 7 days">
      <div className="mb-8 grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        {[
          { n: k.signals_7d ?? 0, l: 'Signals collected (7d)', red: false },
          { n: k.briefs_pending ?? 0, l: 'Briefs pending approval', red: false },
          { n: k.red_active ?? 0, l: 'RED incidents active', red: true },
        ].map((c) => (
          <div key={c.l} className="rounded-lg border border-wb-line bg-wb-surface p-4 shadow-sm">
            <div className={`font-serif text-3xl ${c.red && c.n > 0 ? 'text-wb-crit' : ''}`}>{c.n}</div>
            <div className="text-[12px] text-wb-ink2">{c.l}</div>
          </div>
        ))}
        <div className="rounded-lg border border-wb-line bg-wb-surface p-4 shadow-sm">
          <div className="font-serif text-3xl text-wb-sage-deep">Live</div>
          <div className="text-[12px] text-wb-ink2">Pipeline status</div>
        </div>
      </div>

      <Card title="Briefs — gate status">
        {loading ? (
          <p className="text-[13px] text-wb-ink2">Loading…</p>
        ) : (data?.briefs.length ?? 0) === 0 ? (
          <p className="text-[13px] text-wb-ink2">No pending briefs.</p>
        ) : (
          data!.briefs.map((b) => (
            <div key={b.brief_id} className="flex items-center gap-3 border-b border-wb-line py-2.5 text-sm last:border-0">
              <RiskPill value={b.overall_risk} />
              <span className="flex-1">{briefTitle(b)}</span>
              <span className="text-[12px] text-wb-ink2">{b.approval_status ?? 'IN_REVIEW'}</span>
              <Link href={`/intelligence-workbench/brief/${b.brief_id}`}
                className="rounded-md border border-wb-sage bg-wb-sage px-3 py-1.5 text-[13px] text-white transition hover:-translate-y-px focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                Review Brief →
              </Link>
            </div>
          ))
        )}
      </Card>

      <Card title="Hot incidents — by operational relevance">
        {loading ? (
          <p className="text-[13px] text-wb-ink2">Loading…</p>
        ) : (data?.hotSignals.length ?? 0) === 0 ? (
          <p className="text-[13px] text-wb-ink2">No signals in the last 7 days.</p>
        ) : (
          data!.hotSignals.map((s) => (
            <div key={s.event_id} className="flex items-center gap-3 border-b border-wb-line py-2.5 text-sm last:border-0">
              <RiskPill value={s.risk_rating} />
              <span className="flex-1">{s.raw_title}</span>
              <span className="text-[11px] text-wb-ink2">
                {s.source_tier ? `Tier ${s.source_tier}` : '—'} · {s.sector ?? '—'}
              </span>
              <span className="font-serif text-[15px]">{s.rank_score != null ? Math.round(s.rank_score) : '—'}</span>
            </div>
          ))
        )}
      </Card>
    </Shell>
  );
}
