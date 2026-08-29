'use client';

// Human Systems Workbench — unified single-page view.
//
// Standalone route (outside the (app) group), same wb- design system as the
// other workbenches. Reachable from /workbenches; not promoted into the
// LCARS navigation model.
//
// Domain boundary (2026-08-29, docs/UI-Layer-Debt-Handoff-2026-08-29.md
// Finding 3, resolved): this is first-party personal recovery/readiness
// telemetry (capacity_checkins, capacity_experiments,
// physical_workout_sessions, health_insights et al. — the Captain's own
// data). It has zero overlap with Health OSINT Workbench (/health-osint),
// which is external, population-level research intelligence — disjoint
// tables, disjoint user tasks. Kept as separate workbenches by design, not
// by drift; no merge needed.
//
// VNext consolidation (Human_Systems_Workbench_VNext_Consolidation_Mission_
// Scope.md, WP01): the former Recovery/Medical tab split is removed. Both
// domain payloads are fetched together and rendered as one continuous page
// — a decision-support flow read top to bottom, not a collection of tabs.
// /api/human-systems itself is untouched (still domain-branched:
// ?domain=recovery|medical|readiness) — this page just stops choosing
// between them.
//
// Readiness: declutter directive 2026-08-22 unmounted it from this page;
// 3-workbench council item 2/5 (2026-08-29) then deleted it outright —
// ReadinessView.tsx, the readiness/* sub-routes, and the ?domain=readiness
// API branch are all gone, not just unlinked. It was a never-linked reskin
// attempt; the live, mobile-primary readiness experience is
// (app)/physical-readiness/* (linked from MobileCommandBar's TABS),
// unaffected by this removal. If personal readiness tracking needs a
// presence on this page again, build it fresh rather than reviving this.
//
// The remaining internal sub-route back-links across log/ and medical/*
// still append `?domain=medical|recovery` to their return link — harmless
// (this route ignores the param and always renders everything it
// fetches), so none of them needed touching.

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
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
      {/* 2026-08-29 (3-workbench council item 3/5): recovery-brief/page.tsx
          was live and real (a genuine wb-native replacement for the retired
          (app)/recovery-brief page) but had zero inbound link from this
          workbench's own main page — only reachable via a legacy redirect.
          One line back in, as recommended, not a redesign. */}
      <Link
        href="/human-systems-workbench/recovery-brief"
        className="mb-1 inline-block text-[12px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
      >
        Recovery Brief →
      </Link>

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
