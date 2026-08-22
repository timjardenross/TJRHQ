'use client';

// Human Systems Workbench — unified single-page view.
//
// Standalone route (outside the (app) group), same wb- design system as the
// other workbenches. Reachable from /workbenches; not promoted into the
// LCARS navigation model.
//
// VNext consolidation (Human_Systems_Workbench_VNext_Consolidation_Mission_
// Scope.md, WP01): the former Recovery/Medical tab split is removed. Both
// domain payloads are fetched together and rendered as one continuous page
// — a decision-support flow read top to bottom, not a collection of tabs.
// /api/human-systems itself is untouched (still domain-branched:
// ?domain=recovery|medical|readiness) — this page just stops choosing
// between them.
//
// Readiness (2026-08-22): no longer fetched or rendered here — Captain
// directive to declutter, along with Life Participation and Sleep. The
// ?domain=readiness API branch, ReadinessView component, and the
// readiness/* sub-routes are all still intact if this needs to come back;
// this page just stopped calling any of them.
//
// The 8 internal sub-route back-links across log/, medical/*, and
// readiness/* still append `?domain=medical|recovery|readiness` to their
// return link — harmless (this route ignores the param and always renders
// everything it fetches), so none of them needed touching.

import { Suspense, useCallback, useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { KpiDashboard } from './_components/KpiDashboard';
import { RecoveryView } from './_components/RecoveryView';
import { MedicalView } from './_components/MedicalView';
import { useRealtimeRefresh } from '@/lib/realtime/useRealtimeRefresh';
import type { MedicalPayload, RecoveryPayload } from './_components/types';

interface Loaded {
  recovery: RecoveryPayload | null;
  medical: MedicalPayload | null;
}

function Workbench() {
  const [data, setData] = useState<Loaded | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [live, setLive] = useState(false);

  const load = useCallback((withSpinner: boolean) => {
    if (withSpinner) setLoading(true);
    return Promise.all([
      fetch('/api/human-systems?domain=recovery').then((r) => r.json()),
      fetch('/api/human-systems?domain=medical').then((r) => r.json()),
    ])
      .then(([recovery, medical]: [unknown, unknown]) => {
        const clean = <T,>(p: unknown): T | null =>
          p && typeof p === 'object' && !('error' in (p as Record<string, unknown>)) ? (p as T) : null;
        setData({ recovery: clean<RecoveryPayload>(recovery), medical: clean<MedicalPayload>(medical) });
        setLoadFailed(!recovery || (typeof recovery === 'object' && recovery !== null && 'error' in recovery));
        setLastUpdated(new Date());
      })
      .catch(() => setLoadFailed(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(true);
  }, [load]);

  // Live refresh: every remaining section reads the capacity_checkins signal.
  useRealtimeRefresh({
    table: 'capacity_checkins',
    events: ['INSERT', 'UPDATE'],
    enabled: true,
    onChange: () => load(false),
    onStatusChange: (s) => setLive(s === 'SUBSCRIBED'),
  });

  const right = (
    <span className="hidden text-[11px] text-wb-ink2 sm:inline">
      {live ? '● Live' : lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}` : ''}
    </span>
  );

  return (
    <WorkbenchShell title="Human Systems Workbench" eyebrow="Capacity, Regulation & Recovery"
      tagline="USS TJR · A live view of how my body, nervous system, mind, environment and demands are interacting today · Evidence-informed, non-diagnostic"
      right={right}
      back={{ href: '/workbenches', label: 'Workbenches' }}>
      {loading && !data && <div className="py-16 text-center text-[13px] text-wb-ink2">Loading Human Systems…</div>}

      {data?.recovery && (
        <>
          <KpiDashboard kpis={data.recovery.kpis} />
          <div className="flex flex-col gap-4">
            <RecoveryView data={data.recovery} interventionEffectiveness={data.medical?.intervention_effectiveness ?? []} />
            {data.medical && <MedicalView data={data.medical} />}
          </div>
        </>
      )}

      {loadFailed && !data?.recovery && (
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
