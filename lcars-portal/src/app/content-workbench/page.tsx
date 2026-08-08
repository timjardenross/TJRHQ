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
 * items + export) had no equivalent here, so a Pipeline/Portfolio Tabs
 * split was added — same shape as comms-workbench's own tab bar — reading
 * PortfolioTab.tsx, a new but intentionally duplicated component (not an
 * import from comms-workbench/_components, per the design-system barrel
 * rule). Nothing on comms-workbench itself changed; its route still works,
 * it's just not the only place to reach this content anymore.
 */

import { useState } from 'react';
import { Tabs, WorkbenchShell } from '@/components/ui';
import { CaptureBox } from './_components/CaptureBox';
import { ContentBoard } from './_components/ContentBoard';
import { PortfolioTab } from './_components/PortfolioTab';
import type { Stage } from './_components/shared';

type Tab = 'pipeline' | 'portfolio';

const TABS: { key: Tab; label: string }[] = [
  { key: 'pipeline', label: 'Pipeline' },
  { key: 'portfolio', label: 'Portfolio' },
];

export default function ContentWorkbenchPage() {
  const [tab, setTab] = useState<Tab>('pipeline');
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [counts, setCounts] = useState<Record<Stage, number> | null>(null);
  const refresh = () => setRefreshSignal((n) => n + 1);

  const right = counts ? (
    <span className="text-[11px] text-wb-ink2">
      {counts.capture + counts.research + counts.content_prep + counts.proofing} active
    </span>
  ) : null;

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
      <Tabs tabs={TABS} active={tab} onChange={setTab} ariaLabel="Content Workbench sections" />

      <div className="mt-4">
        {tab === 'pipeline' && (
          <>
            <CaptureBox onCaptured={refresh} />
            <ContentBoard refreshSignal={refreshSignal} onLoaded={setCounts} />
          </>
        )}
        {tab === 'portfolio' && <PortfolioTab />}
      </div>
    </WorkbenchShell>
  );
}
