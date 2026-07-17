'use client';

// Phase B — Intelligence Workbench · Screen 1 (Overview). Domain-toggled view.
// Supports both Operational Signals (Phase A) and Health Intelligence modes.
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Card, RiskPill, Shell } from './_components/Shell';
import { commitHealthInsight, discardHealthInsight } from './_components/health-memory';
import { ClassifierValidationCard, AuditLogCard, PillarMappingsCard } from './_components/health-classifier-dashboard';
import { useRealtimeRefresh } from '@/lib/realtime/useRealtimeRefresh';

type Domain = 'operational' | 'health';

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

type SourceArticle = {
  title: string;
  url: string;
  summary?: string;
  published_date?: string;
  source_type?: string;
};

type HealthInsight = {
  insight_id: string;
  created_at: string;
  overall_status: string | null;
  wellness_narrative: string | null;
  key_findings: string | null;
  source_articles?: SourceArticle[] | null;
  committed_to_memory?: boolean;
  committed_at?: string | null;
};

type HealthEvent = {
  event_id: string;
  logged_at: string;
  event_type: string;
  value: number | string | null;
  notes: string | null;
  source: string | null;
};

type OperationalPayload = {
  domain: 'operational';
  kpis: { signals_7d?: number; briefs_pending?: number; red_active?: number };
  briefs: Brief[];
  hotSignals: Signal[];
};

type HealthPayload = {
  domain: 'health';
  kpis: {
    capacity_score?: number;
    sleep_hours?: number;
    pain_level?: number;
  };
  insights: HealthInsight[];
  recentEvents: HealthEvent[];
  dailyMetrics: any[];
};

type Payload = OperationalPayload | HealthPayload;

function DomainToggle({ domain, onChange }: { domain: Domain; onChange: (d: Domain) => void }) {
  return (
    <div className="flex gap-1 rounded-md border border-wb-line bg-wb-surface px-1.5 py-1">
      <button
        onClick={() => onChange('operational')}
        className={`rounded px-3 py-1.5 text-[13px] font-medium transition ${
          domain === 'operational'
            ? 'bg-wb-sage-deep text-white'
            : 'text-wb-ink2 hover:bg-wb-line'
        }`}
      >
        Operational Signals
      </button>
      <button
        onClick={() => onChange('health')}
        className={`rounded px-3 py-1.5 text-[13px] font-medium transition ${
          domain === 'health'
            ? 'bg-wb-sage-deep text-white'
            : 'text-wb-ink2 hover:bg-wb-line'
        }`}
      >
        Health Intelligence
      </button>
    </div>
  );
}

function SourceArticleCard({ article }: { article: SourceArticle }) {
  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block rounded-md border border-wb-line bg-wb-line/30 p-3 transition hover:border-wb-sage-deep hover:bg-wb-line/60"
    >
      <div className="font-medium text-wb-ink">{article.title}</div>
      {article.summary && (
        <p className="mt-1 text-[12px] text-wb-ink2 line-clamp-2">{article.summary}</p>
      )}
      <div className="mt-2 flex items-center gap-2 text-[11px] text-wb-ink2">
        {article.source_type && (
          <span className="rounded bg-wb-sage-deep/20 px-1.5 py-0.5 text-wb-sage-deep">
            {article.source_type}
          </span>
        )}
        {article.published_date && <span>{new Date(article.published_date).toLocaleDateString()}</span>}
      </div>
    </a>
  );
}

export default function Overview() {
  const [domain, setDomain] = useState<Domain>('operational');
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [live, setLive] = useState(false);

  const load = useCallback((withSpinner: boolean) => {
    if (withSpinner) setLoading(true);
    return fetch(`/api/intelligence-workbench?domain=${domain}`)
      .then(async (r) => {
        const d = await r.json();
        // A read failure must be visibly distinct from "no signals" - this
        // tool exists to monitor operational resilience, so a silently-
        // empty result is the one failure mode it can't afford
        // (WORKBENCH-REVIEW.md H4, 2026-07-18). Data is still populated
        // with an empty-but-valid shape below so the rest of the page
        // doesn't crash - the error banner is what tells the real story.
        if (!r.ok) throw new Error(typeof d?.error === 'string' ? d.error : 'Failed to load');
        setError(null);
        setData(d);
        setLastUpdated(new Date());
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Failed to load');
        setData({
          domain,
          kpis: {},
          ...(domain === 'operational' ? { briefs: [], hotSignals: [] } : { insights: [], recentEvents: [], dailyMetrics: [] })
        } as Payload);
      })
      .finally(() => { if (withSpinner) setLoading(false); });
  }, [domain]);

  useEffect(() => {
    load(true);
  }, [load]);

  // Live UI reflection: intelligence_events is populated by ORI ingestion
  // (currently a daily GitHub Actions cron) - this doesn't make ingestion
  // any faster, it just means a row that already landed shows up here the
  // moment it does, instead of waiting for the next page load/domain switch.
  useRealtimeRefresh({
    table: 'intelligence_events',
    events: ['INSERT'],
    enabled: domain === 'operational',
    onChange: () => load(false),
    onStatusChange: (status) => setLive(status === 'SUBSCRIBED'),
  });

  const handleCommitInsight = async (insightId: string) => {
    setActionInProgress(insightId);
    const result = await commitHealthInsight(insightId);
    if (result.status === '200') await load(false);
    setActionInProgress(null);
  };

  const handleDiscardInsight = async (insightId: string) => {
    setActionInProgress(insightId);
    const result = await discardHealthInsight(insightId);
    if (result.status === '200') await load(false);
    setActionInProgress(null);
  };

  const briefTitle = (b: Brief) =>
    (b.executive_snapshot ?? '').split('.')[0]?.slice(0, 80) || `Brief ${b.brief_id.slice(0, 8)}`;

  const operationalData = data as OperationalPayload | null;
  const healthData = data as HealthPayload | null;

  const eyebrow = domain === 'operational' ? 'Operational Resilience' : 'Health Intelligence';

  return (
    <Shell 
      title="Intelligence Workbench" 
      eyebrow={eyebrow}
      right={<DomainToggle domain={domain} onChange={setDomain} />}
    >
      {error && (
        <p className="mb-4 rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">
          Could not refresh: {error}. Showing last known data, not current.
        </p>
      )}
      {domain === 'operational' && operationalData ? (
        <>
          {/* Operational mode KPIs */}
          <div className="mb-8 grid grid-cols-2 gap-3.5 sm:grid-cols-4">
            {[
              { n: operationalData.kpis.signals_7d ?? 0, l: 'Signals collected (7d)', red: false },
              { n: operationalData.kpis.briefs_pending ?? 0, l: 'Briefs pending approval', red: false },
              { n: operationalData.kpis.red_active ?? 0, l: 'RED incidents active', red: true },
            ].map((c) => (
              <div key={c.l} className="rounded-lg border border-wb-line bg-wb-surface p-4 shadow-sm">
                <div className={`font-serif text-3xl ${c.red && c.n > 0 ? 'text-wb-crit' : ''}`}>{c.n}</div>
                <div className="text-[12px] text-wb-ink2">{c.l}</div>
              </div>
            ))}
            <div className="rounded-lg border border-wb-line bg-wb-surface p-4 shadow-sm">
              <div className="flex items-center gap-2 font-serif text-3xl text-wb-sage-deep">
                {live && <span className="h-2 w-2 rounded-full bg-wb-sage-deep animate-pulse" aria-hidden />}
                {live ? 'Live' : 'Connecting…'}
              </div>
              <div className="text-[12px] text-wb-ink2">
                {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : 'Pipeline status'}
              </div>
            </div>
          </div>

          {/* Operational briefs */}
          <Card title="Briefs — gate status">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (operationalData.briefs.length ?? 0) === 0 ? (
              <p className="text-[13px] text-wb-ink2">No pending briefs.</p>
            ) : (
              operationalData.briefs.map((b) => (
                <div key={b.brief_id} className="flex items-center gap-3 border-b border-wb-line py-2.5 text-sm last:border-0">
                  <RiskPill value={b.overall_risk} />
                  <span className="flex-1">{briefTitle(b)}</span>
                  <span className="text-[12px] text-wb-ink2">{b.approval_status ?? 'IN_REVIEW'}</span>
                  <Link
                    href={`/intelligence-workbench/brief/${b.brief_id}`}
                    className="rounded-md border border-wb-sage-deep bg-wb-sage-deep px-3 py-1.5 text-[13px] text-white transition hover:-translate-y-px focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-ink"
                  >
                    Review Brief →
                  </Link>
                </div>
              ))
            )}
          </Card>

          {/* Operational hot incidents */}
          <Card title="Hot incidents — by operational relevance">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (operationalData.hotSignals.length ?? 0) === 0 ? (
              <p className="text-[13px] text-wb-ink2">No signals in the last 7 days.</p>
            ) : (
              operationalData.hotSignals.map((s) => (
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
        </>
      ) : (
        <>
          {/* Health mode KPIs */}
          <div className="mb-8 grid grid-cols-2 gap-3.5 sm:grid-cols-3">
            {[
              { n: Math.round(healthData?.kpis.capacity_score ?? 0), l: 'Capacity score', unit: '' },
              { n: (healthData?.kpis.sleep_hours ?? 0).toFixed(1), l: 'Sleep quality (7d avg)', unit: 'h' },
              { n: Math.round(healthData?.kpis.pain_level ?? 0), l: 'Pain level', unit: '/10' },
            ].map((c) => (
              <div key={c.l} className="rounded-lg border border-wb-line bg-wb-surface p-4 shadow-sm">
                <div className="font-serif text-3xl text-wb-ink">{c.n}{c.unit}</div>
                <div className="text-[12px] text-wb-ink2">{c.l}</div>
              </div>
            ))}
          </div>

          {/* Health insights with source articles */}
          <Card title="Weekly synthesis & source articles">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (healthData?.insights?.length ?? 0) === 0 ? (
              <p className="text-[13px] text-wb-ink2">No synthesis available.</p>
            ) : (
              healthData!.insights.map((i) => (
                <div key={i.insight_id} className="mb-6 rounded-md border border-wb-line p-4 last:mb-0">
                  {/* Insight header with status and actions */}
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="text-[13px] font-medium text-wb-ink">{i.overall_status ?? 'OK'}</div>
                      <p className="mt-2 text-[13px] text-wb-ink">{i.wellness_narrative ?? 'No narrative available.'}</p>
                      {i.key_findings && (
                        <p className="mt-2 text-[12px] text-wb-ink2">
                          <span className="font-semibold">Key findings:</span> {i.key_findings}
                        </p>
                      )}
                    </div>
                    {/* Commit/Discard buttons */}
                    <div className="ml-4 flex gap-2">
                      <button
                        onClick={() => handleCommitInsight(i.insight_id)}
                        disabled={actionInProgress === i.insight_id || i.committed_to_memory}
                        className={`rounded px-2 py-1.5 text-[11px] font-medium transition ${
                          i.committed_to_memory
                            ? 'bg-wb-ok/20 text-wb-ok-on cursor-default'
                            : 'border border-wb-sage-deep bg-wb-sage-deep text-white hover:-translate-y-px disabled:opacity-50'
                        }`}
                      >
                        {i.committed_to_memory ? '✓ Committed' : 'Commit'}
                      </button>
                      <button
                        onClick={() => handleDiscardInsight(i.insight_id)}
                        disabled={actionInProgress === i.insight_id || i.committed_to_memory}
                        className={`rounded px-2 py-1.5 text-[11px] font-medium transition ${
                          i.committed_to_memory
                            ? 'text-wb-ink2 cursor-default opacity-50'
                            : 'border border-wb-line text-wb-ink2 hover:bg-wb-line disabled:opacity-50'
                        }`}
                      >
                        Discard
                      </button>
                    </div>
                  </div>

                  {/* Source articles section */}
                  {i.source_articles && Array.isArray(i.source_articles) && i.source_articles.length > 0 && (
                    <div className="mt-4 border-t border-wb-line pt-4">
                      <div className="text-[12px] font-semibold text-wb-ink2 mb-3">Source Articles ({i.source_articles.length})</div>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {i.source_articles.map((article, idx) => (
                          <SourceArticleCard key={idx} article={article} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
          </Card>

          {/* Health recent events */}
          <Card title="Recent health events">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (healthData?.recentEvents?.length ?? 0) === 0 ? (
              <p className="text-[13px] text-wb-ink2">No events logged.</p>
            ) : (
              healthData!.recentEvents.map((e) => (
                <div key={e.event_id} className="flex items-start gap-3 border-b border-wb-line py-2.5 text-sm last:border-0">
                  <span className="rounded bg-wb-line px-2 py-0.5 text-[11px] text-wb-ink2">{e.event_type}</span>
                  <div className="flex-1">
                    <div className="font-medium text-wb-ink">{e.value ?? '—'}</div>
                    {e.notes && <div className="text-[12px] text-wb-ink2">{e.notes}</div>}
                  </div>
                  <span className="text-[11px] text-wb-ink2">{e.source ?? '—'}</span>
                </div>
              ))
            )}
          </Card>

          {/* Phase 1C — Classifier Dashboard */}
          <div className="grid gap-3.5 lg:grid-cols-2">
            <ClassifierValidationCard />
            <PillarMappingsCard />
          </div>

          <AuditLogCard />
        </>
      )}
    </Shell>
  );
}
