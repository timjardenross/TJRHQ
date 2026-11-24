'use client';

// SOURCE COVERAGE — is each registered source actually delivering? Counts per
// state first, then every non-healthy source with the reason it is in that
// state. Rules live in src/lib/sourceEffectiveness.ts (parity with the Python
// classifier). Read-only.

import { useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/ui';
import { stateToneClasses } from '@/lib/departments';
import type { StateTone } from '@/lib/types';
import { useAbortEffect } from '@/hooks/useAbortEffect';
import { SOURCE_STATES, type ClassifiedSource, type SourceState } from '@/lib/sourceEffectiveness';

interface Payload {
  limitations_line: string;
  summary: Record<SourceState, number>;
  sources: ClassifiedSource[];
}

const STATE_TONE: Record<SourceState, StateTone> = {
  HEALTHY: 'ok',
  QUIET: 'ok',
  UNVERIFIED: 'warn',
  DEGRADED: 'warn',
  BROKEN: 'crit',
  UNCOVERED: 'unknown',
};

const STATE_LABEL: Record<SourceState, string> = {
  HEALTHY: 'Healthy',
  QUIET: 'Quiet (verified)',
  UNVERIFIED: 'Unverified',
  DEGRADED: 'Degraded',
  BROKEN: 'Broken',
  UNCOVERED: 'Uncovered',
};

export function SourceCoverageView() {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useAbortEffect((signal, alive) => {
    setLoading(true);
    fetch('/api/intelligence-workbench/source-coverage', { signal })
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed to load');
        if (alive()) { setData(d); setError(null); }
      })
      .catch((e) => { if (alive() && e instanceof Error && e.name !== 'AbortError') setError(e.message || 'Failed to load'); })
      .finally(() => { if (alive()) setLoading(false); });
  }, []);

  if (loading) return <p className="text-wb-body text-wb-ink2">Loading source coverage…</p>;
  if (error || !data) return (
    <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-wb-body text-wb-crit-on">
      Unavailable: {error}. <Link href="/agent-status-workbench?tab=pipeline" className="underline">Check pipeline health →</Link>
    </p>
  );

  const order = (s: SourceState) => SOURCE_STATES.indexOf(s);
  const unhealthy = data.sources
    .filter((s) => s.state !== 'HEALTHY')
    .sort((a, b) => {
      const rank = (s: SourceState) => (s === 'BROKEN' ? 0 : s === 'UNCOVERED' ? 1 : s === 'DEGRADED' ? 2 : s === 'UNVERIFIED' ? 3 : 4);
      return rank(a.state) - rank(b.state) || order(a.state) - order(b.state) || a.source_name.localeCompare(b.source_name);
    });

  return (
    <div className="space-y-4">
      <p className="text-wb-label text-wb-ink2">
        Registry presence is not coverage. Each source is graded on whether its checks succeed and whether it is delivering items.
      </p>
      {data.limitations_line && (
        <p className="rounded-lg border border-wb-line bg-wb-surface p-3 text-wb-label text-wb-ink">{data.limitations_line}</p>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {SOURCE_STATES.map((s) => (
          <div key={s} className="rounded-xl border border-wb-line bg-wb-surface p-3">
            <p className="flex items-center gap-2 text-wb-label text-wb-ink2">
              <span className={`inline-block h-2 w-2 rounded-full ${stateToneClasses(STATE_TONE[s]).dot}`} aria-hidden />
              {STATE_LABEL[s]}
            </p>
            <p className="mt-1 font-serif text-2xl text-wb-ink">{data.summary[s] ?? 0}</p>
          </div>
        ))}
      </div>
      <Card title={`Needs a look (${unhealthy.length})`}>
        {unhealthy.length === 0 ? (
          <p className="text-wb-body text-wb-ink2">Every source is healthy.</p>
        ) : (
          <ul className="space-y-2">
            {unhealthy.map((s) => (
              <li key={`${s.state}:${s.source_name}`} className="border-b border-wb-line pb-2 last:border-0">
                <p className="flex items-center gap-2 text-wb-body font-medium text-wb-ink">
                  <span className={`inline-block h-2 w-2 rounded-full ${stateToneClasses(STATE_TONE[s.state]).dot}`} aria-hidden />
                  {s.source_name}
                  <span className="text-wb-label font-normal text-wb-ink2">{STATE_LABEL[s.state]}</span>
                </p>
                <p className="text-wb-label text-wb-ink2">{s.reason}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
