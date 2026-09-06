'use client';

// Domain boundary (2026-08-29, docs/UI-Layer-Debt-Handoff-2026-08-29.md
// Finding 3, resolved): Health OSINT is external, population-level research
// intelligence (health_signals/health_signal_corroboration — clinical
// trials, studies, source reliability, safety escalation). It has zero
// overlap with Human Systems Workbench (/human-systems-workbench), which
// is first-party personal recovery/readiness telemetry
// (capacity_checkins et al.) — disjoint tables, disjoint user tasks.
// Kept as separate workbenches by design, not by drift; no merge needed.
//
// Phase 2 "Three-Workbench Simplification" uplift (2026-09-06): re-anchored
// from a 4-tab analyst console (Confidence Matrix / Intelligence Summary /
// Source Trust Network / Threat Assessment) around Today / My Evidence /
// Library for a single-user living evidence system, mirroring the
// Content Workbench Today/Studio/Pipeline/Library uplift (MSN-0363,
// f2ee2cb4). The original 4-tab console is demoted, not deleted — it lives
// in _components/LegacyDetails.tsx behind the secondary "Details" control.
// The separate /health-osint-curation workbench is folded into a small
// "Needs Your Review" card on Today (ambiguous cases only); the standalone
// route stays live for bulk/manual inspection.
//
// disposition/evidence_contribution/safety_relevance (migration 0186, until
// now shadow-mode per the OSINT Ingestion Quality Mission) are read and
// gated on live here for the first time — see api/health-osint/today's own
// comment for the exact live-data coverage this was checked against before
// building on it.

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { DomainToggle, WorkbenchShell, Button } from '@/components/ui';
import { TodayView } from './_components/TodayView';
import { MyEvidenceView } from './_components/MyEvidenceView';
import { TopicDetail } from './_components/TopicDetail';
import { LibraryView } from './_components/LibraryView';
import { LegacyDetails } from './_components/LegacyDetails';

type Tab = 'today' | 'my-evidence' | 'library';

const TAB_OPTIONS: { key: Tab; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: 'my-evidence', label: 'My Evidence' },
  { key: 'library', label: 'Library' },
];

function isTab(v: string | null): v is Tab {
  return v === 'today' || v === 'my-evidence' || v === 'library';
}

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get('tab');
  const [tab, setTabState] = useState<Tab>(isTab(initial) ? initial : 'today');
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  const setTab = (t: Tab) => {
    setTabState(t);
    setSelectedTopic(null);
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('tab', t);
    router.replace(`/health-osint?${sp.toString()}`, { scroll: false });
  };

  return (
    <WorkbenchShell
      title="Health OSINT"
      eyebrow="Your Personal Health Evidence Desk"
      tagline="USS TJR · What's worth knowing, your evidence position, the full record"
      tabs={!showDetails ? (
        <DomainToggle value={tab} onChange={(v) => setTab(v as Tab)} options={TAB_OPTIONS} ariaLabel="Health OSINT sections" />
      ) : undefined}
      back={{ href: '/workbenches', label: 'Workbenches' }}
      right={
        <Button variant="secondary" size="sm" onClick={() => setShowDetails((v) => !v)}>
          {showDetails ? '← Back' : 'Details (Technical view)'}
        </Button>
      }
    >
      {showDetails ? (
        <LegacyDetails />
      ) : (
        <>
          {tab === 'today' && <TodayView />}
          {tab === 'my-evidence' && (
            selectedTopic ? (
              <TopicDetail topicKey={selectedTopic} onBack={() => setSelectedTopic(null)} />
            ) : (
              <MyEvidenceView onOpenTopic={setSelectedTopic} />
            )
          )}
          {tab === 'library' && <LibraryView />}
        </>
      )}
    </WorkbenchShell>
  );
}

export default function HealthOSINTWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
