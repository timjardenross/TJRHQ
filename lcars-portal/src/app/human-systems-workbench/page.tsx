'use client';

// Human Systems Workbench — unified Recovery / Medical / Readiness collection.
//
// Standalone route (outside the (app) group), same wb- design system and
// domain-toggle architecture as the Intelligence Workbench. Reachable from
// /workbenches; not promoted into the LCARS navigation model. The three domains
// are views over data that is already live in the platform (see
// /api/human-systems) — this page only decides which view is shown and when to
// re-fetch.

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { WorkbenchShell } from '@/components/ui';
import { DomainToggle } from './_components/DomainToggle';
import { KpiDashboard } from './_components/KpiDashboard';
import { RecoveryView } from './_components/RecoveryView';
import { MedicalView } from './_components/MedicalView';
import { ReadinessView } from './_components/ReadinessView';
import { useRealtimeRefresh } from '@/lib/realtime/useRealtimeRefresh';
import type { Domain, Payload } from './_components/types';

const EYEBROW: Record<Domain, string> = {
  recovery: 'Recovery & Capacity',
  medical: 'Health Tracking',
  readiness: 'Fitness Readiness',
};

function isDomain(v: string | null): v is Domain {
  return v === 'recovery' || v === 'medical' || v === 'readiness';
}

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get('domain');
  const [domain, setDomain] = useState<Domain>(isDomain(initial) ? initial : 'recovery');
  const [data, setData] = useState<Payload | { error: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [live, setLive] = useState(false);

  const load = useCallback(
    (d: Domain, withSpinner: boolean) => {
      if (withSpinner) setLoading(true);
      return fetch(`/api/human-systems?domain=${d}`)
        .then((r) => r.json())
        .then((payload: Payload | { error: string }) => {
          setData(payload);
          setLastUpdated(new Date());
        })
        .catch(() => setData(null))
        .finally(() => setLoading(false));
    },
    [],
  );

  useEffect(() => {
    load(domain, true);
  }, [domain, load]);

  const changeDomain = (d: Domain) => {
    setDomain(d);
    // Keep the URL shareable/bookmarkable without a full navigation.
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('domain', d);
    router.replace(`/human-systems-workbench?${sp.toString()}`, { scroll: false });
  };

  // Live refresh: Recovery + Medical read the recovery_pulses signal; Readiness
  // reads workout sessions. Only the active domain's table is subscribed.
  useRealtimeRefresh({
    table: 'recovery_pulses',
    events: ['INSERT', 'UPDATE'],
    enabled: domain === 'recovery' || domain === 'medical',
    onChange: () => load(domain, false),
    onStatusChange: (s) => setLive(s === 'SUBSCRIBED'),
  });
  useRealtimeRefresh({
    table: 'physical_workout_sessions',
    events: ['INSERT', 'UPDATE'],
    enabled: domain === 'readiness',
    onChange: () => load(domain, false),
    onStatusChange: (s) => setLive(s === 'SUBSCRIBED'),
  });

  const right = (
    <div className="flex items-center gap-3">
      <span className="hidden text-[11px] text-wb-ink2 sm:inline">
        {live ? '● Live' : lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}` : ''}
      </span>
      <DomainToggle domain={domain} onChange={changeDomain} />
    </div>
  );

  return (
    <WorkbenchShell title="Human Systems" eyebrow={EYEBROW[domain]}
      homeHref="/human-systems-workbench"
      tagline="USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic"
      right={right} back={{ href: '/workbenches', label: 'Workbenches' }}>
      {loading && !data && <div className="py-16 text-center text-[13px] text-wb-ink2">Loading Human Systems…</div>}

      {data && !('error' in data) && (
        <>
          <KpiDashboard kpis={data.kpis} />
          {data.domain === 'recovery' && <RecoveryView data={data} />}
          {data.domain === 'medical' && <MedicalView data={data} />}
          {data.domain === 'readiness' && <ReadinessView data={data} />}
        </>
      )}

      {data && 'error' in data && (
        <div className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-4 text-[13px] text-wb-crit-on">
          Couldn&rsquo;t load Human Systems data. The workbench stays read-only and safe; try again shortly.
        </div>
      )}
    </WorkbenchShell>
  );
}

export default function HumanSystemsWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
