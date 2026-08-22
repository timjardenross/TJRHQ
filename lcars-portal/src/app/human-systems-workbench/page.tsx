'use client';

// Human Systems Workbench — unified single-page view.
//
// Standalone route (outside the (app) group), same wb- design system as the
// other workbenches. Reachable from /workbenches; not promoted into the
// LCARS navigation model.
//
// VNext consolidation (Human_Systems_Workbench_VNext_Consolidation_Mission_
// Scope.md, WP01): the former Recovery/Medical tab split is removed. Both
// domain payloads (plus Readiness, already folded into the Recovery tab on
// 2026-08-10) are fetched together and rendered as one continuous page — the
// doc's "seven major sections read top to bottom as a decision-support
// flow" model, not a collection of tabs. /api/human-systems itself is
// untouched (still domain-branched: ?domain=recovery|medical|readiness) —
// this page just stops choosing between them and fetches all three.
//
// The 8 internal sub-route back-links across log/, medical/*, and
// readiness/* still append `?domain=medical|recovery|readiness` to their
// return link — harmless now (this route ignores the param and always
// renders everything), so none of them needed touching to avoid a 404 or a
// broken bookmark.

import { Suspense, useCallback, useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { KpiDashboard } from './_components/KpiDashboard';
import { RecoveryView } from './_components/RecoveryView';
import { MedicalView } from './_components/MedicalView';
import { ReadinessView } from './_components/ReadinessView';
import { useRealtimeRefresh } from '@/lib/realtime/useRealtimeRefresh';
import type { MedicalPayload, ReadinessPayload, RecoveryPayload } from './_components/types';

interface Loaded {
  recovery: RecoveryPayload | null;
  medical: MedicalPayload | null;
  readiness: ReadinessPayload | null;
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
      fetch('/api/human-systems?domain=readiness').then((r) => r.json()),
    ])
      .then(([recovery, medical, readiness]: [unknown, unknown, unknown]) => {
        const clean = <T,>(p: unknown): T | null =>
          p && typeof p === 'object' && !('error' in (p as Record<string, unknown>)) ? (p as T) : null;
        setData({ recovery: clean<RecoveryPayload>(recovery), medical: clean<MedicalPayload>(medical), readiness: clean<ReadinessPayload>(readiness) });
        setLoadFailed(!recovery || (typeof recovery === 'object' && recovery !== null && 'error' in recovery));
        setLastUpdated(new Date());
      })
      .catch(() => setLoadFailed(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(true);
  }, [load]);

  // Live refresh: every section reads the capacity_checkins signal, plus
  // Readiness additionally watches workout sessions.
  useRealtimeRefresh({
    table: 'capacity_checkins',
    events: ['INSERT', 'UPDATE'],
    enabled: true,
    onChange: () => load(false),
    onStatusChange: (s) => setLive(s === 'SUBSCRIBED'),
  });
  useRealtimeRefresh({
    table: 'physical_workout_sessions',
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
            <RecoveryView data={data.recovery} />
            {data.readiness && (
              <>
                <div className="mt-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-wb-ink2">Readiness</div>
                <ReadinessView data={data.readiness} />
              </>
            )}
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
