'use client';

// Knowledge Workbench — unified Memory | Library collection.
//
// Standalone route (outside the (app) group), same wb- design system and
// domain-toggle architecture as the Intelligence Workbench. Reachable from
// /workbenches; not promoted into the LCARS navigation model. The two domains
// are views over organisational decisions and personal documents.

import { Suspense, useCallback, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { WorkbenchShell, DomainToggle } from '@/components/ui';
import { MemoryView } from './_components/MemoryView';
import { LibraryView } from './_components/LibraryView';
import type { Domain } from './_components/types';

const DOMAIN_OPTIONS: { key: Domain; label: string }[] = [
  { key: 'memory', label: 'Memory' },
  { key: 'library', label: 'Library' },
];

const EYEBROW: Record<Domain, string> = {
  memory: 'Command Memory',
  library: 'Document Library',
};

function isDomain(v: string | null): v is Domain {
  return v === 'memory' || v === 'library';
}

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get('domain');
  const [domain, setDomain] = useState<Domain>(isDomain(initial) ? initial : 'memory');

  const changeDomain = (d: Domain) => {
    setDomain(d);
    // Keep the URL shareable/bookmarkable without a full navigation.
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('domain', d);
    router.replace(`/knowledge-workbench?${sp.toString()}`, { scroll: false });
  };

  const right = <DomainToggle value={domain} onChange={changeDomain} options={DOMAIN_OPTIONS} ariaLabel="Knowledge domain" />;

  return (
    <WorkbenchShell title="Knowledge Workbench" eyebrow={EYEBROW[domain]}
      homeHref="/knowledge-workbench"
      tagline="USS TJR · Knowledge · Memory · Library · Organisational decisions and personal documents"
      right={right} back={{ href: '/workbenches', label: 'Workbenches' }}>
      {domain === 'memory' && <MemoryView />}
      {domain === 'library' && <LibraryView />}
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
