'use client';

// Capture Workbench — Capture / Inbox on the wb- design system.
//
// Standalone route (outside the (app) group), same Shell + domain-toggle +
// KpiDashboard architecture as the Human Systems Workbench. Reachable from
// /workbenches and (Captain decision 2026-07-12) kept first-class in the
// mobile command bar via a repoint of the old /capture references.
//
// UI-only: the data layer (lib/capture.ts) and the CC proxy (/api/capture/[id])
// are reused unchanged. Unlike Advisory, live refresh is honest here — captures
// arrive asynchronously from Telegram/Slack/API, so we subscribe captured_items.
// See CAPTURE-WORKBENCH-MIGRATION-PLAN.md.

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { WorkbenchShell, DomainToggle } from '@/components/ui';
import { KpiDashboard } from './_components/KpiDashboard';
import { CaptureView } from './_components/CaptureView';
import { InboxView } from './_components/InboxView';
import { EYEBROW, isDomain, isInboxFilter, type Domain, type InboxFilter } from './_components/types';
import { fetchCaptureAnalytics, type CaptureAnalytics } from '@/lib/capture';
import { useRealtimeRefresh } from '@/lib/realtime/useRealtimeRefresh';

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();

  const initialDomain = params.get('domain');
  const initialFilter = params.get('filter');
  const [domain, setDomain] = useState<Domain>(
    isDomain(initialDomain) ? initialDomain : initialFilter ? 'inbox' : 'capture',
  );
  const [inboxFilter, setInboxFilter] = useState<InboxFilter>(isInboxFilter(initialFilter) ? initialFilter : 'all');

  const [stats, setStats] = useState<CaptureAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [live, setLive] = useState(false);
  // Bumped on a realtime change or a new capture; InboxView reloads its list on it.
  const [refreshSignal, setRefreshSignal] = useState(0);

  const loadStats = useCallback((withSpinner: boolean) => {
    if (withSpinner) setLoading(true);
    return fetchCaptureAnalytics()
      .then((s) => { setStats(s); setLastUpdated(new Date()); })
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  // Refresh both the KPI stats and the inbox list.
  const refresh = useCallback(() => { loadStats(false); setRefreshSignal((n) => n + 1); }, [loadStats]);

  useEffect(() => { loadStats(true); }, [loadStats]);

  // Live: new captures land in captured_items from Telegram/Slack/API/portal.
  useRealtimeRefresh({
    table: 'captured_items',
    events: ['INSERT', 'UPDATE'],
    enabled: true,
    onChange: refresh,
    onStatusChange: (s) => setLive(s === 'SUBSCRIBED'),
  });

  const syncUrl = useCallback((next: { domain?: Domain; filter?: InboxFilter }) => {
    const sp = new URLSearchParams(Array.from(params.entries()));
    if (next.domain) sp.set('domain', next.domain);
    if (next.filter) sp.set('filter', next.filter);
    router.replace(`/capture-workbench?${sp.toString()}`, { scroll: false });
  }, [params, router]);

  const changeDomain = (d: Domain) => { setDomain(d); syncUrl({ domain: d }); };
  const changeFilter = (f: InboxFilter) => { setInboxFilter(f); syncUrl({ filter: f }); };
  const filterToInbox = (f: InboxFilter) => { setDomain('inbox'); setInboxFilter(f); syncUrl({ domain: 'inbox', filter: f }); };

  const right = (
    <div className="flex items-center gap-3">
      <span className="hidden text-[11px] text-wb-ink2 sm:inline">
        {live ? '● Live' : lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}` : ''}
      </span>
      <DomainToggle
        value={domain}
        onChange={changeDomain}
        ariaLabel="Capture domain"
        options={[
          { key: 'capture' as const, label: 'Capture' },
          { key: 'inbox' as const, label: 'Inbox', badge: stats?.pending },
        ]}
      />
    </div>
  );

  return (
    <WorkbenchShell title="Capture" eyebrow={EYEBROW[domain]}
      homeHref="/capture-workbench"
      homeAriaLabel="Capture Workbench home"
      tagline="USS TJR · Capture · Review-first — nothing auto-routes without your say"
      right={right} back={{ href: '/workbenches', label: 'Workbenches' }}>
      <KpiDashboard stats={stats} loading={loading} onFilter={filterToInbox} />
      {domain === 'capture' && <CaptureView onCaptured={refresh} />}
      {domain === 'inbox' && (
        <InboxView
          activeFilter={inboxFilter}
          onFilterChange={changeFilter}
          refreshSignal={refreshSignal}
          onMutated={() => loadStats(false)}
        />
      )}
    </WorkbenchShell>
  );
}

export default function CaptureWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
