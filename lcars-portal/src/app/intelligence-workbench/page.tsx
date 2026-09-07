'use client';

/**
 * Technical OSINT Workbench (Three-Workbench Simplification, Phase 1).
 *
 * Re-anchored from a 5-tab analyst console (Signal Confidence Matrix /
 * Intelligence Summary / Source Trust Network / Threat Assessment / Signal
 * Credibility) into a single-user intelligence briefing: Today / Watching /
 * Library — mirroring the Content Workbench uplift (MSN-0363, commit
 * f2ee2cb4)'s Today/Studio/Pipeline/Library pattern: one route, tabs via
 * DomainToggle + ?tab= URL-sync, no new AppShell/theme/nav.
 *
 * This is the first workbench to read and gate the UI on
 * intelligence_events.disposition (intelligence/classification/
 * disposition.py::technical_disposition(), migration 0186) instead of
 * treating it as shadow-mode: ESCALATE -> Needs you, BRIEF -> Worth
 * knowing, WATCH -> Watching, REFERENCE/older -> Library, SUPPRESS ->
 * hidden from every normal view (still queryable in Library via an
 * explicit filter — never hard-deleted). See today/watching/library
 * route.ts files for the real query logic and the documented backfill gap
 * (disposition is NULL on ~80% of pre-migration-0186 rows; verified live
 * that the last 7 days are fully populated, so Today/Watching are
 * unaffected — Library is where NULL disposition surfaces, labelled
 * "Unclassified" rather than hidden).
 *
 * The original 5-tab analyst console is demoted, not deleted: every API
 * route (confidence-matrix/intelligence-summary/source-network/
 * threat-assessment/credibility) and its rendering logic below is
 * unchanged, just reachable via a secondary "Technical view" toggle
 * instead of being the primary nav. brief/[id] and escalation/[id] are
 * untouched and still linked from Credibility's technical view and now
 * also from Library's evidence links.
 */

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Card, WorkbenchShell, DomainToggle, Button } from '@/components/ui';
import { stateToneClasses } from '@/lib/departments';
import type { StateTone } from '@/lib/types';
import { TodayView } from './_components/TodayView';
import { WatchingView } from './_components/WatchingView';
import { LibraryView } from './_components/LibraryView';

type Tab = 'today' | 'watching' | 'library';
type AnalystDomain = 'confidence-matrix' | 'intelligence-summary' | 'source-network' | 'threat-assessment' | 'credibility';

type Payload = { domain: AnalystDomain; [key: string]: any };

const TAB_OPTIONS: { key: Tab; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: 'watching', label: 'Watching' },
  { key: 'library', label: 'Library' },
];

const ANALYST_DOMAIN_OPTIONS: { key: AnalystDomain; label: string }[] = [
  { key: 'confidence-matrix', label: 'Signal Confidence Matrix' },
  { key: 'intelligence-summary', label: 'Intelligence Summary' },
  { key: 'source-network', label: 'Source Trust Network' },
  { key: 'threat-assessment', label: 'Threat Assessment' },
  { key: 'credibility', label: 'Signal Credibility' },
];

function isTab(v: string | null): v is Tab {
  return v === 'today' || v === 'watching' || v === 'library';
}

function isAnalystDomain(v: string | null): v is AnalystDomain {
  return ANALYST_DOMAIN_OPTIONS.some((o) => o.key === v);
}

/** Card title with a semantic state dot in place of a functional emoji glyph.
 * Card's `title` prop only accepts a plain string, so this renders as a
 * first child inside the Card body, matching Card's own title styling. */
function CardTitleWithDot({ tone, label }: { tone: StateTone; label: string }) {
  return (
    <h2 className="mb-3 flex items-center gap-2 border-b border-wb-line pb-3 font-serif text-lg text-wb-ink">
      <span className={`inline-block h-2 w-2 rounded-full ${stateToneClasses(tone).dot}`} aria-hidden />
      {label}
    </h2>
  );
}

/**
 * The original 5-tab analyst console, unchanged from before this uplift
 * except for being reached via a "Technical view" toggle instead of being
 * the workbench's primary navigation. All 5 API routes are untouched.
 */
function AnalystConsole({ onClose }: { onClose: () => void }) {
  const [domain, setDomain] = useState<AnalystDomain>('intelligence-summary');
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((withSpinner: boolean) => {
    if (withSpinner) setLoading(true);
    const endpoints: Record<AnalystDomain, string> = {
      'confidence-matrix': '/api/intelligence-workbench/confidence-matrix',
      'intelligence-summary': '/api/intelligence-workbench/intelligence-summary',
      'source-network': '/api/intelligence-workbench/source-network',
      'threat-assessment': '/api/intelligence-workbench/threat-assessment',
      'credibility': '/api/intelligence-workbench/credibility',
    };
    return fetch(endpoints[domain])
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed');
        setError(null);
        setData(d);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Failed');
        setData({ domain } as Payload);
      })
      .finally(() => { if (withSpinner) setLoading(false); });
  }, [domain]);

  useEffect(() => { load(true); }, [load]);

  const renderSignal = (s: any) => (
    <div key={s.event_id} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
      {s.canonical_url ? (
        <a href={s.canonical_url} target="_blank" rel="noopener noreferrer" className="font-semibold text-wb-ink underline decoration-dotted hover:text-wb-sage-deep">
          {s.raw_title}
        </a>
      ) : (
        <div className="font-semibold text-wb-ink">{s.raw_title}</div>
      )}
      <div>
        {s.source_name}
        {typeof s.rank_score === 'number' && <> • Score: {s.rank_score.toFixed(1)}</>}
        {s.risk_rating && <> • Risk: {s.risk_rating}</>}
        {s.sector && <> • {s.sector.replace(/_/g, ' ')}</>}
        {s.published_at && <> • {new Date(s.published_at).toLocaleDateString()}</>}
      </div>
      {s.summary && <div className="mt-1 text-wb-ink2">{s.summary}{s.summary.length >= 220 ? '…' : ''}</div>}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[12px] text-wb-ink2">Technical view — full analyst console (Signal Confidence, Source Trust, Threat Assessment).</p>
        <Button size="sm" variant="secondary" onClick={onClose}>← Back to briefing</Button>
      </div>
      <DomainToggle value={domain} onChange={setDomain} options={ANALYST_DOMAIN_OPTIONS} ariaLabel="OSINT analyst view" />

      {loading && !data && <div className="py-16 text-center text-[13px] text-wb-ink2">Loading Technical OSINT…</div>}
      {error && <p className="mb-4 rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">Error: {error}</p>}

      {domain === 'confidence-matrix' && data && (
        <div className="space-y-6">
          <Card title="Signal Distribution by Category & Confidence">
            <div className="grid grid-cols-1 gap-4 text-[12px] text-wb-ink2 sm:grid-cols-2">
              {Object.entries(data.matrix || {}).map(([cat, conf]: any) => (
                <div key={cat}>
                  <div className="font-semibold text-wb-ink mb-1">{cat}</div>
                  <div>HIGH: {conf.high}</div>
                  <div>MEDIUM: {conf.medium}</div>
                  <div>LOW: {conf.low}</div>
                </div>
              ))}
            </div>
          </Card>
          <Card title="Coverage Assessment">
            <p className="text-[12px] text-wb-ink2">Total signals: {data.signals?.length || 0}</p>
          </Card>
        </div>
      )}

      {domain === 'intelligence-summary' && data && (
        <div className="space-y-4">
          {data.high?.length > 0 && (
            <Card>
              <CardTitleWithDot tone="ok" label="HIGH CONFIDENCE" />
              <div className="space-y-2">{data.high.slice(0, 15).map(renderSignal)}</div>
            </Card>
          )}
          {data.medium?.length > 0 && (
            <Card>
              <CardTitleWithDot tone="warn" label="MEDIUM CONFIDENCE" />
              <div className="space-y-2">{data.medium.slice(0, 15).map(renderSignal)}</div>
            </Card>
          )}
          {data.low?.length > 0 && (
            <Card>
              <CardTitleWithDot tone="crit" label="LOW CONFIDENCE" />
              <div className="space-y-2">{data.low.slice(0, 8).map(renderSignal)}</div>
            </Card>
          )}
          {data.unknowns?.length > 0 && (
            <Card>
              <CardTitleWithDot tone="unknown" label="KNOWN UNKNOWNS" />
              <div className="space-y-2">
                {data.unknowns.map((u: any) => (
                  <div key={u.title} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
                    <div className="font-semibold text-wb-ink">{u.title}</div>
                    <div>{u.impact}</div>
                    {u.need && <div className="italic">Need: {u.need}</div>}
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {domain === 'source-network' && data && (
        <div className="space-y-6">
          <Card title="Cross-Source Corroboration">
            <div className="text-[12px] text-wb-ink2 space-y-1">
              {Object.entries(data.correlations || {})
                .sort((a: any, b: any) => b[1].signal_count - a[1].signal_count)
                .slice(0, 8)
                .map(([sourceName, info]: any) => (
                  <div key={sourceName}>
                    {sourceName} • {info.signal_count} signals • {info.corroboration_count} corroborated • avg confirmation {info.avg_confirmation_per_signal}
                  </div>
                ))}
            </div>
          </Card>
          <Card title="Source Trending (30-day)">
            <div className="text-[12px] text-wb-ink2 space-y-1">
              {data.trending?.map((t: any) => (
                <div key={t.source}>
                  {t.source} {t.direction === 'up' ? '↗' : t.direction === 'down' ? '↘' : t.direction === 'stable' ? '→' : '—'} {t.from ?? '?'} → {t.to ?? '?'}
                </div>
              ))}
            </div>
            {data.note && <p className="mt-2 text-[11px] italic text-wb-ink2">{data.note}</p>}
          </Card>
        </div>
      )}

      {domain === 'threat-assessment' && data && (
        <div className="space-y-6">
          <Card title="Escalation Matrix">
            <div className="space-y-2">
              {data.threats?.slice(0, 5).map((t: any) => (
                <div key={t.threat} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
                  <div className="font-semibold text-wb-ink">{t.threat}</div>
                  <div>{t.probability}/{t.impact}/{t.confidence} → {t.escalation.toUpperCase()}</div>
                  <div className="italic">{t.recommendation}</div>
                </div>
              ))}
              {!data.threats?.length && <p>No signals above rank_score 70 in this window.</p>}
            </div>
          </Card>
          {data.gaps?.length > 0 && (
            <Card title="Coverage Gaps">
              <div className="text-[12px] text-wb-ink2 space-y-1">
                {data.gaps.map((g: any) => (
                  <div key={g.area}>{g.area}: {g.risk} — {g.blind_spot}</div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {domain === 'credibility' && data && (
        <div className="space-y-6">
          <Card title="Latest Published Brief">
            {data.brief?.brief_id ? (
              <div className="text-[12px] text-wb-ink2 space-y-1">
                <div>Overall risk: <span className="font-semibold text-wb-ink">{data.brief.overall_risk ?? 'unknown'}</span></div>
                <div>Generated: {data.brief.generated_at ? new Date(data.brief.generated_at).toLocaleString() : '—'}</div>
                {data.brief.executive_snapshot && <div className="mt-2 italic">{data.brief.executive_snapshot}</div>}
                <div className="mt-2 flex gap-3">
                  <Link href={`/intelligence-workbench/brief/${data.brief.brief_id}`} className="text-wb-sage-deep hover:underline">
                    View full brief →
                  </Link>
                  <Link href={`/intelligence-workbench/escalation/${data.brief.brief_id}`} className="text-wb-sage-deep hover:underline">
                    Escalation workflow →
                  </Link>
                </div>
              </div>
            ) : (
              <p className="text-[12px] text-wb-ink2">No published brief in this window.</p>
            )}
          </Card>
          <Card title="Brief Composition by Source Tier">
            <div className="text-[12px] text-wb-ink2 space-y-1">
              <div>TIER_1: {data.brief?.tier_counts?.TIER_1 ?? 0} ({data.brief?.composition?.tier1_pct ?? 0}%)</div>
              <div>TIER_2: {data.brief?.tier_counts?.TIER_2 ?? 0} ({data.brief?.composition?.tier2_pct ?? 0}%)</div>
              <div>TIER_3: {data.brief?.tier_counts?.TIER_3 ?? 0} ({data.brief?.composition?.tier3_pct ?? 0}%)</div>
              <div>TIER_4: {data.brief?.tier_counts?.TIER_4 ?? 0} ({data.brief?.composition?.tier4_pct ?? 0}%)</div>
              <div className="mt-1 font-semibold text-wb-ink">Total signals: {data.brief?.total_signals ?? 0}</div>
            </div>
          </Card>
          <Card title="High-Confidence Signals">
            <div className="space-y-2">
              {data.signals?.slice(0, 10).map((s: any) => (
                <div key={s.event_id} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
                  <div className="font-semibold text-wb-ink">{s.raw_title}</div>
                  <div>{s.source.source_name} ({s.source.tier}, srs={s.source.srs}) • {s.confidence_level} confidence • {s.corroboration} corroborating • Score: {s.rank_score?.toFixed?.(1) ?? s.rank_score}</div>
                </div>
              ))}
              {!data.signals?.length && <p>No signals ≥60% confidence in this window.</p>}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get('tab');
  const [tab, setTabState] = useState<Tab>(isTab(initial) ? initial : 'today');
  const [showAnalyst, setShowAnalyst] = useState(isAnalystDomain(params.get('view')));

  const setTab = (t: Tab) => {
    setTabState(t);
    setShowAnalyst(false);
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('tab', t);
    sp.delete('view');
    router.replace(`/intelligence-workbench?${sp.toString()}`, { scroll: false });
  };

  const openAnalyst = () => {
    setShowAnalyst(true);
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('view', 'technical');
    router.replace(`/intelligence-workbench?${sp.toString()}`, { scroll: false });
  };

  const closeAnalyst = () => {
    setShowAnalyst(false);
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.delete('view');
    router.replace(`/intelligence-workbench?${sp.toString()}`, { scroll: false });
  };

  return (
    <WorkbenchShell
      title="Technical OSINT Workbench"
      eyebrow="Cyber & Infrastructure Intelligence"
      tagline="USS TJR · Your daily technical intelligence briefing"
      tabs={!showAnalyst ? <DomainToggle value={tab} onChange={setTab} options={TAB_OPTIONS} ariaLabel="Technical OSINT sections" /> : undefined}
      back={{ href: '/workbenches', label: 'Workbenches' }}
      wide
    >
      {showAnalyst ? (
        <AnalystConsole onClose={closeAnalyst} />
      ) : (
        <>
          {tab === 'today' && (
            <TodayView onOpenWatching={() => setTab('watching')} onOpenTechnical={openAnalyst} />
          )}
          {tab === 'watching' && <WatchingView />}
          {tab === 'library' && (
            <div className="space-y-3">
              <LibraryView />
              <button
                type="button"
                onClick={openAnalyst}
                className="text-[12px] text-wb-ink2 underline decoration-dotted hover:text-wb-sage-deep"
              >
                Technical view (analyst console) →
              </button>
            </div>
          )}
        </>
      )}
    </WorkbenchShell>
  );
}

export default function OSINTWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
