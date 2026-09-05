'use client';

// Captain's Brief Workbench — MSN-0313 on the wb- design system.
//
// Standalone route (outside the (app) group), same Shell + domain-toggle
// architecture as the Advisory / Human Systems / Intelligence Workbenches.
// Reachable from /workbenches. See CAPTAINS-BRIEF-WORKBENCH-MIGRATION-PLAN.md.
//
// The brief is request/response — assembled on GET by the context-service, not
// pushed — so there is NO realtime / ● Live indicator (would be dishonest, as
// in Advisory). A manual Refresh re-fetches. The entire assembly pipeline is
// reused verbatim: this page GETs /api/captain-brief (which proxies the Python
// context-service's /brief/full). No backend/route/contract changes.
//
// Failure state surfaces the route's `detail` field (the real upstream cause:
// unauthorized / full_captain_brief_failed / a fetch error) — the LCARS page
// discarded it, leaving "Failed to assemble Captain Brief" un-diagnosable.

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { WorkbenchShell, DomainToggle } from '@/components/ui';
import { KpiDashboard } from './_components/KpiDashboard';
import { BriefView } from './_components/BriefView';
import { DomainsView } from './_components/DomainsView';
import { EYEBROW, isDomain, type CaptainBriefDocument, type Domain } from './_components/types';

const DOMAIN_OPTIONS: { key: Domain; label: string }[] = [
  { key: 'brief', label: 'Brief' },
  { key: 'domains', label: 'Domains' },
];

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();

  const initial = params.get('domain');
  const [domain, setDomain] = useState<Domain>(isDomain(initial) ? initial : 'brief');

  const [doc, setDoc] = useState<CaptainBriefDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const warningsRef = useRef<HTMLDivElement>(null);
  const prioritiesRef = useRef<HTMLDivElement>(null);
  const nextActionsRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    setDetail(null);
    fetch('/api/captain-brief')
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) {
          if (typeof body?.detail === 'string' && body.detail) setDetail(body.detail);
          throw new Error(body.error ?? 'Failed to load Captain Brief');
        }
        setDoc(body);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const changeDomain = (d: Domain) => {
    setDomain(d);
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('domain', d);
    router.replace(`/captains-brief-workbench?${sp.toString()}`, { scroll: false });
  };

  const jump = (target: 'warnings' | 'priorities' | 'next_actions') => {
    if (domain !== 'brief') changeDomain('brief');
    const ref = { warnings: warningsRef, priorities: prioritiesRef, next_actions: nextActionsRef }[target];
    // Defer so the Brief view is mounted before scrolling to its section.
    requestAnimationFrame(() => ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };

  const right = (
    <div className="flex items-center gap-2">
      <button
        onClick={load}
        disabled={loading}
        className="rounded-md border border-wb-line px-2.5 py-1 text-[12px] text-wb-ink2 transition hover:bg-wb-line disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep"
      >
        {loading ? 'Refreshing…' : '↻ Refresh'}
      </button>
      <DomainToggle value={domain} onChange={changeDomain} options={DOMAIN_OPTIONS} ariaLabel="Captain’s Brief view" />
    </div>
  );

  return (
    <WorkbenchShell wide
      title="Captain’s Brief"
      eyebrow={EYEBROW[domain]}
      tagline="USS TJR · Captain’s Brief · assembled on request — reports the signals received, not an all-clear"
      right={right}
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      {loading && !doc && <p className="text-sm text-wb-ink2">Assembling brief…</p>}

      {error && (
        <div className="rounded-md border border-wb-crit bg-wb-crit/10 p-4">
          <p className="text-sm font-medium text-wb-crit-on">{error}</p>
          {detail && <p className="mt-1 break-words font-mono text-xs text-wb-ink2">Cause: {detail}</p>}
          <button
            onClick={load}
            className="mt-2 rounded-md border border-wb-line px-2.5 py-1 text-[12px] text-wb-ink2 transition hover:bg-wb-line focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep"
          >
            Retry
          </button>
        </div>
      )}

      {doc && !error && (
        <>
          <KpiDashboard doc={doc} onJump={jump} />
          {domain === 'brief' && (
            <BriefView
              doc={doc}
              refs={{ warnings: warningsRef, priorities: prioritiesRef, next_actions: nextActionsRef }}
            />
          )}
          {domain === 'domains' && <DomainsView doc={doc} />}
        </>
      )}
    </WorkbenchShell>
  );
}

export default function CaptainsBriefWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
