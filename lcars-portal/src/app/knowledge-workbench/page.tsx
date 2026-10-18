'use client';

// Knowledge Workbench — unified Memory | Library collection.
//
// Standalone route (outside the (app) group), same wb- design system and
// domain-toggle architecture as the Intelligence Workbench. Reachable from
// /workbenches; not promoted into the LCARS navigation model. The two domains
// are views over organisational decisions and personal documents.

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { DomainToggle, WorkbenchShell } from '@/components/ui';
import { MemoryView } from './_components/MemoryView';
import { ExerciseLibraryView } from './_components/ExerciseLibraryView';

// Library (document cataloguing/review, MSN-0331) pulled back to draft
// 2026-08-22, Captain directive — mid-setup, not fully operational, hidden
// from view until it's ready. Memory is unaffected and stays live; the
// domain-toggle (Memory | Library) is dropped along with it — pointless
// with only one destination — and comes back if/when Library returns.

const OPERATING_MODEL_HREF = '/knowledge-workbench/operating-model';

type KnowledgeTab = 'memory' | 'exercises';
const TAB_OPTIONS: { key: KnowledgeTab; label: string }[] = [
  { key: 'memory', label: 'Memory' },
  { key: 'exercises', label: 'Exercises' },
];

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  // ?tab=exercises is where the retired /physical-readiness/library redirects.
  const [tab, setTab] = useState<KnowledgeTab>(params.get('tab') === 'exercises' ? 'exercises' : 'memory');
  const changeTab = (next: KnowledgeTab) => {
    setTab(next);
    const url = new URL(window.location.href);
    if (next === 'exercises') url.searchParams.set('tab', 'exercises');
    else url.searchParams.delete('tab');
    window.history.replaceState(null, '', url);
  };

  const operatingModel = (
    // "Real navigation, not a tab" (same treatment as Human Systems'
    // TRENDS/REPORT/WEIGHT buttons) — Operating Model relocated here
    // (Mission 7 deferred-register item 11, closed by Captain direction)
    // from the retired (app)/operating-model orphan page.
    <button
      type="button"
      onClick={() => router.push(OPERATING_MODEL_HREF)}
      className="shrink-0 rounded-md border border-wb-line bg-wb-surface px-3 py-2 text-wb-body font-medium text-wb-ink2 transition hover:border-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep"
    >
      OPERATING MODEL →
    </button>
  );
  const tabsRow = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <DomainToggle value={tab} onChange={changeTab} options={TAB_OPTIONS} ariaLabel="Knowledge views" />
      {operatingModel}
    </div>
  );

  return (
    <WorkbenchShell wide title="Knowledge" eyebrow={tab === 'exercises' ? 'Exercise catalogue' : 'Command Memory'}
      tagline={tab === 'exercises' ? 'TJR HQ · Knowledge · Exercises' : 'TJR HQ · Knowledge · Memory · Organisational decisions'}
      tabs={tabsRow}
      back={{ href: '/workbenches', label: 'Workbenches' }}
      mode="command">
      {tab === 'exercises' ? (
        <ExerciseLibraryView />
      ) : (
        <div className="risk-reference-surface risk-reference-read">
          <div className="risk-reference-kicker">Read / discovery · memory with provenance</div>
          <MemoryView />
        </div>
      )}
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
