'use client';

/**
 * Content Workbench (COMMS-002) — Capture -> Research -> Content Prep -> Proofing.
 *
 * A new, standalone workbench, additive to the existing Communications
 * Workbench and Capture Workbench (neither of those is modified by this
 * route). It reuses comms_content/content_signals under the hood via
 * migrations 0095/0096 (purely additive columns + one new revisions table)
 * and the same canonical POST /api/comms/[id]/advance for every status
 * transition it makes.
 *
 * Carries the flow end to end through publish submission: the Proofing
 * column now surfaces "Confirm Ready to Publish" and "Submit for Publish
 * Approval" (see ContentBoard.tsx's ProofingStageBody) instead of handing
 * off to the Communications Workbench. mark_published still only queues a
 * governed proposal — the Captain approves the actual publish in Decide,
 * same as always.
 */

import { useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { CaptureBox } from './_components/CaptureBox';
import { ContentBoard } from './_components/ContentBoard';
import type { Stage } from './_components/shared';

export default function ContentWorkbenchPage() {
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
      eyebrow="Capture → Research → Content Prep → Proofing"
      homeHref="/content-workbench"
      homeAriaLabel="Content Workbench home"
      tagline="USS TJR · Content Workbench · Capture to publish submission, one governed pipeline"
      right={right}
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      <CaptureBox onCaptured={refresh} />
      <ContentBoard refreshSignal={refreshSignal} onLoaded={setCounts} />
    </WorkbenchShell>
  );
}
