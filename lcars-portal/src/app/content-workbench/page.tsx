'use client';

/**
 * Content Workbench (COMMS-002) — Capture -> Research -> Content Prep -> Proofing -> Portfolio.
 *
 * A new, standalone workbench, additive to the existing Communications
 * Workbench and Capture Workbench (neither of those is modified by this
 * route). It reuses comms_content/content_signals under the hood via
 * migrations 0095/0096/0185 (purely additive columns + one new revisions
 * table) and the same canonical POST /api/comms/[id]/advance for every
 * status transition it makes.
 *
 * MSN-0363 (single-person AI content desk uplift): re-anchored around
 * Today / Pipeline / Library instead of always landing on the 4-column
 * board. Today answers "what needs me?" (brief §5); Pipeline now defaults
 * to a priority Queue with Board as a secondary toggle (brief §18);
 * Portfolio is renamed Library with search/filter/export unchanged plus a
 * new Reuse Idea action (brief §19). Selecting any item anywhere opens the
 * shared Content Studio (brief §9) instead of the old per-column Modal —
 * the legacy Board's own Modal-per-card interaction is left exactly as it
 * was (unchanged code path) for anyone who lands there directly.
 *
 * Capture is no longer a permanently-dominant box (brief §6): it's now a
 * "+ Capture Idea" trigger (QuickCaptureModal) shown on Today and Pipeline,
 * wrapping the same unchanged CaptureBox/contentScoring.ts pipeline.
 *
 * 2026-08: Communications Workbench was delisted from /workbenches (see
 * workbenches/page.tsx) in favour of this one. mark_published still only
 * queues a governed proposal — the Captain approves the actual publish in
 * Decide, same as always.
 *
 * 2026-08 follow-up (workbench fault-finding audit): uses `DomainToggle`,
 * the real WAI-ARIA tablist every other *-workbench page uses, with
 * URL-sync (?tab=) matching human-systems-workbench's pattern.
 *
 * MSN-0363 isolation note: this route and everything under
 * content-workbench/_components/ and api/content-workbench/ is this
 * mission's own touch surface. WorkbenchShell/DomainToggle (imported
 * below) are consumed via their existing interface only — not forked,
 * not modified — per the concurrent adaptive-themes-workbench-redesign
 * session's ownership of shared shell/theme components.
 */

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { DomainToggle, WorkbenchShell } from '@/components/ui';
import { QuickCaptureModal } from './_components/QuickCaptureModal';
import { TodayView } from './_components/TodayView';
import { QueueView } from './_components/QueueView';
import { ContentBoard } from './_components/ContentBoard';
import { ContentStudioById } from './_components/ContentStudio';
import { PortfolioTab } from './_components/PortfolioTab';

type Tab = 'today' | 'pipeline' | 'library';
type PipelineView = 'queue' | 'board';

const TAB_OPTIONS: { key: Tab; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: 'pipeline', label: 'Pipeline' },
  { key: 'library', label: 'Library' },
];

function isTab(v: string | null): v is Tab {
  return v === 'today' || v === 'pipeline' || v === 'library';
}

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get('tab');
  const [tab, setTabState] = useState<Tab>(isTab(initial) ? initial : 'today');
  const [pipelineView, setPipelineView] = useState<PipelineView>('queue');
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [selectedContentId, setSelectedContentId] = useState<string | null>(null);
  const refresh = () => setRefreshSignal((n) => n + 1);

  const setTab = (t: Tab) => {
    setTabState(t);
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('tab', t);
    router.replace(`/content-workbench?${sp.toString()}`, { scroll: false });
  };

  function openStudio(contentId: string) {
    setSelectedContentId(contentId);
  }

  function closeStudio() {
    setSelectedContentId(null);
    refresh();
  }

  const captureBar = (
    <QuickCaptureModal onCaptured={refresh} onDevelop={openStudio} />
  );

  return (
    <WorkbenchShell
      title="Content Workbench"
      eyebrow="Your personal AI-assisted content desk"
      tagline="USS TJR · Content Workbench · Capture to publish, AI prepares, you decide"
      right={!selectedContentId ? captureBar : null}
      tabs={!selectedContentId ? (
        <DomainToggle value={tab} onChange={setTab} options={TAB_OPTIONS} ariaLabel="Content Workbench sections" />
      ) : undefined}
      back={{ href: '/workbenches', label: 'Workbenches' }}
      wide
    >
      {selectedContentId ? (
        <ContentStudioById contentId={selectedContentId} onChanged={refresh} onClose={closeStudio} />
      ) : (
        <>
          {tab === 'today' && (
            <TodayView refreshSignal={refreshSignal} onOpenStudio={openStudio} onOpenPipeline={() => setTab('pipeline')} />
          )}
          {tab === 'pipeline' && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPipelineView('queue')}
                  className={`rounded-full px-3 py-1 text-[12px] font-medium ${pipelineView === 'queue' ? 'bg-wb-sage-deep text-white' : 'border border-wb-line text-wb-ink2'}`}
                >
                  Queue
                </button>
                <button
                  type="button"
                  onClick={() => setPipelineView('board')}
                  className={`rounded-full px-3 py-1 text-[12px] font-medium ${pipelineView === 'board' ? 'bg-wb-sage-deep text-white' : 'border border-wb-line text-wb-ink2'}`}
                >
                  Board
                </button>
              </div>
              {pipelineView === 'queue' && <QueueView refreshSignal={refreshSignal} onOpenStudio={openStudio} />}
              {pipelineView === 'board' && <ContentBoard refreshSignal={refreshSignal} onLoaded={() => {}} />}
            </div>
          )}
          {tab === 'library' && <PortfolioTab />}
        </>
      )}
    </WorkbenchShell>
  );
}

export default function ContentWorkbenchPage() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
