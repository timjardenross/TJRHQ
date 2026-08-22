'use client';

// Briefs Workbench — the archive/management view intelligence_briefs never
// had. Previously the only way to reach any brief was a hand-typed
// /intelligence-workbench/brief/[id] URL, or the Pending Briefs widget on
// Captain's Chair (which only shows the not-yet-PUBLISHED ones). Briefs
// synthesize across domains, not just OSINT, so this is its own top-level
// workbench rather than a tab under intelligence-workbench. Reuses the
// existing detail page — this is a list only.

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { Card, RiskPill, WorkbenchShell } from '@/components/ui';

type ApprovalStatus = 'IN_REVIEW' | 'QA_PASSED' | 'PUBLISHED';
type Filter = 'all' | ApprovalStatus;

interface Brief {
  brief_id: string;
  generated_at: string;
  published_at: string | null;
  period_start: string | null;
  period_end: string | null;
  overall_risk: string | null;
  approval_status: ApprovalStatus | null;
  executive_snapshot: string | null;
}

const STATUS_LABEL: Record<ApprovalStatus, string> = {
  IN_REVIEW: 'In Review',
  QA_PASSED: 'QA Passed',
  PUBLISHED: 'Published',
};

// 2026-08-22: single-user platform, briefs now auto-publish at generation
// time (intelligence/persistence/intelligence_store.py:save_brief()) — the
// IN_REVIEW/QA_PASSED states are pre-2026-08-22 history, not an active queue
// anyone works through. Default view is Published; the others stay
// selectable for that history, not because anything new lands there.
const FILTERS: { key: Filter; label: string }[] = [
  { key: 'PUBLISHED', label: 'Published' },
  { key: 'all', label: 'All' },
  { key: 'IN_REVIEW', label: 'In Review (legacy)' },
  { key: 'QA_PASSED', label: 'Awaiting Publish (legacy)' },
];

export default function BriefsPage() {
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('PUBLISHED');

  useEffect(() => {
    fetch('/api/briefs')
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed to load');
        setBriefs(d.briefs ?? []);
        setCounts(d.counts ?? {});
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  const visible = useMemo(
    () => (filter === 'all' ? briefs : briefs.filter((b) => b.approval_status === filter)),
    [briefs, filter],
  );

  return (
    <WorkbenchShell
      title="Briefs"
      eyebrow="Intelligence Brief Archive"
      tagline="USS TJR · Every synthesized brief, across every domain — not scoped to one workbench"
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      {error && (
        <p className="mb-4 rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">{error}</p>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              filter === f.key
                ? 'border-wb-sage-deep bg-wb-sage-deep text-white'
                : 'border-wb-line text-wb-ink2 hover:bg-wb-bg'
            }`}
          >
            {f.label}
            {f.key !== 'all' && counts[f.key] != null ? ` (${counts[f.key]})` : ''}
          </button>
        ))}
      </div>

      <Card title={`${visible.length} Brief${visible.length === 1 ? '' : 's'}`}>
        {loading ? (
          <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>
        ) : visible.length === 0 ? (
          <p className="text-sm text-wb-ink2">No briefs in this state.</p>
        ) : (
          <div className="space-y-3">
            {visible.map((b) => (
              <Link
                key={b.brief_id}
                href={`/intelligence-workbench/brief/${encodeURIComponent(b.brief_id)}`}
                className="block rounded-lg border border-wb-line/60 bg-wb-bg/60 p-3 text-sm hover:bg-wb-bg"
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
                {b.executive_snapshot && (
                  <p className="mt-1.5 text-wb-ink">
                    {b.executive_snapshot.slice(0, 200)}
                    {b.executive_snapshot.length > 200 ? '…' : ''}
                  </p>
                )}
              </Link>
            ))}
          </div>
        )}
      </Card>
    </WorkbenchShell>
  );
}
