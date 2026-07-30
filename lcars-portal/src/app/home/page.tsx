'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Card, RiskPill, WorkbenchShell } from '@/components/ui';

type NeedsAttention = {
  hotSignals: Array<{
    event_id: string;
    raw_title: string;
    risk_rating: string | null;
    sector: string | null;
    collected_at: string;
    canonical_url: string | null;
  }>;
  pendingBriefs: Array<{
    brief_id: string;
    overall_risk: string | null;
    approval_status: string | null;
    generated_at: string;
    executive_snapshot: string | null;
  }>;
  interrupts: Array<{
    id: string;
    brief_type: string;
    signals_count: number;
    generated_at: string;
  }>;
  staleSources: Array<{
    source_id: string;
    status: string;
    checked_at: string;
    error_message: string | null;
  }>;
  hasAnything: boolean;
};

export default function HomePage() {
  const [data, setData] = useState<NeedsAttention | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/home/needs-attention');
      if (!res.ok) throw new Error('Failed to load home data');
      const d = await res.json();
      setError(null);
      setData(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60000); // refresh every minute
    return () => clearInterval(interval);
  }, [load]);

  if (error) {
    return (
      <WorkbenchShell
        title="Home"
        eyebrow="USS TJR"
        tagline="Daily Operations Dashboard"
        homeHref="/home"
      >
        <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">
          {error}
        </p>
      </WorkbenchShell>
    );
  }

  if (loading) {
    return (
      <WorkbenchShell title="Home" eyebrow="USS TJR" tagline="Daily Operations Dashboard" homeHref="/home">
        <p className="text-wb-ink2">Loading…</p>
      </WorkbenchShell>
    );
  }

  // Quiet day — nothing needs attention
  if (!data?.hasAnything) {
    return (
      <WorkbenchShell title="Home" eyebrow="USS TJR" tagline="Daily Operations Dashboard" homeHref="/home">
        <div className="mx-auto max-w-md text-center py-16">
          <h2 className="font-serif text-2xl text-wb-ink mb-2">All Clear</h2>
          <p className="text-wb-ink2 mb-8">
            No signals requiring immediate attention. All systems operational.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Link
              href="/intelligence-workbench"
              className="rounded-md border border-wb-sage-deep bg-wb-sage-deep px-3 py-2 text-[13px] text-white transition hover:-translate-y-px"
            >
              Intelligence →
            </Link>
            <Link
              href="/captains-chair-workbench"
              className="rounded-md border border-wb-sage-deep/40 bg-wb-sage-deep/10 px-3 py-2 text-[13px] text-wb-sage-deep transition hover:bg-wb-sage-deep/20"
            >
              Captain&apos;s Chair →
            </Link>
          </div>
        </div>
      </WorkbenchShell>
    );
  }

  // Busy day — show what needs attention
  return (
    <WorkbenchShell title="Home" eyebrow="USS TJR" tagline="Daily Operations Dashboard" homeHref="/home">
      <div className="grid grid-cols-1 gap-6">
        {/* HOT SIGNALS */}
        {(data?.hotSignals?.length ?? 0) > 0 && (
          <Card title="🔴 Hot Signals — Immediate Attention">
            {data!.hotSignals.map((signal) => (
              <a
                key={signal.event_id}
                href={signal.canonical_url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 border-b border-wb-line py-2.5 text-sm last:border-0 transition hover:bg-wb-line/20"
              >
                <RiskPill value={signal.risk_rating} />
                <span className="flex-1 line-clamp-2">{signal.raw_title}</span>
                <span className="text-[11px] text-wb-ink2">{signal.sector ?? '—'}</span>
              </a>
            ))}
          </Card>
        )}

        {/* PENDING BRIEFS */}
        {(data?.pendingBriefs?.length ?? 0) > 0 && (
          <Card title="📋 Pending Briefs — QA Review">
            {data!.pendingBriefs.map((brief) => (
              <Link
                key={brief.brief_id}
                href={`/intelligence-workbench/brief/${brief.brief_id}`}
                className="flex items-start gap-3 border-b border-wb-line py-2.5 last:border-0 transition hover:bg-wb-line/20 block"
              >
                <RiskPill value={brief.overall_risk} />
                <div className="flex-1">
                  <div className="text-sm font-medium text-wb-ink line-clamp-2">
                    {brief.executive_snapshot?.split('.')[0]?.slice(0, 100) || `Brief ${brief.brief_id.slice(0, 8)}`}
                  </div>
                  <div className="text-[11px] text-wb-ink2 mt-1">
                    Generated: {new Date(brief.generated_at).toLocaleString()}
                  </div>
                </div>
                <span className="text-[12px] text-wb-ink2 whitespace-nowrap">{brief.approval_status}</span>
              </Link>
            ))}
          </Card>
        )}

        {/* CAPTAIN'S BRIEF INTERRUPTS */}
        {(data?.interrupts?.length ?? 0) > 0 && (
          <Card title="⚡ Captain's Brief Interrupts">
            {data!.interrupts.map((interrupt) => (
              <Link
                key={interrupt.id}
                href="/captains-brief-workbench"
                className="flex items-center gap-3 border-b border-wb-line py-2.5 text-sm last:border-0 transition hover:bg-wb-line/20"
              >
                <span className="flex h-2 w-2 rounded-full bg-wb-crit animate-pulse" aria-hidden />
                <span className="flex-1">{interrupt.brief_type} — {interrupt.signals_count} signals</span>
                <span className="text-[11px] text-wb-ink2">
                  {new Date(interrupt.generated_at).toLocaleTimeString()}
                </span>
              </Link>
            ))}
          </Card>
        )}

        {/* STALE SOURCES */}
        {(data?.staleSources?.length ?? 0) > 0 && (
          <Card title="⚠️ Source Health Issues">
            {data!.staleSources.map((source) => (
              <Link
                key={source.source_id}
                href="/intelligence-workbench?domain=operational"
                className="flex items-start gap-3 border-b border-wb-line py-2.5 last:border-0 transition hover:bg-wb-line/20"
              >
                <span className={`text-xs font-semibold rounded px-1.5 py-0.5 ${
                  source.status === 'failed'
                    ? 'bg-wb-crit/20 text-wb-crit'
                    : 'bg-wb-amber/20 text-wb-amber'
                }`}>
                  {source.status.toUpperCase()}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-wb-ink">{source.source_id}</div>
                  {source.error_message && (
                    <p className="text-[11px] text-wb-ink2 line-clamp-1 mt-0.5">{source.error_message}</p>
                  )}
                </div>
              </Link>
            ))}
          </Card>
        )}

        {/* NAVIGATION SUGGESTIONS */}
        <div className="grid grid-cols-2 gap-3">
          <Link
            href="/intelligence-workbench"
            className="rounded-md border border-wb-sage-deep/40 bg-wb-sage-deep/10 px-3 py-2 text-[13px] text-wb-sage-deep transition hover:bg-wb-sage-deep/20 text-center"
          >
            View Intelligence →
          </Link>
          <Link
            href="/captains-chair-workbench"
            className="rounded-md border border-wb-sage-deep/40 bg-wb-sage-deep/10 px-3 py-2 text-[13px] text-wb-sage-deep transition hover:bg-wb-sage-deep/20 text-center"
          >
            Captain&apos;s Dashboard →
          </Link>
        </div>
      </div>
    </WorkbenchShell>
  );
}
