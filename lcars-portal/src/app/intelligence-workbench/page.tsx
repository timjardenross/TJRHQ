'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Card, WorkbenchShell, DomainToggle } from '@/components/ui';
import { stateToneClasses } from '@/lib/departments';
import type { StateTone } from '@/lib/types';

type Domain = 'confidence-matrix' | 'intelligence-summary' | 'source-network' | 'threat-assessment' | 'credibility';

type Payload = { domain: Domain; [key: string]: any };

const DOMAIN_OPTIONS: { key: Domain; label: string }[] = [
  { key: 'confidence-matrix', label: 'Signal Confidence Matrix' },
  { key: 'intelligence-summary', label: 'Intelligence Summary' },
  { key: 'source-network', label: 'Source Trust Network' },
  { key: 'threat-assessment', label: 'Threat Assessment' },
  { key: 'credibility', label: 'Signal Credibility' },
];

function isDomain(v: string | null): v is Domain {
  return DOMAIN_OPTIONS.some((o) => o.key === v);
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

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get('domain');
  // Land on Intelligence Summary by default (Captain's directive,
  // 2026-08-22) — was Confidence Matrix.
  const [domain, setDomainState] = useState<Domain>(isDomain(initial) ? initial : 'intelligence-summary');
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((withSpinner: boolean) => {
    if (withSpinner) setLoading(true);
    const endpoints: Record<Domain, string> = {
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

  const setDomain = (d: Domain) => {
    setDomainState(d);
    // Keep the URL shareable/bookmarkable without a full navigation —
    // matches human-systems-workbench's pattern. Previously a refresh
    // on a non-default tab silently dropped back to Confidence Matrix.
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('domain', d);
    router.replace(`/intelligence-workbench?${sp.toString()}`, { scroll: false });
  };

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
    <WorkbenchShell
      title="Technical OSINT Workbench"
      eyebrow="Cyber & Infrastructure Intelligence"
      tagline="USS TJR · Signal Confidence, Source Trust, Threat Assessment"
      tabs={<DomainToggle value={domain} onChange={setDomain} options={DOMAIN_OPTIONS} ariaLabel="OSINT view" />}
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      {loading && !data && <div className="py-16 text-center text-[13px] text-wb-ink2">Loading Technical OSINT…</div>}
      {error && <p className="mb-4 rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">Error: {error}</p>}

      {domain === 'confidence-matrix' && data && (
        <div className="space-y-6">
          <Card title="Signal Distribution by Category & Confidence">
            {/* 2026-08-09 mobile/iPad review (P2): fixed grid-cols-2 gave
                each category ~170px on a 375px phone for a name + 4
                stacked confidence counts — tight but the real fix is just
                not forcing 2 columns below sm. */}
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
