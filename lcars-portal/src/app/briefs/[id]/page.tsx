'use client';

// Briefs canonical uplift, Section 19-20: /briefs/[id] is the canonical
// detail route for a stored intelligence brief — a read-only presentation
// of the immutable record ("what did HQ assess at that point in time").
// Legacy QA/Publish/Escalate actions stay on
// /intelligence-workbench/brief/[id] (see BRIEFS_CANONICAL_UPLIFT.md §3);
// this page never writes to the brief.

import { useCallback, useEffect, useState } from 'react';
import { Card, Modal, RiskPill, WorkbenchShell } from '@/components/ui';
import type { BriefDetail } from '@/lib/briefsShared';
import { buildMorningIntelligenceView } from '@/lib/briefsShared';

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

function fmt(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleString();
}

export default function BriefDetailPage({ params }: { params: { id: string } }) {
  const id = params.id;
  const [brief, setBrief] = useState<BriefDetail | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showEvidence, setShowEvidence] = useState(false);
  const [openSignal, setOpenSignal] = useState<Signal | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/briefs/${encodeURIComponent(id)}`)
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(typeof d?.error === 'string' ? d.error : 'Failed to load');
        setBrief(d.brief);
        setSignals(d.signals ?? []);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, [id]);
  useEffect(load, [load]);

  const view = buildMorningIntelligenceView(brief, 5);

  return (
    <WorkbenchShell
      title="Daily Intelligence Brief"
      eyebrow="Briefs · Canonical Record"
      tagline="USS TJR · HQ's canonical daily synthesis of the intelligence picture — an immutable historical record"
      back={{ href: '/briefs', label: 'Briefs' }}
      right={brief ? <RiskPill value={brief.overall_risk} /> : ''}
    >
      {loading ? (
        <p className="text-[13px] text-wb-ink2">Loading…</p>
      ) : error ? (
        <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>
      ) : !brief ? (
        <p className="text-[13px] text-wb-ink2">Brief not found.</p>
      ) : (
        <div className="space-y-4">
          <Card title={fmt(brief.published_at) !== '—' ? `Published ${fmt(brief.published_at)}` : `Generated ${fmt(brief.generated_at)}`}>
            <p className="mb-3 text-[13px] text-wb-ink2">
              Period {brief.period_start ?? '—'} → {brief.period_end ?? '—'}
              {brief.morning_cycle_id ? ` · Morning cycle ${brief.morning_cycle_id}` : ''}
            </p>
            <div className="flex items-center gap-2">
              <span className="text-[11px] uppercase tracking-wider text-wb-ink2">Intelligence posture</span>
              <RiskPill value={brief.overall_risk} />
            </div>
          </Card>

          {view.executiveRead && (
            <Card title="Executive Read">
              <p className="text-sm text-wb-ink">{view.executiveRead}</p>
            </Card>
          )}

          {view.whatMatters.length > 0 && (
            <Card title="What Matters">
              <ol className="space-y-3">
                {view.whatMatters.map((item, i) => (
                  <li key={`${item.title}-${i}`} className="flex gap-3 text-sm">
                    <span className="shrink-0 font-serif text-wb-ink2">{String(i + 1).padStart(2, '0')}</span>
                    <div>
                      <p className="font-medium text-wb-ink">{item.title}</p>
                      {item.soWhat && <p className="mt-0.5 text-[13px] text-wb-ink2">{item.soWhat}</p>}
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          )}

          {view.changed && (
            <Card title="What Changed Since Yesterday">
              <div className="space-y-2 text-sm">
                {view.changed.new.length > 0 && (
                  <p><span className="font-medium text-wb-ink">New — </span>{view.changed.new.join('; ')}</p>
                )}
                {view.changed.escalated.length > 0 && (
                  <p><span className="font-medium text-wb-crit-on">Escalated — </span>{view.changed.escalated.join('; ')}</p>
                )}
                {view.changed.improved.length > 0 && (
                  <p><span className="font-medium text-wb-ok">Improved — </span>{view.changed.improved.join('; ')}</p>
                )}
              </div>
            </Card>
          )}

          {brief.domain_picture && Object.keys(brief.domain_picture).length > 0 && (
            <Card title="Domain Picture">
              <div className="grid gap-3 sm:grid-cols-2">
                {Object.entries(brief.domain_picture).map(([key, bucket]) => (
                  <div key={key} className="rounded-lg border border-wb-line/60 p-3 text-sm">
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="font-medium text-wb-ink">{bucket.label}</span>
                      <RiskPill value={bucket.worst_risk} />
                    </div>
                    <ul className="space-y-1 text-[12.5px] text-wb-ink2">
                      {bucket.events.map((e, i) => (
                        <li key={i}>{e.title}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-[11px] text-wb-ink2">
                Reflects domains actually assessed in this brief&rsquo;s evidence base. Health OSINT and Emergency
                Alert Hub are separate systems not yet fused into this synthesis — see{' '}
                <a href="/agent-job-status-workbench" className="underline">Agent &amp; Job Status</a>.
              </p>
            </Card>
          )}

          {view.watch.length > 0 && (
            <Card title="Watch">
              <ul className="list-disc space-y-1 pl-5 text-sm text-wb-ink">
                {view.watch.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </Card>
          )}

          {Array.isArray(brief.known_unknowns) && brief.known_unknowns.length > 0 && (
            <Card title="Known Unknowns">
              <ul className="list-disc space-y-1 pl-5 text-sm text-wb-ink2">
                {brief.known_unknowns.map((k, i) => <li key={i}>{k}</li>)}
              </ul>
            </Card>
          )}

          <Card title="Collection Coverage">
            {brief.coverage ? (
              <div className="space-y-1.5 text-sm">
                <p>
                  {brief.coverage.completed ?? '—'}/{brief.coverage.expected ?? '—'} sources successful
                  {brief.coverage.failed ? ` · ${brief.coverage.failed} failed` : ''}
                </p>
                {view.coverageNote && (
                  <p className="text-wb-crit-on">⚠️ {view.coverageNote}</p>
                )}
                {brief.coverage.latest_included_at && (
                  <p className="text-[12px] text-wb-ink2">
                    Latest included intelligence: {fmt(brief.coverage.latest_included_at)}
                  </p>
                )}
                <a href="/agent-job-status-workbench" className="inline-block text-[12.5px] text-wb-sage-deep underline">
                  View system status →
                </a>
              </div>
            ) : (
              <p className="text-[13px] text-wb-ink2">
                Coverage detail is not available for this brief (generated before this feature shipped).
              </p>
            )}
          </Card>

          <Card title={`Sources / Evidence (${signals.length})`}>
            {!showEvidence ? (
              <button
                type="button"
                onClick={() => setShowEvidence(true)}
                className="rounded-md border border-wb-line px-3 py-1.5 text-[12.5px] text-wb-ink2 hover:bg-wb-bg"
              >
                Show {signals.length} linked signal{signals.length === 1 ? '' : 's'}
              </button>
            ) : signals.length === 0 ? (
              <p className="text-[13px] text-wb-ink2">No linked signals.</p>
            ) : (
              <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
                {signals.map((s) => (
                  <button
                    key={s.event_id}
                    type="button"
                    onClick={() => setOpenSignal(s)}
                    className="rounded-lg border border-wb-line p-3.5 text-left transition-colors hover:border-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                  >
                    <h4 className="mb-2 text-[13.5px] font-semibold leading-snug">{s.raw_title}</h4>
                    <p className="mb-2 text-[11.5px] text-wb-ink2">
                      {s.sector ?? '—'} · {s.geography ?? '—'} · {s.source_tier ? `Tier ${s.source_tier}` : '—'}
                    </p>
                    <RiskPill value={s.risk_rating} />
                  </button>
                ))}
              </div>
            )}
          </Card>

          <Modal open={!!openSignal} onClose={() => setOpenSignal(null)} title={openSignal?.raw_title ?? 'Signal'} variant="preview">
            {openSignal && (
              <div className="flex flex-col gap-3 text-[13px]">
                <div className="flex flex-wrap items-center gap-2">
                  <RiskPill value={openSignal.risk_rating} />
                  <span className="text-wb-ink2">
                    {openSignal.sector ?? '—'} · {openSignal.geography ?? '—'} · {openSignal.event_type ?? '—'}
                  </span>
                </div>
                {openSignal.raw_summary ? (
                  <p className="text-wb-ink">{openSignal.raw_summary}</p>
                ) : (
                  <p className="text-[12px] italic text-wb-ink2">Source provides title only — no summary available.</p>
                )}
                {openSignal.canonical_url && (
                  <a href={openSignal.canonical_url} target="_blank" rel="noopener noreferrer" className="text-[12.5px] text-wb-sage-deep underline">
                    Open source →
                  </a>
                )}
              </div>
            )}
          </Modal>
        </div>
      )}
    </WorkbenchShell>
  );
}
