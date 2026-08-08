'use client';

/**
 * Content Workbench (COMMS-002) — Capture -> Research -> Content Prep -> Proofing -> Portfolio.
 *
 * A new, standalone workbench, additive to the existing Communications
 * Workbench and Capture Workbench (neither of those is modified by this
 * route). It reuses comms_content/content_signals under the hood via
 * migrations 0095/0096 (purely additive columns + one new revisions table)
 * and the same canonical POST /api/comms/[id]/advance for every status
 * transition it makes.
 *
 * Carries the flow end to end through publish submission: the Proofing
 * column surfaces "Confirm Ready to Publish" and "Submit for Publish
 * Approval" (see ContentBoard.tsx's ProofingStageBody) instead of handing
 * off to the Communications Workbench. mark_published still only queues a
 * governed proposal — the Captain approves the actual publish in Decide,
 * same as always.
 *
 * 2026-08: Communications Workbench was delisted from /workbenches (see
 * workbenches/page.tsx) in favour of this one. Its Portfolio tab (published
 * items + export) had no equivalent here, so a Pipeline/Portfolio split
 * was added — reading PortfolioTab.tsx, a new but intentionally duplicated
 * component (not an import from comms-workbench/_components, per the
 * design-system barrel rule). Nothing on comms-workbench itself changed;
 * its route still works, it's just not the only place to reach this
 * content anymore.
 *
 * 2026-08 follow-up (workbench fault-finding audit): originally used the
 * `Tabs` component (plain buttons, `aria-current="page"` — semantically
 * wrong for tab selection, no arrow-key nav). Switched to `DomainToggle`,
 * the real WAI-ARIA tablist every other *-workbench page uses (see its
 * own header comment for why it exists) — this was the one page still on
 * the old inaccessible pattern DomainToggle's consolidation was meant to
 * retire. Also added URL-sync (?tab=) matching human-systems-workbench's
 * pattern — previously a refresh on Portfolio silently dropped back to
 * Pipeline.
 */

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { DomainToggle, WorkbenchShell } from '@/components/ui';
import { CaptureBox } from './_components/CaptureBox';
import { ContentBoard } from './_components/ContentBoard';
import { PortfolioTab } from './_components/PortfolioTab';
import type { Stage } from './_components/shared';

type Tab = 'pipeline' | 'portfolio';

const TAB_OPTIONS: { key: Tab; label: string }[] = [
  { key: 'pipeline', label: 'Pipeline' },
  { key: 'portfolio', label: 'Portfolio' },
];

function isTab(v: string | null): v is Tab {
  return v === 'pipeline' || v === 'portfolio';
}

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get('tab');
  const [tab, setTabState] = useState<Tab>(isTab(initial) ? initial : 'pipeline');
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [counts, setCounts] = useState<Record<Stage, number> | null>(null);
  const refresh = () => setRefreshSignal((n) => n + 1);

  const setTab = (t: Tab) => {
    setTabState(t);
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('tab', t);
    router.replace(`/content-workbench?${sp.toString()}`, { scroll: false });
  };

  const right = (
    <div className="flex items-center gap-3">
      {counts && (
        <span className="hidden text-[11px] text-wb-ink2 sm:inline">
          {counts.capture + counts.research + counts.content_prep + counts.proofing} active
        </span>
      )}
      <DomainToggle value={tab} onChange={setTab} options={TAB_OPTIONS} ariaLabel="Content Workbench sections" />
    </div>
  );

  return (
    <WorkbenchShell
      title="Content Workbench"
      eyebrow="Capture → Research → Content Prep → Proofing → Portfolio"
      homeHref="/content-workbench"
      homeAriaLabel="Content Workbench home"
      tagline="USS TJR · Content Workbench · Capture to publish submission, one governed pipeline"
      right={right}
      back={{ href: '/workbenches', label: 'Workbenches' }}
      wide
    >
      {tab === 'pipeline' && (
        <>
          <CaptureBox onCaptured={refresh} />
          <ContentBoard refreshSignal={refreshSignal} onLoaded={setCounts} />
        </>
      )}
      {tab === 'portfolio' && <PortfolioTab />}
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
