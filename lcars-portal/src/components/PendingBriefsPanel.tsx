'use client';

// Captain's Chair — surfaces intelligence briefs waiting on human review
// (IN_REVIEW) or waiting on the final publish decision (QA_PASSED). The
// only place that ever listed these and linked to the review UI was the
// old /home "needs attention" page, retired in the 2026-08 nav rewrite
// without this content migrating anywhere — so briefs piled up at
// QA_PASSED with no discoverable path to /intelligence-workbench/brief/[id],
// and "Latest Published Brief" went stale. This restores just that link,
// reusing /api/home/needs-attention rather than duplicating its query.

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { WorkbenchPanel } from './WorkbenchPanel';

interface PendingBrief {
  brief_id: string;
  overall_risk: string | null;
  approval_status: string | null;
  generated_at: string;
  executive_snapshot: string | null;
}

const RISK_DOT: Record<string, string> = {
  RED: 'bg-state-crit',
  AMBER: 'bg-state-warn',
  GREEN: 'bg-state-ok',
};

const STATUS_LABEL: Record<string, string> = {
  IN_REVIEW: 'Awaiting QA',
  QA_PASSED: 'Awaiting Publish',
};

export function PendingBriefsPanel() {
  const [briefs, setBriefs] = useState<PendingBrief[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/home/needs-attention')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setBriefs(d?.pendingBriefs ?? []))
      .catch(() => setBriefs([]))
      .finally(() => setLoading(false));
  }, []);

  if (!loading && briefs.length === 0) return null;

  return (
    <WorkbenchPanel
      title="Pending Intelligence Briefs"
      eyebrow="Awaiting review or publish decision"
      actions={
        <Link href="/briefs" className="text-xs font-medium text-wb-sage-deep hover:underline">
          All briefs →
        </Link>
      }
    >
      {loading ? (
        <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>
      ) : (
        <div className="flex flex-col gap-2">
          {briefs.map((b) => (
            <Link
              key={b.brief_id}
              href={`/intelligence-workbench/brief/${encodeURIComponent(b.brief_id)}`}
              className="flex items-center justify-between gap-3 rounded-lg border border-wb-line/60 bg-wb-bg/60 p-3 text-sm hover:bg-wb-bg"
            >
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${RISK_DOT[b.overall_risk ?? ''] ?? 'bg-wb-ink2'}`}
                  aria-hidden
                />
                <span className="text-wb-ink">
                  {b.executive_snapshot ? b.executive_snapshot.slice(0, 90) : b.brief_id}
                  {(b.executive_snapshot?.length ?? 0) > 90 ? '…' : ''}
                </span>
              </div>
              <span className="whitespace-nowrap text-[10px] uppercase tracking-wider text-wb-ink2">
                {STATUS_LABEL[b.approval_status ?? ''] ?? b.approval_status} · {new Date(b.generated_at).toLocaleDateString()}
              </span>
            </Link>
          ))}
        </div>
      )}
    </WorkbenchPanel>
  );
}
