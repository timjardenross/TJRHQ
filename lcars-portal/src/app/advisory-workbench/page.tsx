'use client';

// Advisory Workbench — Consult / Board / Perspectives on the wb- design system.
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

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Shell } from './_components/Shell';
import { DomainToggle } from './_components/DomainToggle';
import { ConsultView } from './_components/ConsultView';
import { BoardView } from './_components/BoardView';
import { PerspectivesView } from './_components/PerspectivesView';
import { ProactiveBanner } from './_components/ProactiveBanner';
import { EYEBROW, isDomain, type Domain } from './_components/types';

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();

  // Back-compat: the legacy page used ?tab=; honour it as an alias for ?domain=.
  // A deep-linked investigation opens Board (matches the old contract).
  const investigationType = params.get('investigationType') ?? undefined;
  const investigationReason = params.get('investigationReason') ?? undefined;
  const initial = params.get('domain') ?? params.get('tab');
  const [domain, setDomain] = useState<Domain>(
    isDomain(initial) ? initial : investigationType && investigationReason ? 'board' : 'consult',
  );

  const changeDomain = (d: Domain) => {
    setDomain(d);
    // Keep the URL shareable/bookmarkable without a full navigation.
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.delete('tab');
    sp.set('domain', d);
    router.replace(`/advisory-workbench?${sp.toString()}`, { scroll: false });
  };

  const right = <DomainToggle domain={domain} onChange={changeDomain} />;

  return (
    <Shell
      title="Advisory"
      eyebrow={EYEBROW[domain]}
      right={right}
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      <div className="mb-4">
        <ProactiveBanner />
      </div>
      {domain === 'consult' && <ConsultView />}
      {domain === 'board' && (
        <BoardView investigationType={investigationType} investigationReason={investigationReason} />
      )}
      {domain === 'perspectives' && <PerspectivesView />}
    </Shell>
  );
}

export default function AdvisoryWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
