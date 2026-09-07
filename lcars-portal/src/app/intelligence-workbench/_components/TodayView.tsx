'use client';

// TODAY — the default Technical OSINT Workbench landing view (Three-Workbench
// Simplification Phase 1). Answers "what needs me?" first (Needs You), then
// what's worth knowing with no action attached, then a watching summary
// (count only, never a raw dump — mission §18), then the known-unknowns gap
// statement. Mobile order matches mission §30: status -> worth knowing ->
// watching summary -> what we don't know yet, no horizontal scroll.

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui';
import type { Development } from './shared';
import { KNOWN_UNKNOWNS } from './shared';

interface TodayPayload {
  needs_you: Development[];
  worth_knowing: Development[];
  watching_count: number;
  unknowns: { title: string; impact: string; need: string }[];
}

interface Props {
  onOpenWatching: () => void;
  onOpenTechnical: () => void;
}

function DevelopmentCard({ item, tone }: { item: Development; tone: 'needs-you' | 'worth-knowing' }) {
  const border = tone === 'needs-you' ? 'border-wb-crit/40 bg-wb-crit/5' : 'border-wb-line bg-wb-surface';
  return (
    <div className={`space-y-1.5 rounded-xl border p-4 ${border}`}>
      <p className="text-[10.5px] font-semibold uppercase tracking-wide text-wb-ink2">
        {tone === 'needs-you' ? 'Needs you' : 'Worth knowing'}
      </p>
      {item.canonical_url ? (
        <a
          href={item.canonical_url}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-[14px] font-medium leading-snug text-wb-ink underline decoration-dotted hover:text-wb-sage-deep"
        >
          {item.title}
        </a>
      ) : (
        <p className="text-[14px] font-medium leading-snug text-wb-ink">{item.title}</p>
      )}
      <p className="text-[12.5px] text-wb-ink2">{item.what_happened}</p>
      <p className="text-[12.5px] text-wb-ink2">{item.why_you_care}</p>
      <p className="text-[11.5px] italic text-wb-ink2">{item.assessment}</p>
      <p className="text-[12.5px] font-medium text-wb-ink">{item.you_need_to}</p>
      {item.canonical_url && (
        <a href={item.canonical_url} target="_blank" rel="noopener noreferrer" className="inline-block text-[12px] text-wb-sage-deep hover:underline">
          Why it matters →
        </a>
      )}
    </div>
  );
}

export function TodayView({ onOpenWatching, onOpenTechnical }: Props) {
  const [data, setData] = useState<TodayPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch('/api/intelligence-workbench/today')
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed to load');
        if (!cancelled) { setData(d); setError(null); }
      })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <p className="text-[13px] text-wb-ink2">Loading today&apos;s briefing…</p>;
  if (error) return (
    <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-[13px] text-wb-crit-on">
      Unavailable: {error}. <Link href="/agent-status-workbench?tab=pipeline" className="underline">Check pipeline health →</Link>
    </p>
  );
  if (!data) return null;

  const needsYou = data.needs_you ?? [];
  const worthKnowing = data.worth_knowing ?? [];
  const unknowns = data.unknowns?.length ? data.unknowns : KNOWN_UNKNOWNS;

  return (
    <div className="space-y-6">
      {/* Status — always renders first (mission §30 mobile order), never
          conflated with "no data available" (mission §25: clear/empty/
          unavailable/loading are distinct states, this is the "clear" one). */}
      <div className="rounded-xl border border-wb-line bg-wb-surface p-4">
        <p className="text-[15px] font-medium text-wb-ink">
          {needsYou.length === 0
            ? 'ALL CLEAR — nothing currently requires your attention.'
            : `${needsYou.length} development${needsYou.length === 1 ? '' : 's'} need${needsYou.length === 1 ? 's' : ''} your attention.`}
        </p>
        {worthKnowing.length > 0 && needsYou.length === 0 && (
          <p className="mt-1 text-[13px] text-wb-ink2">
            {worthKnowing.length} development{worthKnowing.length === 1 ? ' is' : 's are'} worth knowing about — no action needed.
          </p>
        )}
      </div>

      {needsYou.length > 0 && (
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">Needs you</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {needsYou.map((d) => <DevelopmentCard key={d.event_id} item={d} tone="needs-you" />)}
          </div>
        </div>
      )}

      {worthKnowing.length > 0 && (
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">Worth knowing</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {worthKnowing.map((d) => <DevelopmentCard key={d.event_id} item={d} tone="worth-knowing" />)}
          </div>
        </div>
      )}

      {needsYou.length === 0 && worthKnowing.length === 0 && (
        <p className="text-[13px] text-wb-ink2">Nothing worth knowing about in the last 7 days.</p>
      )}

      {/* Watching summary — count only, never a raw item dump (mission §18). */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-wb-line bg-wb-surface p-4 text-[13px] text-wb-ink2">
        <span>
          {data.watching_count > 0
            ? `${data.watching_count} development${data.watching_count === 1 ? ' is' : 's are'} being monitored automatically. Nothing required from you.`
            : 'Nothing is currently being monitored automatically.'}
        </span>
        <Button size="sm" variant="secondary" onClick={onOpenWatching} className="ml-auto">View watching →</Button>
      </div>

      {/* What we don't know yet. */}
      <div className="rounded-xl border border-wb-line bg-wb-surface p-4">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-wb-ink2">What we don&apos;t know yet</p>
        <div className="space-y-2">
          {unknowns.map((u) => (
            <div key={u.title} className="text-[12.5px] text-wb-ink2">
              <span className="font-medium text-wb-ink">{u.title}:</span> {u.impact}
              {u.need && <span className="italic"> — need: {u.need}</span>}
            </div>
          ))}
        </div>
      </div>

      <button
        type="button"
        onClick={onOpenTechnical}
        className="text-[12px] text-wb-ink2 underline decoration-dotted hover:text-wb-sage-deep"
      >
        Technical view (analyst console) →
      </button>
    </div>
  );
}
