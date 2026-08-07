'use client';

// OSINT Intelligence Workbench — 4 views aligned to intelligence tradecraft

import { useCallback, useEffect, useState } from 'react';
import { Card, WorkbenchShell, DomainToggle } from '@/components/ui';

type Domain = 'confidence-matrix' | 'intelligence-summary' | 'source-network' | 'threat-assessment';

type Payload = {
  domain: Domain;
  matrix?: Record<string, Record<string, number>>;
  high?: any[];
  medium?: any[];
  low?: any[];
  unknowns?: any[];
  trending?: any[];
  threats?: any[];
  gaps?: any[];
  [key: string]: any;
};

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

    const endpoint = {
      'confidence-matrix': '/api/intelligence-workbench/confidence-matrix',
      'intelligence-summary': '/api/intelligence-workbench/intelligence-summary',
      'source-network': '/api/intelligence-workbench/source-network',
      'threat-assessment': '/api/intelligence-workbench/threat-assessment',
    }[domain];

    return fetch(endpoint)
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(typeof d?.error === 'string' ? d.error : 'Failed to load');
        setError(null);
        setData(d);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Failed to load');
        setData({ domain } as Payload);
      })
      .finally(() => { if (withSpinner) setLoading(false); });
  }, [domain]);

  useEffect(() => {
    load(true);
  }, [load]);

  return (
    <WorkbenchShell
      title="OSINT Intelligence Workbench"
      eyebrow="Intelligence Operations"
      homeHref="/intelligence-workbench"
      tagline="USS TJR · Signal Confidence, Source Trust, Threat Assessment"
      right={<DomainToggle value={domain} onChange={setDomain} options={DOMAIN_OPTIONS} ariaLabel="OSINT view" />}
    >
      {error && (
        <p className="mb-4 rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">
          Could not load: {error}
        </p>
      )}

      {/* Signal Confidence Matrix */}
      {domain === 'confidence-matrix' && data ? (
        <div className="space-y-6">
          <Card title="Signal Distribution by Category & Confidence">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-wb-line">
                      <th className="text-left py-2 px-3 font-semibold">Category</th>
                      <th className="text-center py-2 px-3 font-semibold">HIGH</th>
                      <th className="text-center py-2 px-3 font-semibold">MEDIUM</th>
                      <th className="text-center py-2 px-3 font-semibold">LOW</th>
                      <th className="text-center py-2 px-3 font-semibold">UNKNOWN</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.matrix && Object.entries(data.matrix).map(([cat, counts]: [string, any]) => (
                      <tr key={cat} className="border-b border-wb-line hover:bg-wb-line/20">
                        <td className="py-2 px-3 font-medium">{cat}</td>
                        <td className="text-center py-2 px-3 font-semibold">{counts.high || 0}</td>
                        <td className="text-center py-2 px-3 font-semibold">{counts.medium || 0}</td>
                        <td className="text-center py-2 px-3 font-semibold">{counts.low || 0}</td>
                        <td className="text-center py-2 px-3">{counts.unknown || 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Coverage Assessment">
            <div className="space-y-3 text-[12px] text-wb-ink2">
              <div><strong>Strong:</strong> Cybersecurity (TIER_1), Regulatory (TIER_1)</div>
              <div><strong>Gaps:</strong> Infrastructure UNKNOWN, Intelligence UNKNOWN</div>
              <div><strong>Risk:</strong> Over-reliance on single regulatory source (CISA)</div>
            </div>
          </Card>
        </div>
      ) : null}

      {/* Intelligence Summary */}
      {domain === 'intelligence-summary' && data ? (
        <div className="space-y-6">
          {/* HIGH Confidence */}
          <Card title="🟢 HIGH CONFIDENCE — Act immediately">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (data.high?.length ?? 0) === 0 ? (
              <p className="text-[13px] text-wb-ink2">No high-confidence signals.</p>
            ) : (
              data.high!.map((sig: any) => (
                <div key={sig.event_id} className="py-3 border-b border-wb-line last:border-0">
                  <div className="font-medium">{sig.raw_title}</div>
                  <div className="text-[11px] text-wb-ink2 mt-1">{sig.source_name} • SRS {(sig.rank_score ?? 0).toFixed(0)}</div>
                </div>
              ))
            )}
          </Card>

          {/* MEDIUM Confidence */}
          <Card title="🟡 MEDIUM CONFIDENCE — Cross-verify">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (data.medium?.length ?? 0) === 0 ? (
              <p className="text-[13px] text-wb-ink2">No medium-confidence signals.</p>
            ) : (
              data.medium!.map((sig: any) => (
                <div key={sig.event_id} className="py-3 border-b border-wb-line last:border-0">
                  <div className="font-medium">{sig.raw_title}</div>
                  <div className="text-[11px] text-wb-ink2 mt-1">{sig.source_name} • Needs verification</div>
                </div>
              ))
            )}
          </Card>

          {/* LOW Confidence */}
          <Card title="🔴 LOW CONFIDENCE — Research/Archive">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (data.low?.length ?? 0) === 0 ? (
              <p className="text-[13px] text-wb-ink2">No low-confidence signals.</p>
            ) : (
              data.low!.map((sig: any) => (
                <div key={sig.event_id} className="py-3 border-b border-wb-line last:border-0">
                  <div className="font-medium">{sig.raw_title}</div>
                  <div className="text-[11px] text-wb-ink2 mt-1">{sig.source_name} • Single source, archive or verify</div>
                </div>
              ))
            )}
          </Card>

          {/* Known Unknowns */}
          <Card title="⚠️ KNOWN UNKNOWNS">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (
              <div className="space-y-3 text-[12px]">
                {data.unknowns?.map((u: any, i: number) => (
                  <div key={i} className="border-l-3 border-wb-line pl-3">
                    <div className="font-medium">{u.title}</div>
                    <div className="text-wb-ink2">Risk: {u.impact}</div>
                    <div className="text-wb-ink2">Fix: {u.need}</div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      ) : null}

      {/* Source Trust Network */}
      {domain === 'source-network' && data ? (
        <div className="space-y-6">
          <Card title="Cross-Source Corroboration">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (
              <div className="space-y-4 text-[12px]">
                <div className="border-l-3 border-wb-line pl-4">
                  <div className="font-medium">High-confidence clusters</div>
                  <div className="text-wb-ink2 text-[11px]">Signals confirmed by 3+ TIER_1 sources</div>
                </div>
                <div className="border-l-3 border-wb-line pl-4">
                  <div className="font-medium">Medium-confidence isolated</div>
                  <div className="text-wb-ink2 text-[11px]">Single TIER_2 source, needs verification</div>
                </div>
                <div className="border-l-3 border-wb-line pl-4">
                  <div className="font-medium">Low-confidence noise</div>
                  <div className="text-wb-ink2 text-[11px]">TIER_4 sources, contradicted by higher tiers</div>
                </div>
              </div>
            )}
          </Card>

          <Card title="Source Reliability Trending">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (
              <div className="space-y-3 text-[12px]">
                {data.trending?.map((t: any, i: number) => (
                  <div key={i} className="flex justify-between items-center py-2 border-b border-wb-line last:border-0">
                    <div className="font-medium">{t.source}</div>
                    <div className="text-wb-ink2">{t.from} → {t.to}</div>
                    <div>{t.direction === 'up' ? '↗' : t.direction === 'stable' ? '→' : '↘'}</div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      ) : null}

      {/* Threat Assessment */}
      {domain === 'threat-assessment' && data ? (
        <div className="space-y-6">
          <Card title="Escalation Matrix: Probability × Impact × Confidence">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (data.threats?.length ?? 0) === 0 ? (
              <p className="text-[13px] text-wb-ink2">No threats requiring assessment.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-wb-line">
                      <th className="text-left py-2 px-3 font-semibold">Threat</th>
                      <th className="text-center py-2 px-3 font-semibold">Prob</th>
                      <th className="text-center py-2 px-3 font-semibold">Impact</th>
                      <th className="text-center py-2 px-3 font-semibold">Conf</th>
                      <th className="text-center py-2 px-3 font-semibold">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.threats!.map((t: any, i: number) => (
                      <tr key={i} className="border-b border-wb-line hover:bg-wb-line/20">
                        <td className="py-2 px-3">{(t.threat ?? '').slice(0, 40)}...</td>
                        <td className="text-center py-2 px-3">{t.probability}</td>
                        <td className="text-center py-2 px-3 font-medium">{t.impact}</td>
                        <td className="text-center py-2 px-3 font-medium">{t.confidence}</td>
                        <td className="text-center py-2 px-3 font-semibold">{(t.escalation ?? 'monitor').toUpperCase()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Coverage Gaps vs. Threat Surface">
            {loading ? (
              <p className="text-[13px] text-wb-ink2">Loading…</p>
            ) : (
              <div className="space-y-3 text-[12px] text-wb-ink2">
                {data.gaps?.map((g: any, i: number) => (
                  <div key={i} className="border-l-3 border-wb-line pl-3">
                    <div className="font-medium">{g.area}</div>
                    <div>Risk: <span className="font-semibold">{g.risk}</span></div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      ) : null}
    </WorkbenchShell>
  );
}
