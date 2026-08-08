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
 * Scope boundary, deliberate: this board stops at 'approved'. Publishing
 * (ready_to_publish -> published) is the Communications Workbench Pipeline
 * tab's job — see ContentBoard.tsx and the Proofing stage's approved-state
 * copy.
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
      tagline="USS TJR · Content Workbench · Ends at Approved — publishing lives in the Communications Workbench"
      right={right}
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      <CaptureBox onCaptured={refresh} />
      <ContentBoard refreshSignal={refreshSignal} onLoaded={setCounts} />
    </WorkbenchShell>
  );
}
