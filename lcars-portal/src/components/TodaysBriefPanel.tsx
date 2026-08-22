'use client';

// Today's Brief — the executive-summary card the retired Pending
// Intelligence Briefs panel left a gap for (2026-08-22, Captain's direct
// request: "some form of executive view being brought from briefs into my
// captains chair"). That panel showed a stale review QUEUE (dead now that
// briefs auto-publish — see intelligence/persistence/intelligence_store.py
// save_brief()); this shows today's actual synthesized digest CONTENT —
// executive_snapshot + risk + themes from the real daily brief, not a
// decision-pending list. Reuses /api/briefs (same data /briefs itself
// reads) rather than a new endpoint.

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { RiskPill } from '@/components/ui';
import { WorkbenchPanel } from './WorkbenchPanel';

interface Brief {
  brief_id: string;
  generated_at: string;
  published_at: string | null;
  overall_risk: string | null;
  approval_status: string | null;
  executive_snapshot: string | null;
}

function isToday(dateStr: string | null): boolean {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

export function TodaysBriefPanel() {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/briefs')
      .then((r) => {
        if (!r.ok) throw new Error(`briefs unavailable (${r.status})`);
        return r.json();
      })
      .then((d) => {
        const briefs: Brief[] = d?.briefs ?? [];
        const today = briefs.find(
          (b) => b.approval_status === 'PUBLISHED' && isToday(b.published_at ?? b.generated_at),
        );
        setBrief(today ?? null);
        setError(null);
      })
      .catch((e) => {
        console.error('[TodaysBriefPanel] load failed:', e);
        setError(e instanceof Error ? e.message : 'Failed to load');
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <WorkbenchPanel
      title="Executive Brief"
      eyebrow="Today's Synthesized Digest · from /briefs"
      actions={
        <Link href="/briefs" className="text-xs font-medium text-wb-sage-deep hover:underline">
          All briefs →
        </Link>
      }
    >
      {loading ? (
        <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>
      ) : error ? (
        <p className="text-sm text-wb-crit-on">Failed to load today's brief: {error}</p>
      ) : !brief ? (
        <p className="text-sm text-wb-ink2">
          No brief generated yet today — the daily job runs at 06:30 AEST, or trigger one on
          demand via the XO bot's /brief command.
        </p>
      ) : (
        <Link
          href={`/intelligence-workbench/brief/${encodeURIComponent(brief.brief_id)}`}
          className="block rounded-lg border border-wb-line/60 bg-wb-bg/60 p-3 text-sm hover:bg-wb-bg"
        >
          <div className="mb-1.5 flex items-center gap-2">
            <RiskPill value={brief.overall_risk} />
            <span className="text-[10px] uppercase tracking-wider text-wb-ink2">
              {new Date(brief.published_at ?? brief.generated_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          </div>
          {brief.executive_snapshot && <p className="text-wb-ink">{brief.executive_snapshot}</p>}
        </Link>
      )}
    </WorkbenchPanel>
  );
}
