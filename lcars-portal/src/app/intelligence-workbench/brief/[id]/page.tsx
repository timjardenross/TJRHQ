'use client';

// Phase B — Screens 2 & 3: Brief Review + Approval Gate (standalone brand).
import { useCallback, useEffect, useState } from 'react';
import { Card, Modal, RiskPill, WorkbenchShell } from '@/components/ui';
import { runAction } from '../../_components/actions';

// 2026-07-18: consolidated from the original 7-stage ladder (In Review / Data
// QA / Factual QA / Analytical QA / QA Ready / Approved / Published) per
// Captain feedback — live data showed the three QA gates were never used
// distinctly (one brief ever published, all three passed by the same actor
// in one sitting) while every other brief sat permanently at In Review.
const GATE_FLOW = ['IN_REVIEW', 'QA_PASSED', 'PUBLISHED'];
const GATE_LABEL: Record<string, string> = {
  IN_REVIEW: 'In Review', QA_PASSED: 'QA Passed', PUBLISHED: 'Published',
};

type Brief = {
  brief_id: string; overall_risk: string | null; approval_status: string | null;
  approval_audit: Record<string, { status?: string; approved_by?: string }> | null;
  executive_snapshot: string | null; bottom_line: string | null;
  period_start: string | null; period_end: string | null; signal_ids: string[] | null;
};
type Signal = {
  event_id: string; raw_title: string; raw_summary: string | null;
  sector: string | null; geography: string | null;
  risk_rating: string | null; rank_score: number | null; source_tier: number | null;
  confidence_level: string | null; cluster_similarity: number | null; analysis_summary: string | null;
  canonical_url: string | null; published_at: string | null; collected_at: string | null;
  event_type: string | null; operational_relevance: number | null; customer_impact: string | null;
  banking_relevance: string | null; cps230_relevance: boolean | null; dependency_risk: boolean | null;
  confidence: number | null; score_breakdown: Record<string, unknown> | null;
};
type AuditEvent = {
  id: string; category: string | null; actor: string | null; action: string | null;
  outcome: string | null; details: Record<string, unknown> | null; created_at: string;
};

export default function BriefReview({ params }: { params: { id: string } }) {
  const id = params.id;
  const [brief, setBrief] = useState<Brief | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [auditTrail, setAuditTrail] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [openSignal, setOpenSignal] = useState<Signal | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/intelligence-workbench/brief?id=${id}`)
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(typeof d?.error === 'string' ? d.error : 'Failed to load');
        setBrief(d.brief); setSignals(d.signals ?? []); setAuditTrail(d.audit ?? []);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
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
    <WorkbenchShell wide title="Brief Review"
           tagline="USS TJR · Operational Resilience Intelligence · Phase B"
           back={{ href: '/intelligence-workbench', label: 'Overview' }}
           right={brief ? <RiskPill value={brief.overall_risk} /> : ''}>
      {loading ? (
        <p className="text-[13px] text-wb-ink2">Loading…</p>
      ) : error ? (
        <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>
      ) : !brief ? (
        <p className="text-[13px] text-wb-ink2">Brief not found.</p>
      ) : (
        <>
          <Card title={title}>
            {/* 2026-07-18: was brief.signal_ids.length, which can be empty/stale
                while the grid below legitimately finds linked events via the
                brief_id fallback query in route.ts — a real Captain saw "0
                signals" next to a populated 5-signal grid. Both counts now
                read the same signals array the grid renders, so they can't
                disagree. */}
            <p className="mb-2 text-[13px] text-wb-ink2">
              {brief.period_start} → {brief.period_end} · {signals.length} signals
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
                <button key={s.event_id} type="button" onClick={() => setOpenSignal(s)}
                  className="rounded-lg border border-wb-line p-3.5 text-left transition-colors hover:border-wb-sage-deep
                    focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
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
                </button>
              ))}
              {signals.length === 0 && <p className="text-[13px] text-wb-ink2">No linked signals.</p>}
            </div>
          </Card>

          {/* Screen 3 — approval gate. 2026-07-18: consolidated from three
              separate data_qa/factual_qa/analytical_qa rows + a "Mark QA
              Ready" step into one QA row + Publish, matching the 3-state
              workflow above. */}
          <Card title="Approval gate">
            <div className="flex items-center gap-3 border-b border-wb-line py-2.5 text-[13.5px] last:border-0">
              <span className={`grid h-5 w-5 place-items-center rounded text-[11px] text-white ${gatePassed('qa') ? 'bg-wb-ok' : 'bg-wb-line'}`}>
                {gatePassed('qa') ? '✓' : ''}
              </span>
              <span className="flex-1">QA</span>
              {audit?.qa?.approved_by && <span className="text-[11.5px] text-wb-ink2">{audit.qa.approved_by}</span>}
              {!gatePassed('qa') && (
                <button disabled={!!busy} onClick={() => act('brief.qa_pass', {}, 'QA pass')}
                  className="rounded-md border border-wb-sage px-2.5 py-1 text-[12px] text-wb-sage-deep hover:bg-wb-sage/10 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">
                  Pass
                </button>
              )}
            </div>
            <div className="mt-4 flex flex-wrap gap-2.5">
              <button disabled={!!busy} onClick={() => act('brief.publish', {}, 'Publish')}
                className="rounded-md border border-wb-sage-deep bg-wb-sage-deep px-3.5 py-2 text-[13px] text-white transition hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink">
                Publish
              </button>
              <button disabled={!!busy} onClick={() => act('brief.escalate', {}, 'Escalate to RED')}
                className="rounded-md border border-wb-crit-on bg-wb-crit-on px-3.5 py-2 text-[13px] text-white transition hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-crit-on">
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

          {/* Audit trail — fetched by the brief API since it was built, never
              rendered until now (WORKBENCH-REVIEW.md H11, 2026-07-18). Every
              QA gate/publish/escalate action on this brief, real provenance. */}
          {auditTrail.length > 0 && (
            <Card title="Audit trail">
              <div className="flex flex-col gap-2.5">
                {auditTrail.map((a) => (
                  <div key={a.id} className="flex items-start gap-3 border-b border-wb-line py-2 text-[12.5px] last:border-0">
                    <span className="w-[140px] shrink-0 text-wb-ink2">
                      {new Date(a.created_at).toLocaleString()}
                    </span>
                    <span className="flex-1">
                      <span className="font-medium">{a.actor ?? 'unknown'}</span>
                      {' — '}{a.action ?? a.category ?? 'event'}
                      {a.outcome && a.outcome !== 'success' && (
                        <span className="ml-1.5 text-wb-crit-on">({a.outcome})</span>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* 2026-07-18: signal cards were plain, non-interactive divs — no
              way to see raw_summary, canonical_url, or the OR classification
              fields (operational_relevance, cps230_relevance, etc.) that the
              API already returns but the card never rendered. Wired the
              existing (previously unused) Modal primitive as the detail view. */}
          <Modal open={!!openSignal} onClose={() => setOpenSignal(null)}
                 title={openSignal?.raw_title ?? 'Signal'} variant="preview">
            {openSignal && (
              <div className="flex flex-col gap-3 text-[13px]">
                <div className="flex flex-wrap items-center gap-2">
                  <RiskPill value={openSignal.risk_rating} />
                  <span className="font-serif text-[15px]">
                    {openSignal.rank_score != null ? Math.round(openSignal.rank_score) : '—'}/50
                  </span>
                  <span className="text-wb-ink2">
                    {openSignal.sector ?? '—'} · {openSignal.geography ?? '—'} · {openSignal.event_type ?? '—'}
                  </span>
                </div>

                {openSignal.raw_summary ? (
                  <p className="text-wb-ink">{openSignal.raw_summary}</p>
                ) : (
                  <p className="text-[12px] italic text-wb-ink2">
                    Source provides title only — no summary available.
                  </p>
                )}
                {openSignal.analysis_summary && (
                  <p className="rounded-md bg-wb-line/30 p-2.5 text-[12.5px] text-wb-ink2">
                    {openSignal.analysis_summary}
                  </p>
                )}

                <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px]">
                  <dt className="text-wb-ink2">Operational relevance</dt>
                  <dd>{openSignal.operational_relevance != null ? openSignal.operational_relevance : '—'}</dd>
                  <dt className="text-wb-ink2">Customer impact</dt>
                  <dd>{openSignal.customer_impact ?? '—'}</dd>
                  <dt className="text-wb-ink2">Banking relevance</dt>
                  <dd>{openSignal.banking_relevance ?? '—'}</dd>
                  <dt className="text-wb-ink2">CPS 230 relevant</dt>
                  <dd>{openSignal.cps230_relevance ? 'Yes' : 'No'}</dd>
                  <dt className="text-wb-ink2">Dependency risk</dt>
                  <dd>{openSignal.dependency_risk ? 'Yes' : 'No'}</dd>
                  <dt className="text-wb-ink2">Confidence</dt>
                  <dd>{openSignal.confidence != null ? openSignal.confidence : '—'}</dd>
                  <dt className="text-wb-ink2">Published</dt>
                  <dd>{openSignal.published_at ? new Date(openSignal.published_at).toLocaleString() : '—'}</dd>
                  <dt className="text-wb-ink2">Collected</dt>
                  <dd>{openSignal.collected_at ? new Date(openSignal.collected_at).toLocaleString() : '—'}</dd>
                </dl>

                {openSignal.score_breakdown && (
                  <pre className="overflow-x-auto rounded-md bg-wb-line/30 p-2.5 text-[11px] text-wb-ink2">
                    {JSON.stringify(openSignal.score_breakdown, null, 2)}
                  </pre>
                )}

                {openSignal.canonical_url && (
                  <a href={openSignal.canonical_url} target="_blank" rel="noopener noreferrer"
                     className="text-[12.5px] text-wb-sage-deep underline">
                    Open source →
                  </a>
                )}
              </div>
            )}
          </Modal>
        </>
      )}
    </WorkbenchShell>
  );
}
