'use client';

// Human Systems Workbench — tabbed view (Human Systems redesign, 2026-09-06).
//
// Standalone route (outside the (app) group), same wb- design system as the
// other workbenches. Reachable from /workbenches; not promoted into the
// LCARS navigation model. Route stays /human-systems-workbench — only the
// user-facing title shortened to "Human Systems".
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
// NOW / WHAT HELPS / PATTERNS / TRENDS tabs (2026-09-06, replacing the
// 2026-08-29 VNext single continuous-scroll layout): "Medical" is retired
// as a primary user-facing tab/mode name — its content (Capacity & Recovery
// Conditions, Sensory & Regulation, redesign candidates) is redistributed
// into NOW and PATTERNS (see NowView.tsx / PatternsView.tsx), not deleted.
// /api/human-systems itself is untouched (still domain-branched:
// ?domain=recovery|medical|readiness) — both payloads are still fetched
// together; only how they're presented changed. TRENDS is a real
// navigation to the existing /human-systems-workbench/trends route, not an
// embedded rebuild — that page is left alone this pass.
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
import { useRouter } from 'next/navigation';
import { DomainToggle, WorkbenchShell } from '@/components/ui';
import { NowView } from './_components/NowView';
import { PatternsView } from './_components/PatternsView';
import { WhatHelpsView } from './_components/WhatHelpsView';
import { useRealtimeRefresh } from '@/lib/realtime/useRealtimeRefresh';
import type { MedicalPayload, RecoveryPayload } from './_components/types';

interface Loaded {
  recovery: RecoveryPayload | null;
  medical: MedicalPayload | null;
}

type TabKey = 'now' | 'what-helps' | 'patterns';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'now', label: 'NOW' },
  { key: 'what-helps', label: 'WHAT HELPS' },
  { key: 'patterns', label: 'PATTERNS' },
];

const TRENDS_HREF = '/human-systems-workbench/trends';

function Workbench() {
  const router = useRouter();
  const [tab, setTab] = useState<TabKey>('now');
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

  const tabsRow = (
    <div className="flex flex-wrap items-center gap-2">
      <DomainToggle value={tab} onChange={setTab} options={TABS} ariaLabel="Human Systems sections" />
      {/* TRENDS is a real navigation to the existing dedicated Trends page
          (app/human-systems-workbench/trends), not an in-place tab — that
          page isn't being rebuilt this pass, just wired into the nav. It's
          rendered as a plain link/button outside the tablist (not
          role="tab") because it doesn't switch a panel within this page. */}
      <button
        type="button"
        onClick={() => router.push(TRENDS_HREF)}
        className="shrink-0 rounded-md border border-wb-line bg-wb-surface px-3 py-2 text-[13px] font-medium text-wb-ink2 transition hover:border-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep"
      >
        TRENDS →
      </button>
    </div>
  );

  return (
    <WorkbenchShell wide title="Human Systems" eyebrow="Capacity, regulation, recovery & sustainability."
      tagline="USS TJR · A live view of how my body, nervous system, mind, environment and demands are interacting today · Evidence-informed, non-diagnostic"
      right={right}
      tabs={tabsRow}
      back={{ href: '/workbenches', label: 'Workbenches' }}>
      {/* Human Systems redesign Phase 10 (2026-09-06): recovery-brief's real
          content has been consolidated into the NOW/PATTERNS tabs below
          (see recovery-brief/page.tsx's own header comment) — the
          "Recovery Brief →" link added here 2026-08-29 pointed at a page
          that is now an explainer stub, so it's removed rather than
          linking a Captain to a dead end. /human-systems-workbench/
          recovery-brief itself is kept as a route (other callers still
          link to it), just not promoted from this page any more. */}

      {loading && !data && <div className="py-16 text-center text-[13px] text-wb-ink2">Loading Human Systems…</div>}

      {data?.recovery && (
        <>
          {tab === 'now' && <NowView recovery={data.recovery} medical={data.medical} />}
          {tab === 'what-helps' && <WhatHelpsView recovery={data.recovery} medical={data.medical} />}
          {tab === 'patterns' && <PatternsView recovery={data.recovery} medical={data.medical} />}
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
