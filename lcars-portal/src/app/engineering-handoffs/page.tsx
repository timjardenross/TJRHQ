'use client';

/**
 * Engineering Handoffs — a Captain-facing view of approved engineering
 * handoffs (core/coordination/engineering_handoff_reader.py's own
 * already-computed data), added 2026-09-06 to close a real gap: this data
 * previously only ever fed Number One's advisory work queue, with no
 * dedicated page anywhere in the platform. The Captain had to leave for
 * GitHub.com with nothing but a bare handoff ID to find the right PR.
 *
 * Named distinctly from /engineering-queue, which is a deliberate redirect
 * stub to /engineering for a DIFFERENT, removed feature (the old
 * build-request inbox detail view, dropped 2026-08-22 per the Captain's
 * own request — see that route's page.tsx) — different data (build
 * requests, not engineering handoffs), coincidentally similar name only.
 *
 * Read-only, deliberately no in-platform approve/merge action — every
 * "Open draft PR" link takes the Captain to GitHub's own review view, so
 * the diff always gets opened and read before anything merges. Adding a
 * same-tap approve+merge here was assessed and explicitly deferred
 * (Chief Engineer review, 2026-09-06): it would touch shared GitHub-write
 * infrastructure used by multiple services and risks quietly removing the
 * one safety property this whole pipeline depends on — a human actually
 * opening the diff before it lands on main.
 */

import { useEffect, useState } from 'react';
import { Badge, Card, WorkbenchShell } from '@/components/ui';
import type { BadgeStatus } from '@/components/ui';

interface HandoffMetadata {
  engineering_status: string;
  batch_status: string;
  pr_url: string;
  batch_artifact: string;
  handoff_file: string;
  approved_at: string;
}

interface Handoff {
  mission_id: string;
  title: string;
  priority: string;
  next_action: string;
  metadata: HandoffMetadata;
}

const STATUS_BADGE: Record<string, BadgeStatus> = {
  'Awaiting Review': 'warning',
  'In Progress': 'info',
  'Assigned': 'info',
  'Pending Triage': 'neutral',
};

const STATUS_ORDER = ['Awaiting Review', 'In Progress', 'Assigned', 'Pending Triage'];

function displayTitle(title: string): string {
  return title.replace(/^\[ENG-HANDOFF\]\s*/, '');
}

function HandoffCard({ handoff }: { handoff: Handoff }) {
  const { metadata } = handoff;
  const badgeStatus = STATUS_BADGE[metadata.engineering_status] ?? 'neutral';

  return (
    <div className="rounded-lg border border-wb-line bg-wb-bg p-4">
      <div className="mb-2 flex items-start justify-between gap-3">
        <h3 className="font-serif text-[15px] text-wb-ink">{displayTitle(handoff.title)}</h3>
        <span className="shrink-0 rounded-md border border-wb-line px-2 py-0.5 font-mono text-[11px] text-wb-ink2">
          {handoff.priority}
        </span>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge status={badgeStatus}>{metadata.engineering_status}</Badge>
        <span className="text-[11px] uppercase tracking-wide text-wb-ink2">
          batch: {metadata.batch_status}
        </span>
      </div>
      <p className="mb-3 text-[12px] text-wb-ink2">{handoff.next_action}</p>
      {metadata.pr_url ? (
        <a
          href={metadata.pr_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-md border border-wb-sage-deep bg-wb-sage-deep/10
            px-3 py-1.5 text-[12px] font-semibold text-wb-sage-deep transition-colors hover:bg-wb-sage-deep/20
            focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        >
          Open draft PR →
        </a>
      ) : metadata.batch_artifact ? (
        <p className="text-[11px] italic text-wb-ink2">
          No PR yet — review artifact: {metadata.batch_artifact}
        </p>
      ) : (
        <p className="text-[11px] italic text-wb-ink2">No PR or artifact yet.</p>
      )}
    </div>
  );
}

export default function EngineeringHandoffsPage() {
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch('/api/engineering-handoffs', { cache: 'no-store' });
        const body = await res.json();
        if (!res.ok) throw new Error(body?.error || 'bad upstream response');
        setHandoffs(body.handoffs ?? []);
      } catch (e) {
        console.error('engineering handoffs fetch failed', e);
        setLoadError('Couldn’t load engineering handoffs right now.');
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, []);

  const byStatus: Record<string, number> = {};
  handoffs.forEach(h => {
    const s = h.metadata.engineering_status;
    byStatus[s] = (byStatus[s] ?? 0) + 1;
  });

  const sorted = [...handoffs].sort(
    (a, b) => STATUS_ORDER.indexOf(a.metadata.engineering_status) - STATUS_ORDER.indexOf(b.metadata.engineering_status)
  );

  return (
    <WorkbenchShell
      title="Engineering Handoffs"
      eyebrow="Number One · Engineering Handoffs"
      tagline="Approved engineering handoffs awaiting triage, delivery, or your review — with a direct link to every draft PR"
    >
      <div className="flex flex-col gap-4">
        <Card>
          {isLoading ? (
            <p className="text-[13px] italic text-wb-ink2">Loading engineering handoffs…</p>
          ) : loadError ? (
            <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
              <p className="text-[13px] font-semibold text-wb-crit-on">{loadError}</p>
              <p className="mt-1 text-[12px] text-wb-ink2">
                This is a load failure, not an empty queue. Retry shortly.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {STATUS_ORDER.map(s => (
                <div key={s} className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
                  <p className="text-2xl font-bold text-wb-ink">{byStatus[s] ?? 0}</p>
                  <p className="text-[10px] uppercase tracking-wider text-wb-ink2">{s}</p>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div className="mb-3">
            <h2 className="font-serif text-lg text-wb-ink">Outstanding Handoffs</h2>
            <p className="text-[11px] uppercase tracking-wide text-wb-ink2">
              Most-needs-attention first
            </p>
          </div>
          {isLoading ? (
            <p className="text-[13px] italic text-wb-ink2">Loading engineering handoffs…</p>
          ) : loadError ? (
            <p className="text-[13px] text-wb-crit-on">{loadError} No list to show.</p>
          ) : sorted.length === 0 ? (
            <p className="text-[13px] italic text-wb-ink2">
              Nothing needs your attention — no outstanding engineering handoffs.
            </p>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {sorted.map(h => (
                <HandoffCard key={h.mission_id} handoff={h} />
              ))}
            </div>
          )}
        </Card>
      </div>
    </WorkbenchShell>
  );
}
