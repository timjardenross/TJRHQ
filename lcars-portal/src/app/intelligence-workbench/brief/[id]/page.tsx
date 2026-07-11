'use client';

// Phase B — Screens 2 & 3: Brief Review + Approval Gate (standalone brand).
import { useCallback, useEffect, useState } from 'react';
import { Card, RiskPill, Shell } from '../../_components/Shell';
import { runAction } from '../../_components/actions';

const GATE_FLOW = [
  'IN_REVIEW', 'DATA_QA_PASSED', 'FACTUAL_QA_PASSED', 'ANALYTICAL_QA_PASSED',
  'QA_READY', 'EXECUTIVE_APPROVED', 'PUBLISHED',
];
const GATE_LABEL: Record<string, string> = {
  IN_REVIEW: 'In Review', DATA_QA_PASSED: 'Data QA', FACTUAL_QA_PASSED: 'Factual QA',
  ANALYTICAL_QA_PASSED: 'Analytical QA', QA_READY: 'QA Ready',
  EXECUTIVE_APPROVED: 'Approved', PUBLISHED: 'Published',
};

type Brief = {
  brief_id: string; overall_risk: string | null; approval_status: string | null;
  approval_audit: Record<string, { status?: string; approved_by?: string }> | null;
  executive_snapshot: string | null; bottom_line: string | null;
  period_start: string | null; period_end: string | null; signal_ids: string[] | null;
};
type Signal = {
  event_id: string; raw_title: string; sector: string | null; geography: string | null;
  risk_rating: string | null; rank_score: number | null; source_tier: number | null;
  confidence_level: string | null; cluster_similarity: number | null; analysis_summary: string | null;
};

export default function BriefReview({ params }: { params: { id: string } }) {
  const id = params.id;
  const [brief, setBrief] = useState<Brief | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`/api/intelligence-workbench/brief?id=${id}`)
      .then((r) => r.json())
      .then((d) => { setBrief(d.brief); setSignals(d.signals ?? []); })
      .finally(() => setLoading(false));
  }, [id]);
  useEffect(load, [load]);

  const act = async (action: string, payload: Record<string, unknown>, label: string) => {
    setBusy(label); setMsg(null);
    const { status, body } = await runAction(action, { brief_id: id, ...payload });
    setBusy(null);
    const err = (body as { error?: string })?.error;
    setMsg(status === 200 ? `✓ ${label} succeeded` : `✗ ${label}: ${err ?? status}`);
    load();
  };

  const status = brief?.approval_status ?? 'IN_REVIEW';
  const curIdx = GATE_FLOW.indexOf(status);
  const audit = brief?.approval_audit ?? {};
  const gatePassed = (g: string) => audit?.[g]?.status === 'passed';
  const title = (brief?.executive_snapshot ?? '').split('.')[0]?.slice(0, 90) || `Brief ${id.slice(0, 8)}`;

  return (
    <Shell title="Brief Review" back={{ href: '/intelligence-workbench', label: 'Overview' }}
           right={brief ? <RiskPill value={brief.overall_risk} /> : ''}>
      {loading ? (
        <p className="text-[13px] text-wb-ink2">Loading…</p>
      ) : !brief ? (
        <p className="text-[13px] text-wb-ink2">Brief not found.</p>
      ) : (
        <>
          <Card title={title}>
            <p className="mb-2 text-[13px] text-wb-ink2">
              {brief.period_start} → {brief.period_end} · {(brief.signal_ids ?? []).length} signals
            </p>
            <p className="text-sm">{brief.executive_snapshot ?? brief.bottom_line ?? '—'}</p>
            {/* gate progress */}
            <div className="mt-5 flex flex-wrap items-center gap-1.5 text-[12px]">
              {GATE_FLOW.map((g, i) => (
                <span key={g}
                  className={`rounded-full border px-2.5 py-1 ${
                    i < curIdx ? 'border-wb-ok/40 bg-wb-ok/15 text-wb-ok'
                    : i === curIdx ? 'border-wb-sage bg-wb-sage text-white'
                    : 'border-wb-line text-wb-ink2'}`}>
                  {i < curIdx ? '✓ ' : ''}{GATE_LABEL[g]}
                </span>
              ))}
            </div>
          </Card>

          <Card title={`Signals (${signals.length})`}>
            <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
              {signals.map((s) => (
                <div key={s.event_id} className="rounded-lg border border-wb-line p-3.5">
                  <h4 className="mb-2 text-[13.5px] font-semibold leading-snug">{s.raw_title}</h4>
                  <p className="mb-2 text-[11.5px] text-wb-ink2">
                    {s.sector ?? '—'} · {s.geography ?? '—'} · {s.source_tier ? `Tier ${s.source_tier}` : '—'}
                  </p>
                  <div className="flex items-center gap-2">
                    <RiskPill value={s.risk_rating} />
                    <span className="font-serif text-[15px]">{s.rank_score != null ? Math.round(s.rank_score) : '—'}/50</span>
                  </div>
                  {(s.confidence_level || s.cluster_similarity != null) && (
                    <p className="mt-2 text-[11px] text-wb-sage-deep">
                      {s.confidence_level ?? ''}{s.cluster_similarity != null ? ` · sim ${s.cluster_similarity}` : ''}
                    </p>
                  )}
                </div>
              ))}
              {signals.length === 0 && <p className="text-[13px] text-wb-ink2">No linked signals.</p>}
            </div>
          </Card>

          {/* Screen 3 — approval gate */}
          <Card title="Approval gate">
            {(['data_qa', 'factual_qa', 'analytical_qa'] as const).map((g) => (
              <div key={g} className="flex items-center gap-3 border-b border-wb-line py-2.5 text-[13.5px] last:border-0">
                <span className={`grid h-5 w-5 place-items-center rounded text-[11px] text-white ${gatePassed(g) ? 'bg-wb-ok' : 'bg-wb-line'}`}>
                  {gatePassed(g) ? '✓' : ''}
                </span>
                <span className="flex-1 capitalize">{g.replace('_', ' ')}</span>
                {audit?.[g]?.approved_by && <span className="text-[11.5px] text-wb-ink2">{audit[g].approved_by}</span>}
                {!gatePassed(g) && (
                  <button disabled={!!busy} onClick={() => act('brief.qa_gate', { gate: g }, `${g} pass`)}
                    className="rounded-md border border-wb-sage px-2.5 py-1 text-[12px] text-wb-sage-deep hover:bg-wb-sage/10 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">
                    Pass
                  </button>
                )}
              </div>
            ))}
            <div className="mt-4 flex flex-wrap gap-2.5">
              <button disabled={!!busy} onClick={() => act('brief.mark_qa_ready', {}, 'Mark QA ready')}
                className="rounded-md border border-wb-sage bg-wb-sage px-3.5 py-2 text-[13px] text-white transition hover:-translate-y-px disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
                Mark QA Ready
              </button>
              <button disabled={!!busy} onClick={() => act('brief.publish', {}, 'Publish')}
                className="rounded-md border border-wb-sage-deep bg-wb-sage-deep px-3.5 py-2 text-[13px] text-white transition hover:-translate-y-px disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink">
                Publish
              </button>
              <button disabled={!!busy} onClick={() => act('brief.escalate', {}, 'Escalate to RED')}
                className="rounded-md border border-wb-crit bg-wb-crit px-3.5 py-2 text-[13px] text-white transition hover:-translate-y-px disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-crit">
                Escalate to RED
              </button>
              <a href={`/intelligence-workbench/escalation/${id}`}
                 className="rounded-md border border-wb-line px-3.5 py-2 text-[13px] text-wb-ink2 hover:bg-wb-line/40">
                Open escalation →
              </a>
            </div>
            {busy && <p className="mt-3 text-[12px] text-wb-ink2" aria-live="polite">Working: {busy}…</p>}
            {msg && <p className="mt-3 text-[12px]" aria-live="polite">{msg}</p>}
          </Card>
        </>
      )}
    </Shell>
  );
}
