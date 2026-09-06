'use client';

// Briefs — HQ's canonical intelligence record (BRIEFS_CANONICAL_UPLIFT.md).
//
// Rebuilt around Latest / Timeline / Explore (Sections 14-18) in place of
// the old publication-state filter tabs (Today / All Published / All / In
// Review (legacy) / Awaiting Publish (legacy)) — those legacy review states
// are pre-2026-08-22 history (auto-publish shipped then), not a live queue,
// and now live inside Explore's advanced filters instead of being the
// primary navigation.

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { Card, RiskPill, WorkbenchShell } from '@/components/ui';
import type { ApprovalStatus, BriefListItem } from '@/lib/briefsShared';
import { buildMorningIntelligenceView, isToday } from '@/lib/briefsShared';

type Tab = 'latest' | 'timeline' | 'explore';

const TABS: { key: Tab; label: string }[] = [
  { key: 'latest', label: 'Latest' },
  { key: 'timeline', label: 'Timeline' },
  { key: 'explore', label: 'Explore' },
];

const STATUS_LABEL: Record<ApprovalStatus, string> = {
  IN_REVIEW: 'In Review (legacy)',
  QA_PASSED: 'Awaiting Publish (legacy)',
  PUBLISHED: 'Published',
};

function excerpt(text: string | null | undefined, len: number): string {
  if (!text) return '';
  return text.length > len ? `${text.slice(0, len)}…` : text;
}

function monthLabel(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, { month: 'long', year: 'numeric' }).toUpperCase();
}

function TabBar({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  return (
    <div className="flex gap-2" role="tablist" aria-label="Briefs views">
      {TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}
          className={`rounded-full border px-4 py-1.5 text-[13px] font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${
            active === t.key
              ? 'border-wb-sage-deep bg-wb-sage-deep text-white'
              : 'border-wb-line text-wb-ink2 hover:bg-wb-bg'
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

function LatestView({ latest, loading }: { latest: BriefListItem | null; loading: boolean }) {
  if (loading) return <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>;

  if (!latest) {
    return (
      <Card title="Today's Brief">
        <p className="text-sm text-wb-ink2">
          Today&rsquo;s brief has not been generated yet. Morning intelligence collection may still be in
          progress — the daily job targets ~06:30 AEST once collection completes, or trigger one on demand
          via the XO bot&rsquo;s <code>/brief</code> command.
        </p>
      </Card>
    );
  }

  const view = buildMorningIntelligenceView(latest, 3);
  const label = latest.published_at ?? latest.generated_at;
  const isFromToday = isToday(label);

  return (
    <Card title={isFromToday ? "Today's Brief" : 'Latest Brief'}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <span className="text-[13px] text-wb-ink2">{new Date(label).toLocaleString()}</span>
        <RiskPill value={latest.overall_risk} />
      </div>

      {view.coverageDegraded && view.coverageNote && (
        <p className="mb-4 rounded-md border border-wb-crit/30 bg-wb-crit/10 p-2.5 text-[12.5px] text-wb-crit-on">
          ⚠️ {view.coverageNote} Assessment may be incomplete in that domain.
        </p>
      )}

      {view.executiveRead && (
        <div className="mb-4">
          <h3 className="mb-1 text-[11px] uppercase tracking-wider text-wb-ink2">Executive Read</h3>
          <p className="text-sm text-wb-ink">{view.executiveRead}</p>
        </div>
      )}

      {view.whatMatters.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-2 text-[11px] uppercase tracking-wider text-wb-ink2">What Matters</h3>
          <ol className="space-y-2">
            {view.whatMatters.map((item, i) => (
              <li key={`${item.title}-${i}`} className="flex gap-2.5 text-sm">
                <span className="shrink-0 font-serif text-wb-ink2">{String(i + 1).padStart(2, '0')}</span>
                <span>
                  <span className="font-medium text-wb-ink">{item.title}</span>
                  {item.soWhat && <span className="text-wb-ink2"> — {item.soWhat}</span>}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {view.changed && (
        <div className="mb-4">
          <h3 className="mb-1.5 text-[11px] uppercase tracking-wider text-wb-ink2">What Changed</h3>
          <div className="space-y-1 text-[13px]">
            {view.changed.new.map((t, i) => <p key={`n${i}`}><span className="font-medium">New —</span> {t}</p>)}
            {view.changed.escalated.map((t, i) => <p key={`e${i}`}><span className="font-medium text-wb-crit-on">Escalated —</span> {t}</p>)}
            {view.changed.improved.map((t, i) => <p key={`i${i}`}><span className="font-medium text-wb-ok">Improved —</span> {t}</p>)}
          </div>
        </div>
      )}

      {view.watch.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-1.5 text-[11px] uppercase tracking-wider text-wb-ink2">Watch</h3>
          <ul className="list-disc space-y-0.5 pl-5 text-[13px] text-wb-ink2">
            {view.watch.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}

      {latest.coverage && (
        <p className="mb-4 text-[12px] text-wb-ink2">
          {latest.coverage.completed ?? '—'}/{latest.coverage.expected ?? '—'} sources successful
          {latest.coverage.latest_included_at ? ` · Current through ${new Date(latest.coverage.latest_included_at).toLocaleTimeString()}` : ''}
        </p>
      )}

      <Link href={`/briefs/${encodeURIComponent(latest.brief_id)}`} className="text-[13px] text-wb-sage-deep underline">
        Read full brief →
      </Link>
    </Card>
  );
}

function TimelineView({ briefs, loading }: { briefs: BriefListItem[]; loading: boolean }) {
  const grouped = useMemo(() => {
    const groups = new Map<string, BriefListItem[]>();
    for (const b of briefs) {
      const key = monthLabel(b.published_at ?? b.generated_at);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(b);
    }
    return Array.from(groups.entries());
  }, [briefs]);

  if (loading) return <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>;
  if (briefs.length === 0) return <Card title="Timeline"><p className="text-sm text-wb-ink2">No briefs yet.</p></Card>;

  return (
    <div className="space-y-6">
      {grouped.map(([month, rows]) => (
        <Card key={month} title={month}>
          <div className="space-y-3">
            {rows.map((b) => (
              <Link
                key={b.brief_id}
                href={`/briefs/${encodeURIComponent(b.brief_id)}`}
                className="block rounded-lg border border-wb-line/60 bg-wb-bg/60 p-3 text-sm hover:bg-wb-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
              >
                <div className="flex items-center gap-3">
                  <span className="w-16 shrink-0 text-[12px] uppercase tracking-wide text-wb-ink2">
                    {new Date(b.published_at ?? b.generated_at).toLocaleDateString(undefined, { day: '2-digit', month: 'short' })}
                  </span>
                  <RiskPill value={b.overall_risk} />
                </div>
                {b.executive_snapshot && (
                  <p className="mt-1.5 text-wb-ink">{excerpt(b.executive_snapshot, 200)}</p>
                )}
              </Link>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

function ExploreView({ briefs, loading }: { briefs: BriefListItem[]; loading: boolean }) {
  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | ApprovalStatus>('all');
  const [showAdvanced, setShowAdvanced] = useState(false);

  const filtered = useMemo(() => {
    return briefs.filter((b) => {
      if (riskFilter !== 'all' && b.overall_risk !== riskFilter) return false;
      if (statusFilter !== 'all' && b.approval_status !== statusFilter) return false;
      if (search.trim()) {
        const haystack = `${b.executive_snapshot ?? ''} ${b.bottom_line ?? ''}`.toLowerCase();
        if (!haystack.includes(search.trim().toLowerCase())) return false;
      }
      return true;
    });
  }, [briefs, search, riskFilter, statusFilter]);

  return (
    <div className="space-y-4">
      <Card title="Search &amp; Filter">
        <div className="flex flex-wrap gap-2.5">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search briefs…"
            className="min-w-[200px] flex-1 rounded-md border border-wb-line bg-wb-bg px-3 py-1.5 text-[13px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          />
          <select
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value)}
            className="rounded-md border border-wb-line bg-wb-bg px-2 py-1.5 text-[13px]"
          >
            <option value="all">All postures</option>
            <option value="RED">Red</option>
            <option value="AMBER">Amber</option>
            <option value="GREEN">Green</option>
            <option value="UNKNOWN">Unknown</option>
          </select>
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="rounded-md border border-wb-line px-3 py-1.5 text-[13px] text-wb-ink2 hover:bg-wb-bg"
          >
            {showAdvanced ? 'Hide' : 'Show'} advanced filters
          </button>
        </div>

        {showAdvanced && (
          <div className="mt-3 border-t border-wb-line pt-3">
            <p className="mb-2 text-[11px] uppercase tracking-wider text-wb-ink2">
              Historical publication state (legacy — every brief since 2026-08-22 auto-publishes)
            </p>
            <div className="flex flex-wrap gap-2">
              {(['all', 'PUBLISHED', 'IN_REVIEW', 'QA_PASSED'] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStatusFilter(s)}
                  aria-pressed={statusFilter === s}
                  className={`rounded-full border px-3 py-1 text-[12px] ${
                    statusFilter === s ? 'border-wb-sage-deep bg-wb-sage-deep text-white' : 'border-wb-line text-wb-ink2'
                  }`}
                >
                  {s === 'all' ? 'All' : STATUS_LABEL[s]}
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      <Card title={`${filtered.length} Brief${filtered.length === 1 ? '' : 's'}`}>
        {loading ? (
          <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-wb-ink2">No briefs match these filters.</p>
        ) : (
          <div className="space-y-3">
            {filtered.map((b) => (
              <Link
                key={b.brief_id}
                href={`/briefs/${encodeURIComponent(b.brief_id)}`}
                className="block rounded-lg border border-wb-line/60 bg-wb-bg/60 p-3 text-sm hover:bg-wb-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <RiskPill value={b.overall_risk} />
                    <span className="text-[10px] uppercase tracking-wider text-wb-ink2">
                      {b.approval_status ? STATUS_LABEL[b.approval_status] : 'Unknown'}
                    </span>
                  </div>
                  <span className="whitespace-nowrap text-[10px] text-wb-ink2/70">
                    {b.published_at
                      ? `Published ${new Date(b.published_at).toLocaleDateString()}`
                      : `Generated ${new Date(b.generated_at).toLocaleDateString()}`}
                  </span>
                </div>
                {b.executive_snapshot && <p className="mt-1.5 text-wb-ink">{excerpt(b.executive_snapshot, 200)}</p>}
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

export default function BriefsPage() {
  const [briefs, setBriefs] = useState<BriefListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('latest');

  useEffect(() => {
    fetch('/api/briefs')
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed to load');
        setBriefs(d.briefs ?? []);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  const latest = briefs[0] ?? null; // API already orders generated_at desc

  return (
    <WorkbenchShell
      title="Briefs"
      eyebrow="Canonical Intelligence Record"
      tagline="USS TJR · HQ's canonical daily synthesis of the intelligence picture — one assessment, multiple delivery formats"
      back={{ href: '/workbenches', label: 'Workbenches' }}
      tabs={<TabBar active={tab} onChange={setTab} />}
    >
      {error && (
        <p className="mb-4 rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>
      )}

      {tab === 'latest' && <LatestView latest={latest} loading={loading} />}
      {tab === 'timeline' && <TimelineView briefs={briefs} loading={loading} />}
      {tab === 'explore' && <ExploreView briefs={briefs} loading={loading} />}
    </WorkbenchShell>
  );
}
