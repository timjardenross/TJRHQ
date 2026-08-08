'use client';

import { useCallback, useEffect, useState } from 'react';
import { Card, WorkbenchShell, DomainToggle } from '@/components/ui';

type Domain = 'confidence-matrix' | 'intelligence-summary' | 'source-network' | 'threat-assessment';

type Payload = { domain: Domain; [key: string]: any };

const DOMAIN_OPTIONS: { key: Domain; label: string }[] = [
  { key: 'confidence-matrix', label: 'Signal Confidence Matrix' },
  { key: 'intelligence-summary', label: 'Intelligence Summary' },
  { key: 'source-network', label: 'Source Trust Network' },
  { key: 'threat-assessment', label: 'Threat Assessment' },
];

export default function OSINTWorkbench() {
  const [domain, setDomain] = useState<Domain>('confidence-matrix');
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

  return (
    <WorkbenchShell
      title="OSINT Intelligence Workbench"
      eyebrow="Intelligence Operations"
      homeHref="/intelligence-workbench"
      tagline="USS TJR · Signal Confidence, Source Trust, Threat Assessment"
      right={<DomainToggle value={domain} onChange={setDomain} options={DOMAIN_OPTIONS} ariaLabel="OSINT view" />}
    >
      {error && <p className="mb-4 rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">Error: {error}</p>}

      {domain === 'confidence-matrix' && data && (
        <div className="space-y-6">
          <Card title="Signal Distribution by Category & Confidence">
            <div className="grid grid-cols-2 gap-4 text-[12px] text-wb-ink2">
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
            <Card title="🟢 HIGH CONFIDENCE">
              <div className="space-y-2">
                {data.high.slice(0, 5).map((s: any) => (
                  <div key={s.event_id} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
                    <div className="font-semibold text-wb-ink">{s.raw_title}</div>
                    <div>{s.source_name} • Score: {s.rank_score.toFixed(1)}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {data.medium?.length > 0 && (
            <Card title="🟡 MEDIUM CONFIDENCE">
              <div className="space-y-2">
                {data.medium.slice(0, 5).map((s: any) => (
                  <div key={s.event_id} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
                    <div className="font-semibold text-wb-ink">{s.raw_title}</div>
                    <div>{s.source_name} • Score: {s.rank_score.toFixed(1)}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {data.low?.length > 0 && (
            <Card title="🔴 LOW CONFIDENCE">
              <div className="space-y-2">
                {data.low.slice(0, 3).map((s: any) => (
                  <div key={s.event_id} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
                    <div className="font-semibold text-wb-ink">{s.raw_title}</div>
                    <div>{s.source_name}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {data.unknowns?.length > 0 && (
            <Card title="⚠️ KNOWN UNKNOWNS">
              <div className="space-y-2">
                {data.unknowns.map((u: any) => (
                  <div key={u.title} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
                    <div className="font-semibold text-wb-ink">{u.title}</div>
                    <div>{u.impact}</div>
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
                .slice(0, 5)
                .map(([srcId, info]: any) => (
                  <div key={srcId}>
                    Source: {srcId} • {info.signals} signals • {info.confirmCount} confirmations
                  </div>
                ))}
            </div>
          </Card>
          <Card title="Source Trending">
            <div className="text-[12px] text-wb-ink2 space-y-1">
              {data.trending?.map((t: any) => (
                <div key={t.source}>
                  {t.source} {t.direction === 'up' ? '↗' : t.direction === 'stable' ? '→' : '↘'} {t.from} → {t.to}
                </div>
              ))}
            </div>
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
                </div>
              ))}
            </div>
          </Card>
          {data.gaps?.length > 0 && (
            <Card title="Coverage Gaps">
              <div className="text-[12px] text-wb-ink2 space-y-1">
                {data.gaps.map((g: any) => (
                  <div key={g.area}>{g.area}: {g.risk}</div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </WorkbenchShell>
  );
}
