'use client';

// Advisory Workbench — Ask / Talk to Someone / Panel of Voices on the wb-
// design system.
//
// Standalone route (outside the (app) group), same Shell + domain-toggle
// architecture as the Human Systems / Intelligence Workbenches. Reachable from
// /workbenches and (Captain decision 2026-07-12) kept first-class in the main
// nav via a repoint of the old /advisory-council references.
//
// Unlike Human Systems, advisory is request/response — this page decides which
// view is shown; each view calls the existing advisory endpoints unchanged. No
// new GET route, no realtime, no live indicator (would be dishonest here).
// See ADVISORY-COUNCIL-WORKBENCH-MIGRATION-PLAN.md.
//
// 2026-08-09: redesigned around the Captain's own review of this workbench
// — too many roles, no invitation on the first page, wanted "ask a
// question, then pull it apart." Ask (AskView.tsx, internal key 'board')
// is now the default landing domain instead of Consult's 18-officer
// sidebar; Consult itself is regrouped behind 5 group chips instead of
// all 18 always expanded (see ConsultView.tsx).

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { WorkbenchShell, DomainToggle } from '@/components/ui';
import { ConsultView } from './_components/ConsultView';
import { AskView } from './_components/AskView';
import { PerspectivesView } from './_components/PerspectivesView';
import { LoopsView } from './_components/LoopsView';
import { ProactiveBanner } from './_components/ProactiveBanner';
import { EYEBROW, isDomain, type Domain } from './_components/types';

// 2026-08-09 redesign: 'board' is the internal key (unchanged — existing
// advisory-sessions rows already use mode:'board', investigate/page.tsx's
// deep link already targets ?domain=board) but "Ask" is now both the
// label and the default landing view, not "Consult"'s 18-officer sidebar.
const DOMAIN_OPTIONS: { key: Domain; label: string }[] = [
  { key: 'board', label: 'Ask' },
  { key: 'consult', label: 'Talk to Someone' },
  { key: 'perspectives', label: 'Panel of Voices' },
  { key: 'loops', label: 'Close Out' },
];

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();

  // Back-compat: the legacy page used ?tab=; honour it as an alias for ?domain=.
  // A deep-linked investigation lands on Ask (default domain), matching
  // the old contract's "opens Board" behavior.
  const investigationType = params.get('investigationType') ?? undefined;
  const investigationReason = params.get('investigationReason') ?? undefined;
  const initial = params.get('domain') ?? params.get('tab');
  const [domain, setDomain] = useState<Domain>(isDomain(initial) ? initial : 'board');

  const changeDomain = (d: Domain) => {
    setDomain(d);
    // Keep the URL shareable/bookmarkable without a full navigation.
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.delete('tab');
    sp.set('domain', d);
    router.replace(`/advisory-workbench?${sp.toString()}`, { scroll: false });
  };

  return (
    <WorkbenchShell
      title="Advisory"
      eyebrow={EYEBROW[domain]}
      tagline="USS TJR · Advisory · Ask a question, one specific advisor, or a panel of voices · Advisory only — the Captain decides"
      tabs={<DomainToggle value={domain} onChange={changeDomain} options={DOMAIN_OPTIONS} ariaLabel="Advisory domain" />}
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      <div className="mb-4">
        <ProactiveBanner />
      </div>
      {domain === 'board' && (
        <AskView investigationType={investigationType} investigationReason={investigationReason} />
      )}
      {domain === 'consult' && <ConsultView />}
      {domain === 'perspectives' && <PerspectivesView />}
      {domain === 'loops' && <LoopsView />}
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
