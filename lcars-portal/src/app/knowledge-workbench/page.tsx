'use client';

// Knowledge Workbench — unified Memory | Library collection.
//
// Standalone route (outside the (app) group), same wb- design system and
// domain-toggle architecture as the Intelligence Workbench. Reachable from
// /workbenches; not promoted into the LCARS navigation model. The two domains
// are views over organisational decisions and personal documents.

import { Suspense } from 'react';
import { useRouter } from 'next/navigation';
import { WorkbenchShell } from '@/components/ui';
import { MemoryView } from './_components/MemoryView';

// Library (document cataloguing/review, MSN-0331) pulled back to draft
// 2026-08-22, Captain directive — mid-setup, not fully operational, hidden
// from view until it's ready. Memory is unaffected and stays live; the
// domain-toggle (Memory | Library) is dropped along with it — pointless
// with only one destination — and comes back if/when Library returns.

const OPERATING_MODEL_HREF = '/knowledge-workbench/operating-model';

function Workbench() {
  const router = useRouter();

  const tabsRow = (
    // "Real navigation, not a tab" (same treatment as Human Systems'
    // TRENDS/REPORT/WEIGHT buttons) — Operating Model relocated here
    // (Mission 7 deferred-register item 11, closed by Captain direction)
    // from the retired (app)/operating-model orphan page.
    <button
      type="button"
      onClick={() => router.push(OPERATING_MODEL_HREF)}
      className="shrink-0 rounded-md border border-wb-line bg-wb-surface px-3 py-2 text-[13px] font-medium text-wb-ink2 transition hover:border-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep"
    >
      OPERATING MODEL →
    </button>
  );

  return (
    <WorkbenchShell wide title="Knowledge Workbench" eyebrow="Command Memory"
      tagline="USS TJR · Knowledge · Memory · Organisational decisions"
      tabs={tabsRow}
      back={{ href: '/workbenches', label: 'Workbenches' }}>
      <MemoryView />
    </WorkbenchShell>
  );
}

export default function KnowledgeWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
