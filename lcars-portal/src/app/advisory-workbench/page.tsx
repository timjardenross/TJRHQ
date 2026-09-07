'use client';

// Advisory — Think / Perspectives / Outcomes on the wb- design system.
//
// Standalone route (outside the (app) group), same Shell + domain-toggle
// architecture as the Human Systems / Intelligence Workbenches. Reachable
// from /workbenches and (Captain decision 2026-07-12) kept first-class in
// the main nav via a repoint of the old /advisory-council references.
//
// Unlike Human Systems, advisory is request/response — this page decides
// which view is shown; each view calls the existing advisory endpoints
// unchanged. No new GET route, no realtime, no live indicator (would be
// dishonest here).
//
// 2026-09 redesign: four competing interaction models (Ask / Talk to
// Someone / Panel of Voices / Close Out) collapsed into three simple jobs —
// Think ("help me reason through something"), Perspectives ("show me
// another way to see it"), Outcomes ("learn from what actually happened").
// The underlying engine (specialist routing → challenge → evidence →
// synthesis → recommendation → decision → outcome → calibration) is
// unchanged; only what's exposed up front changed. See types.ts's
// normalizeDomain for the back-compat mapping from the old domain keys.

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { WorkbenchShell, DomainToggle } from '@/components/ui';
import { ThinkView } from './_components/ThinkView';
import { PerspectivesView } from './_components/PerspectivesView';
import { OutcomesView } from './_components/OutcomesView';
import { ProactiveBanner } from './_components/ProactiveBanner';
import { EYEBROW, normalizeDomain, type Domain } from './_components/types';

const DOMAIN_OPTIONS: { key: Domain; label: string }[] = [
  { key: 'think', label: 'Think' },
  { key: 'perspectives', label: 'Perspectives' },
  { key: 'outcomes', label: 'Outcomes' },
];

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();

  // Back-compat: the legacy page used ?tab=, and the legacy domain keys
  // were 'board'/'consult'/'loops' — normalizeDomain maps all of them onto
  // the current three. A deep-linked investigation lands on Think.
  const investigationType = params.get('investigationType') ?? undefined;
  const investigationReason = params.get('investigationReason') ?? undefined;
  const initial = params.get('domain') ?? params.get('tab');
  const [domain, setDomain] = useState<Domain>(normalizeDomain(initial));
  const [prefill, setPrefill] = useState<{ text: string; nonce: number } | null>(null);

  const changeDomain = (d: Domain) => {
    setDomain(d);
    // Keep the URL shareable/bookmarkable without a full navigation.
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.delete('tab');
    sp.set('domain', d);
    router.replace(`/advisory-workbench?${sp.toString()}`, { scroll: false });
  };

  const thinkItThrough = (text: string) => {
    setPrefill((prev) => ({ text, nonce: (prev?.nonce ?? 0) + 1 }));
    changeDomain('think');
  };

  return (
    <WorkbenchShell wide
      title="Advisory"
      eyebrow={EYEBROW[domain]}
      tagline="USS TJR · Advisory · Think through a decision, challenge your assumptions, and get another perspective · Advisory only. You decide what happens next."
      tabs={<DomainToggle value={domain} onChange={changeDomain} options={DOMAIN_OPTIONS} ariaLabel="Advisory mode" />}
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      <div className="mb-4">
        <ProactiveBanner onThinkItThrough={thinkItThrough} />
      </div>
      {domain === 'think' && (
        <ThinkView investigationType={investigationType} investigationReason={investigationReason} prefill={prefill} />
      )}
      {domain === 'perspectives' && <PerspectivesView />}
      {domain === 'outcomes' && <OutcomesView />}
    </WorkbenchShell>
  );
}

export default function AdvisoryWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
