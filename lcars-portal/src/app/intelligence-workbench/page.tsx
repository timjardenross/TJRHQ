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

      {domain === 'confidence-matrix' && (
        <div className="space-y-6">
          <Card title="Signal Distribution by Category & Confidence">
            <p className="text-[12px] text-wb-ink2">Cybersecurity: 8 HIGH, 3 MEDIUM | Infrastructure: 5 HIGH, 4 MEDIUM | Regulatory: 12 HIGH, 2 MEDIUM</p>
          </Card>
          <Card title="Coverage Assessment"><p className="text-[12px] text-wb-ink2">Strong: Cybersecurity, Regulatory | Gaps: Infrastructure, Intelligence</p></Card>
        </div>
      )}

      {domain === 'intelligence-summary' && (
        <div className="space-y-6">
          <Card title="🟢 HIGH CONFIDENCE"><p className="text-[12px] text-wb-ink2">Critical RCE, AWS outages — act immediately</p></Card>
          <Card title="🟡 MEDIUM CONFIDENCE"><p className="text-[12px] text-wb-ink2">DDoS reports, API errors — cross-verify</p></Card>
          <Card title="🔴 LOW CONFIDENCE"><p className="text-[12px] text-wb-ink2">Unconfirmed rumors — research or archive</p></Card>
          <Card title="⚠️ KNOWN UNKNOWNS"><p className="text-[12px] text-wb-ink2">Internal threats, supply chain risks</p></Card>
        </div>
      )}

      {domain === 'source-network' && (
        <div className="space-y-6">
          <Card title="Cross-Source Corroboration"><p className="text-[12px] text-wb-ink2">High-confidence clusters: 3+ TIER_1 sources confirming</p></Card>
          <Card title="Source Trending"><p className="text-[12px] text-wb-ink2">CISA ↗ improving | AWS → stable | SecurityBlog ↘ declining</p></Card>
        </div>
      )}

      {domain === 'threat-assessment' && (
        <div className="space-y-6">
          <Card title="Escalation Matrix"><p className="text-[12px] text-wb-ink2">Cisco RCE: HIGH/CRITICAL/HIGH → ESCALATE | AWS: HIGH/HIGH/HIGH → ESCALATE | DDoS: MED/MED/MED → WATCH</p></Card>
          <Card title="Coverage Gaps"><p className="text-[12px] text-wb-ink2">Blind to internal compromise, supply chain, zero-days</p></Card>
        </div>
      )}
    </WorkbenchShell>
  );
}
