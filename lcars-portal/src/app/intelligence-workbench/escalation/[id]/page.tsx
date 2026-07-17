'use client';

// Phase B — Screens 4/5/6: RED Escalation + Stand-Down + Telegram deep-link target.
import { useCallback, useEffect, useState } from 'react';
import { Card, RiskPill, Shell } from '../../_components/Shell';
import { runAction } from '../../_components/actions';

const DIM_LABEL: Record<string, string> = {
  criticality: 'Criticality', scale: 'Scale', duration: 'Duration', customer_harm: 'Customer harm',
  systemic_relevance: 'Systemic relevance', dependency_risk: 'Dependency risk',
  regulatory_relevance: 'Regulatory relevance', learning_value: 'Learning value',
  australian_relevance: 'Australian relevance', forward_significance: 'Forward significance',
};

type Brief = {
  brief_id: string; overall_risk: string | null; executive_snapshot: string | null;
  bottom_line: string | null; signal_ids: string[] | null;
};
type Signal = {
  event_id: string; raw_title: string; risk_rating: string | null; rank_score: number | null;
  score_breakdown: Record<string, number> | null;
};
type AuditEvent = {
  id: string; category: string | null; actor: string | null; action: string | null;
  outcome: string | null; details: Record<string, unknown> | null; created_at: string;
};

export default function Escalation({ params }: { params: { id: string } }) {
  const id = params.id;
  const [brief, setBrief] = useState<Brief | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [auditTrail, setAuditTrail] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [fromTelegram, setFromTelegram] = useState(false);
  const [lesson, setLesson] = useState('');

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
  useEffect(() => {
    setFromTelegram(new URLSearchParams(window.location.search).get('alert_source') === 'telegram');
  }, []);

  const act = async (action: string, payload: Record<string, unknown>, label: string) => {
    setBusy(label); setMsg(null);
    const { status, body } = await runAction(action, { brief_id: id, ...payload });
    setBusy(null);
    const b = body as { error?: string; result?: { sent?: boolean } };
    setMsg(status === 200
      ? `✓ ${label}${b.result?.sent === false ? ' (queued — telegram not configured)' : ' succeeded'}`
      : `✗ ${label}: ${b.error ?? status}`);
    load();
  };

  const top = signals.slice().sort((a, b) => (b.rank_score ?? 0) - (a.rank_score ?? 0))[0];
  const dims = top?.score_breakdown ?? null;

  return (
    <Shell title="RED Escalation" eyebrow="Crisis mode"
           back={{ href: `/intelligence-workbench/brief/${id}`, label: 'Brief' }}>
      {fromTelegram && (
        <p className="mb-4 rounded border-l-[3px] border-wb-sage bg-wb-sage/10 px-3 py-2 text-[12px] text-wb-ink2">
          Opened from a Telegram alert · incident {id.slice(0, 8)}
        </p>
      )}
      {loading ? (
        <p className="text-[13px] text-wb-ink2">Loading…</p>
      ) : error ? (
        <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>
      ) : !brief ? (
        <p className="text-[13px] text-wb-ink2">Brief not found.</p>
      ) : (
        <>
          <div className="mb-6 flex items-center gap-3.5 rounded-lg bg-gradient-to-r from-wb-crit-on to-wb-crit-deep px-5 py-4 text-white">
            <span className="h-3 w-3 animate-pulse rounded-full bg-white" aria-hidden />
            <div>
              <div className="font-serif text-[20px]" role="status" aria-live="assertive">
                🔴 {brief.overall_risk === 'RED' ? 'CRITICAL INCIDENT' : `Status: ${brief.overall_risk ?? 'UNKNOWN'}`}
              </div>
              <div className="text-[13px] opacity-90">{(brief.executive_snapshot ?? '').slice(0, 100) || 'Operational resilience incident'}</div>
            </div>
          </div>

          {dims && (
            <Card title={`10-dimension risk breakdown — ${top?.rank_score ?? '?'}/50 ${top?.risk_rating ?? ''}`}>
              <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
                {Object.keys(DIM_LABEL).map((k) => (
                  <div key={k} className="flex items-center gap-2 text-[12.5px]">
                    <span className="w-[130px]">{DIM_LABEL[k]}</span>
                    <span className="h-1.5 flex-1 overflow-hidden rounded bg-wb-line">
                      <span className="block h-full bg-wb-sage" style={{ width: `${((dims[k] ?? 0) / 5) * 100}%` }} />
                    </span>
                    <span className="w-6 text-right text-wb-ink2">{dims[k] ?? '—'}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card title="Immediate actions">
            <div className="flex flex-wrap gap-2.5">
              <button disabled={!!busy} onClick={() => act('brief.notify_telegram', {}, 'Send Telegram alert')}
                className="rounded-md border border-wb-sage-deep bg-wb-sage-deep px-3.5 py-2 text-[13px] text-white transition hover:-translate-y-px disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink">
                📱 Send Telegram Alert
              </button>
              <button disabled={!!busy} onClick={() => act('brief.escalate', {}, 'Escalate to Captain')}
                className="rounded-md border border-wb-warn-on bg-wb-warn-on px-3.5 py-2 text-[13px] text-white transition hover:-translate-y-px disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-warn-on">
                🚀 Escalate to Captain
              </button>
            </div>
            {busy && <p className="mt-3 text-[12px] text-wb-ink2" aria-live="polite">Working: {busy}…</p>}
            {msg && <p className="mt-3 text-[12px]" aria-live="polite">{msg}</p>}
          </Card>

          {/* Screen 5 — stand-down */}
          <Card title="Stand-down">
            <label htmlFor="lesson" className="mb-1 block text-[12.5px] text-wb-ink2">Lesson (optional — what should improve?)</label>
            <textarea id="lesson" rows={2} value={lesson} onChange={(e) => setLesson(e.target.value)}
              placeholder="e.g. add carrier-dependency forward-watch to telecom briefs"
              className="w-full rounded-md border border-wb-line p-2.5 text-[13px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep" />
            <button disabled={!!busy}
              onClick={() => act('brief.stand_down', lesson ? { lesson_text: lesson, category: 'methodology_change' } : {}, 'Stand-down')}
              className="mt-3 rounded-md border border-wb-ink bg-wb-ink px-3.5 py-2 text-[13px] text-white transition hover:-translate-y-px disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink">
              Record lesson &amp; close
            </button>
          </Card>

          {/* Audit trail — fetched by the brief API since it was built, never
              rendered until now (WORKBENCH-REVIEW.md H11, 2026-07-18). */}
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
        </>
      )}
    </Shell>
  );
}
