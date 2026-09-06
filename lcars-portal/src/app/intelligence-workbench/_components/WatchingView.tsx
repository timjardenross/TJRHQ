'use client';

// WATCHING — WATCH-disposition developments. Bounded list (API caps at 50,
// most-significant-first), not a raw queue — mission §18 still applies here:
// this view exists precisely so "watching" doesn't mean "buried in a queue
// of hundreds", each item states why it's being watched and what would move
// it, so scanning the list is itself informative rather than a wall of text.

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { RiskPill } from '@/components/ui';

interface WatchItem {
  event_id: string;
  title: string;
  canonical_url: string | null;
  why_watched: string;
  confidence_level: string;
  significance: string;
  geography: string | null;
  corroboration: number;
  what_would_change_this: string;
  last_update: string | null;
}

export function WatchingView() {
  const [items, setItems] = useState<WatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch('/api/intelligence-workbench/watching')
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed to load');
        if (!cancelled) { setItems(d.items ?? []); setError(null); }
      })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <p className="text-[13px] text-wb-ink2">Loading watching list…</p>;
  if (error) return (
    <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-[13px] text-wb-crit-on">
      Unavailable: {error}. <Link href="/agent-status-workbench?tab=pipeline" className="underline">Check pipeline health →</Link>
    </p>
  );

  if (items.length === 0) {
    return <p className="text-[13px] text-wb-ink2">Nothing is currently being monitored automatically.</p>;
  }

  return (
    <div className="space-y-3">
      <p className="text-[12px] text-wb-ink2">
        {items.length} development{items.length === 1 ? '' : 's'} being monitored automatically. Nothing required from you unless one moves to Worth Knowing.
      </p>
      {items.map((w) => (
        <div key={w.event_id} className="space-y-1.5 rounded-xl border border-wb-line bg-wb-surface p-4">
          <div className="flex items-start justify-between gap-2">
            {w.canonical_url ? (
              <a href={w.canonical_url} target="_blank" rel="noopener noreferrer" className="text-[13.5px] font-medium text-wb-ink underline decoration-dotted hover:text-wb-sage-deep">
                {w.title}
              </a>
            ) : (
              <p className="text-[13.5px] font-medium text-wb-ink">{w.title}</p>
            )}
            <RiskPill value={w.significance} />
          </div>
          <p className="text-[12px] text-wb-ink2">{w.why_watched}</p>
          <p className="text-[11.5px] text-wb-ink2">
            {w.confidence_level} confidence{w.geography ? ` · ${w.geography}` : ''}
            {w.corroboration > 0 ? ` · ${w.corroboration} corroborating source${w.corroboration === 1 ? '' : 's'}` : ''}
          </p>
          <p className="text-[11.5px] italic text-wb-ink2">What would change this: {w.what_would_change_this}</p>
          {w.last_update && (
            <p className="text-[11px] text-wb-ink2">Last update: {new Date(w.last_update).toLocaleDateString()}</p>
          )}
        </div>
      ))}
    </div>
  );
}
