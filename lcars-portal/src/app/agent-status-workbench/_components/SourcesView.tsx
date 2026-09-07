'use client';

import { useEffect, useState } from 'react';
import { Card, Badge } from '@/components/ui';
import { relativeTime, sourceStatusToBadge, sourceStatusLabel } from './shared';
import type { SourceStatus } from './shared';

interface TechnicalSourceRow {
  sourceId: string;
  sourceName: string;
  sourceType: string;
  category: string;
  status: SourceStatus;
  lastCheckedAt: string | null;
  errorMessage: string | null;
  active: boolean;
}

interface HealthSourceRow {
  sourceId: string;
  sourceName: string;
  sourceType: string | null;
  status: SourceStatus;
  cadence: string | null;
  lastFetch: string | null;
  lastFetchStatus: string | null;
  lastFetchMessage: string | null;
}

interface SourcesData {
  technical: TechnicalSourceRow[];
  health: HealthSourceRow[];
  healthUncadenced: number;
  note: string;
}

const STATUS_ORDER: Record<SourceStatus, number> = { failing: 0, delayed: 1, degraded: 2, unknown: 3, healthy: 4 };

export function SourcesView() {
  const [data, setData] = useState<SourcesData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch('/api/agent-status-workbench/sources', { cache: 'no-store' });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body?.error ?? `HTTP ${res.status}`);
        }
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Failed to load source health');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  if (isLoading) return <Card><p className="text-[13px] italic text-wb-ink2">Loading source health…</p></Card>;
  if (loadError || !data) {
    return (
      <Card>
        <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
          <p className="text-[13px] font-semibold text-wb-crit-on">Source health unavailable</p>
          <p className="mt-1 text-[12px] text-wb-ink2">{loadError ?? 'No data returned.'}</p>
        </div>
      </Card>
    );
  }

  const technical = [...data.technical].sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status]);
  const health = [...data.health].sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status]);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="mb-3 font-serif text-lg text-wb-ink">Technical OSINT Sources ({technical.length})</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-wb-line">
                <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Source</th>
                <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Category</th>
                <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Status</th>
                <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Last Success</th>
                <th className="pb-2 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Error</th>
              </tr>
            </thead>
            <tbody>
              {technical.map((s) => (
                <tr key={s.sourceId} className="border-b border-wb-line last:border-0">
                  <td className="py-2.5 pr-4 text-[13px] font-medium text-wb-ink">{s.sourceName}</td>
                  <td className="py-2.5 pr-4 text-[12px] text-wb-ink2">{s.category} · {s.sourceType}</td>
                  <td className="py-2.5 pr-4"><Badge status={sourceStatusToBadge(s.status)}>{sourceStatusLabel(s.status)}</Badge></td>
                  <td className="py-2.5 pr-4 text-[12px] tabular-nums text-wb-ink2">{relativeTime(s.lastCheckedAt)}</td>
                  <td className="py-2.5 max-w-[320px] truncate text-[12px] text-wb-ink2" title={s.errorMessage ?? undefined}>
                    {s.errorMessage ?? <span className="italic">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] text-wb-ink2">No per-source cadence metadata exists for technical sources (only source_type/priority) — &ldquo;Last Success&rdquo; is shown without an expected-cadence comparison.</p>
      </Card>

      <Card>
        <h2 className="mb-3 font-serif text-lg text-wb-ink">Health OSINT Sources — auto-fetched ({health.length})</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-wb-line">
                <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Source</th>
                <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Cadence</th>
                <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Status</th>
                <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Last Fetch</th>
                <th className="pb-2 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Parser / fetch error</th>
              </tr>
            </thead>
            <tbody>
              {health.map((s) => (
                <tr key={s.sourceId} className="border-b border-wb-line last:border-0">
                  <td className="py-2.5 pr-4 text-[13px] font-medium text-wb-ink">{s.sourceName}</td>
                  <td className="py-2.5 pr-4 text-[12px] text-wb-ink2">{s.cadence ?? '—'}</td>
                  <td className="py-2.5 pr-4"><Badge status={sourceStatusToBadge(s.status)}>{sourceStatusLabel(s.status)}</Badge></td>
                  <td className="py-2.5 pr-4 text-[12px] tabular-nums text-wb-ink2">{relativeTime(s.lastFetch)}</td>
                  <td className="py-2.5 max-w-[320px] truncate text-[12px] text-wb-ink2" title={s.lastFetchMessage ?? undefined}>
                    {s.lastFetchStatus === 'failed' ? (s.lastFetchMessage ?? 'Failed — no detail') : <span className="italic">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] text-wb-ink2">{data.note}</p>
      </Card>
    </div>
  );
}
