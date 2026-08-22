'use client';

// Knowledge Workbench — unified Memory | Library collection.
//
// Standalone route (outside the (app) group), same wb- design system and
// domain-toggle architecture as the Intelligence Workbench. Reachable from
// /workbenches; not promoted into the LCARS navigation model. The two domains
// are views over organisational decisions and personal documents.

import { Suspense } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { MemoryView } from './_components/MemoryView';

// Library (document cataloguing/review, MSN-0331) pulled back to draft
// 2026-08-22, Captain directive — mid-setup, not fully operational, hidden
// from view until it's ready. Memory is unaffected and stays live; the
// domain-toggle (Memory | Library) is dropped along with it — pointless
// with only one destination — and comes back if/when Library returns.

function Workbench() {
  return (
    <WorkbenchShell title="Knowledge Workbench" eyebrow="Command Memory"
      tagline="USS TJR · Knowledge · Memory · Organisational decisions"
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
