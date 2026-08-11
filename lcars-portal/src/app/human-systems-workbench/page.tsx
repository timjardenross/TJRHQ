'use client';

// Human Systems Workbench — unified Recovery / Medical collection.
//
// Standalone route (outside the (app) group), same wb- design system and
// domain-toggle architecture as the Intelligence Workbench. Reachable from
// /workbenches; not promoted into the LCARS navigation model. The two tabs
// are views over data that is already live in the platform (see
// /api/human-systems) — this page only decides which view is shown and when
// to re-fetch.
//
// 2026-08-10: Readiness folded into the Recovery tab (not a separate API
// domain change — /api/human-systems still serves a 'readiness' payload,
// this page just fetches it alongside 'recovery' and renders both views
// together). Readiness had thinned to two quick links and a "last session"
// card after that day's manual check-in removal; Medical stayed separate —
// still five substantive cards, and combining all three risked recreating
// the long-scroll problem already flagged and worked around on Captain's
// Chair the day before. `?domain=readiness` deep links (still used by the
// readiness sub-routes' back-links) are kept working as an alias for the
// Recovery tab rather than touching every one of those files.

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { WorkbenchShell, DomainToggle } from '@/components/ui';
import { KpiDashboard } from './_components/KpiDashboard';
import { RecoveryView } from './_components/RecoveryView';
import { MedicalView } from './_components/MedicalView';
import { ReadinessView } from './_components/ReadinessView';
import { useRealtimeRefresh } from '@/lib/realtime/useRealtimeRefresh';
import type { Payload, ReadinessPayload } from './_components/types';

type TabDomain = 'recovery' | 'medical';

const EYEBROW: Record<TabDomain, string> = {
  recovery: 'Recovery, Capacity & Readiness',
  medical: 'Health Tracking',
};

const DOMAIN_OPTIONS: { key: TabDomain; label: string }[] = [
  { key: 'recovery', label: 'Recovery' },
  { key: 'medical', label: 'Medical' },
];

function isTabDomain(v: string | null): v is TabDomain {
  return v === 'recovery' || v === 'medical';
}

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get('domain');
  // 'readiness' deep links resolve into the Recovery tab (see header note).
  const [tab, setTab] = useState<TabDomain>(isTabDomain(initial) ? initial : 'recovery');
  const [data, setData] = useState<Payload | { error: string } | null>(null);
  const [readinessData, setReadinessData] = useState<ReadinessPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [live, setLive] = useState(false);

  const load = useCallback(
    (d: TabDomain, withSpinner: boolean) => {
      if (withSpinner) setLoading(true);
      const primary = fetch(`/api/human-systems?domain=${d}`).then((r) => r.json());
      const readiness =
        d === 'recovery' ? fetch('/api/human-systems?domain=readiness').then((r) => r.json()) : Promise.resolve(null);
      return Promise.all([primary, readiness])
        .then(([payload, readinessPayload]: [Payload | { error: string }, ReadinessPayload | { error: string } | null]) => {
          setData(payload);
          setReadinessData(readinessPayload && !('error' in readinessPayload) ? readinessPayload : null);
          setLastUpdated(new Date());
        })
        .catch(() => setData(null))
        .finally(() => setLoading(false));
    },
    [],
  );

  useEffect(() => {
    load(tab, true);
  }, [tab, load]);

  const changeTab = (d: TabDomain) => {
    setTab(d);
    // Keep the URL shareable/bookmarkable without a full navigation.
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('domain', d);
    router.replace(`/human-systems-workbench?${sp.toString()}`, { scroll: false });
  };

  // Live refresh: Recovery + Medical read the recovery_pulses signal; Recovery
  // also carries Readiness now, so it additionally watches workout sessions.
  useRealtimeRefresh({
    table: 'recovery_pulses',
    events: ['INSERT', 'UPDATE'],
    enabled: tab === 'recovery' || tab === 'medical',
    onChange: () => load(tab, false),
    onStatusChange: (s) => setLive(s === 'SUBSCRIBED'),
  });
  useRealtimeRefresh({
    table: 'physical_workout_sessions',
    events: ['INSERT', 'UPDATE'],
    enabled: tab === 'recovery',
    onChange: () => load(tab, false),
    onStatusChange: (s) => setLive(s === 'SUBSCRIBED'),
  });

  const right = (
    <span className="hidden text-[11px] text-wb-ink2 sm:inline">
      {live ? '● Live' : lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}` : ''}
    </span>
  );

  return (
    <WorkbenchShell title="Human Systems" eyebrow={EYEBROW[tab]}
      tagline="USS TJR · Human Systems · Recovery & Readiness · Medical · Evidence-informed, non-diagnostic"
      right={right}
      tabs={<DomainToggle value={tab} onChange={changeTab} options={DOMAIN_OPTIONS} ariaLabel="Human Systems domain" />}
      back={{ href: '/workbenches', label: 'Workbenches' }}>
      {loading && !data && <div className="py-16 text-center text-[13px] text-wb-ink2">Loading Human Systems…</div>}

      {data && !('error' in data) && (
        <>
          <KpiDashboard kpis={data.kpis} />
          {data.domain === 'recovery' && (
            <div className="flex flex-col gap-4">
              <RecoveryView data={data} />
              {readinessData && (
                <>
                  <div className="mt-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-wb-ink2">Readiness</div>
                  <ReadinessView data={readinessData} />
                </>
              )}
            </div>
          )}
          {data.domain === 'medical' && <MedicalView data={data} />}
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
