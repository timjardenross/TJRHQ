'use client';

/**
 * HQ Status (route stays /agent-status-workbench — see spec §59 on
 * migration/compatibility; a future mission may move this to /hq-status
 * with a redirect).
 *
 * HQ Status answers one question: "Is HQ working properly, and does
 * anything actually need me?" — not "what did every job last report?"
 * (spec §1-§2). Four tabs, progressive disclosure:
 *   Status      — interpreted capability posture, calm when healthy.
 *   Automations — the detailed scheduler/job table (formerly "Jobs").
 *   Sources     — source health + pipeline health, nested under one tab
 *                 (formerly two separate top-level tabs).
 *   History     — a compact failure/recovery timeline, not a log viewer.
 *
 * This workbench remains the SOLE owner of source-health / pipeline-health
 * / ingestion diagnostics UI — Technical OSINT (/intelligence-workbench)
 * and Health OSINT (/health-osint) link here instead of duplicating it.
 * Read-only throughout (spec §46) — no retry/rerun/disable/acknowledge
 * actions exist here or are planned without a future mission explicitly
 * authorising them.
 *
 * Data sources (all read-only, no new scoring logic beyond the interpreter
 * in lib/hqStatusInterpreter.ts):
 *  - /api/agent-status-workbench/overview   — Status tab (interpreted)
 *  - /api/agent-status-workbench/sources    — Sources tab (source health)
 *  - /api/agent-status-workbench/pipeline-quality — Sources tab (pipeline)
 *  - /api/agent-status-workbench/history    — History tab
 *  - /api/agent-status (unchanged) — Automations tab, scheduler state from
 *    domain_heartbeats
 *
 * Tab state stays synced to ?tab= (same pattern as content-workbench's
 * MSN-0363 uplift) so sibling workbenches can link to stable URLs:
 *   /agent-status-workbench?tab=automations
 *   /agent-status-workbench?tab=sources
 *   /agent-status-workbench?tab=history
 * Old ?tab=jobs / ?tab=overview / ?tab=pipeline deep links still resolve
 * (mapped below) so nothing that linked here before this uplift breaks.
 */

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { DomainToggle, WorkbenchShell } from '@/components/ui';
import { StatusView } from './_components/StatusView';
import { SourcesTabView } from './_components/SourcesTabView';
import { JobsView } from './_components/JobsView';
import { HistoryView } from './_components/HistoryView';

type Tab = 'status' | 'automations' | 'sources' | 'history';

const TAB_OPTIONS: { key: Tab; label: string }[] = [
  { key: 'status', label: 'Status' },
  { key: 'automations', label: 'Automations' },
  { key: 'sources', label: 'Sources' },
  { key: 'history', label: 'History' },
];

/** Maps a raw ?tab= value (including pre-uplift values) to the current Tab
 *  type, defaulting to 'status'. Keeps old deep links (?tab=overview,
 *  ?tab=jobs, ?tab=pipeline) working per spec §59. */
function resolveTab(v: string | null): Tab {
  switch (v) {
    case 'status':
    case 'overview': // pre-uplift name for this tab
      return 'status';
    case 'automations':
    case 'jobs': // pre-uplift name for this tab
      return 'automations';
    case 'sources':
    case 'pipeline': // pre-uplift: was its own tab, now nested under Sources
      return 'sources';
    case 'history':
      return 'history';
    default:
      return 'status';
  }
}

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  const [tab, setTabState] = useState<Tab>(resolveTab(params.get('tab')));

  const setTab = (t: Tab) => {
    setTabState(t);
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('tab', t);
    router.replace(`/agent-status-workbench?${sp.toString()}`, { scroll: false });
  };

  return (
    <WorkbenchShell
      title="HQ Status"
      eyebrow="Platform Operations"
      tagline="USS TJR · HQ Status · Is HQ working properly?"
      tabs={<DomainToggle value={tab} onChange={setTab} options={TAB_OPTIONS} ariaLabel="HQ Status sections" />}
      back={{ href: '/workbenches', label: 'Workbenches' }}
      wide
    >
      {tab === 'status' && <StatusView onNavigate={setTab} />}
      {tab === 'automations' && <JobsView />}
      {tab === 'sources' && <SourcesTabView />}
      {tab === 'history' && <HistoryView />}
    </WorkbenchShell>
  );
}

export default function AgentStatusWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
