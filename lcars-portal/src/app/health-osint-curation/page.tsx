'use client';

// Health OSINT Curation — HEALTH_OSINT_IMPLEMENTATION.md Phase 5.
//
// Sunday-night review queue for signals the automated weekly fetch
// (tools/health-osint/health_signal_ingestion.py, wired into
// intelligence/scheduler.py) pulled in. Conservative by design: every
// auto-ingested signal starts suppressed and unreviewed — nothing from
// this pipeline reaches the main /health-osint dashboard until a human
// looks at it here and clicks Publish.

import { useEffect, useState } from 'react';
import { WorkbenchShell, Card } from '@/components/ui';

interface PendingSignal {
  signal_id: string;
  title: string;
  description: string | null;
  signal_type: string;
  health_domain: string;
  source_name: string | null;
  collected_at: string;
  canonical_url: string | null;
}

interface FetchStat {
  source_name: string | null;
  last_fetch: string | null;
  last_fetch_status: string | null;
  last_fetch_message: string | null;
}

export default function HealthOsintCurationPage() {
  const [pending, setPending] = useState<PendingSignal[]>([]);
  const [fetchStats, setFetchStats] = useState<FetchStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  function load() {
    setLoading(true);
    fetch('/api/health-osint-curation/pending')
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to load (${r.status})`);
        return r.json();
      })
      .then((data) => {
        setPending(data.signals ?? []);
        setFetchStats(data.fetch_stats ?? []);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  async function decide(signalId: string, action: 'publish' | 'reject') {
    setBusyId(signalId);
    try {
      const res = await fetch(`/api/health-osint-curation/${signalId}/${action}`, { method: 'POST' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.error || `Failed to ${action}`);
      }
      setPending((prev) => prev.filter((s) => s.signal_id !== signalId));
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to ${action}`);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <WorkbenchShell wide
      title="Health OSINT Curation"
      eyebrow="Sunday Night Review"
      tagline="USS TJR · Auto-ingested signals pending approval — nothing publishes without a human decision"
      back={{ href: '/health-osint', label: 'Health OSINT' }}
    >
      {error && (
        <p className="mb-4 rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">
          {error}
        </p>
      )}

      {fetchStats.length > 0 && (
        <Card title="Last Fetch, Per Source">
          <div className="space-y-1.5 text-xs">
            {fetchStats.map((s) => (
              <div key={s.source_name} className="flex items-center justify-between gap-3">
                <span className="text-wb-ink2">{s.source_name ?? 'Unknown source'}</span>
                <span className="flex items-center gap-2">
                  <span
                    className={
                      s.last_fetch_status === 'success'
                        ? 'text-wb-sage-deep'
                        : s.last_fetch_status === 'failed'
                          ? 'text-wb-crit'
                          : 'text-wb-ink2'
                    }
                  >
                    {s.last_fetch_status ?? 'never run'}
                  </span>
                  {s.last_fetch && (
                    <span className="text-wb-ink2/70">{new Date(s.last_fetch).toLocaleString()}</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card title={`Pending Review (${pending.length})`}>
        {loading ? (
          <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>
        ) : pending.length === 0 ? (
          <p className="text-sm text-wb-ink2">Nothing pending — queue is clear.</p>
        ) : (
          <div className="space-y-4">
            {pending.map((signal) => (
              <div key={signal.signal_id} className="border-b border-wb-line pb-4 text-sm last:border-b-0 last:pb-0">
                <div className="font-semibold text-wb-ink">
                  {signal.canonical_url ? (
                    <a href={signal.canonical_url} target="_blank" rel="noreferrer" className="hover:underline">
                      {signal.title}
                    </a>
                  ) : (
                    signal.title
                  )}
                </div>
                <div className="mt-1 text-xs text-wb-ink2">
                  {signal.source_name ?? 'Unknown source'} · {signal.signal_type} · {signal.health_domain}
                  {' · '}
                  {new Date(signal.collected_at).toLocaleString()}
                </div>
                {signal.description && (
                  <p className="mt-2 text-xs text-wb-ink2/80">{signal.description.slice(0, 220)}…</p>
                )}
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    disabled={busyId === signal.signal_id}
                    onClick={() => decide(signal.signal_id, 'publish')}
                    className="rounded bg-wb-sage-deep px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                  >
                    ✓ Publish
                  </button>
                  <button
                    type="button"
                    disabled={busyId === signal.signal_id}
                    onClick={() => decide(signal.signal_id, 'reject')}
                    className="rounded bg-wb-crit/10 px-3 py-1 text-xs font-medium text-wb-crit disabled:opacity-50"
                  >
                    ✗ Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </WorkbenchShell>
  );
}
