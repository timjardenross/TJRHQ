'use client';

/**
 * Agent & Job Status Workbench — Phase 3 "Three-Workbench Simplification"
 * uplift: from a plain job/heartbeat table into the technical health screen
 * for HQ's machinery. Four tabs, progressive disclosure per the mission
 * spec: System Health (default landing) -> Source Health -> Pipeline
 * Health -> Jobs.
 *
 * This workbench is now the SOLE owner of source-health / pipeline-health /
 * ingestion diagnostics UI — Technical OSINT (/intelligence-workbench) and
 * Health OSINT (/health-osint) link here instead of duplicating it.
 *
 * Data sources (all read-only, no new scoring logic):
 *  - /api/agent-status-workbench/overview   — System Health landing
 *  - /api/agent-status-workbench/sources    — Source Health tab
 *  - /api/agent-status-workbench/pipeline-quality — Pipeline Health tab
 *    (reads the Phase 26 views: intelligence_ingestion_quality_daily /
 *    health_ingestion_quality_daily, migration 0187)
 *  - /api/agent-status (unchanged) — Jobs tab, scheduler state from
 *    domain_heartbeats
 *
 * Route stays a single page at /agent-status-workbench with tab state
 * synced to ?tab= (same pattern as content-workbench's MSN-0363 uplift) so
 * sibling workbenches can link to stable URLs:
 *   /agent-status-workbench?tab=sources
 *   /agent-status-workbench?tab=pipeline
 *   /agent-status-workbench?tab=jobs
 */

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { DomainToggle, WorkbenchShell } from '@/components/ui';
import { OverviewView } from './_components/OverviewView';
import { SourcesView } from './_components/SourcesView';
import { PipelineHealthView } from './_components/PipelineHealthView';
import { JobsView } from './_components/JobsView';

type Tab = 'overview' | 'sources' | 'pipeline' | 'jobs';

const TAB_OPTIONS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'System Health' },
  { key: 'sources', label: 'Source Health' },
  { key: 'pipeline', label: 'Pipeline Health' },
  { key: 'jobs', label: 'Jobs' },
];

function isTab(v: string | null): v is Tab {
  return v === 'overview' || v === 'sources' || v === 'pipeline' || v === 'jobs';
}

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get('tab');
  const [tab, setTabState] = useState<Tab>(isTab(initial) ? initial : 'overview');

  const setTab = (t: Tab) => {
    setTabState(t);
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('tab', t);
    router.replace(`/agent-status-workbench?${sp.toString()}`, { scroll: false });
  };

  return (
    <WorkbenchShell
      title="Agent & Job Status"
      eyebrow="Platform Operations"
      tagline="USS TJR · Agent Status · Technical health screen for HQ's machinery"
      tabs={<DomainToggle value={tab} onChange={setTab} options={TAB_OPTIONS} ariaLabel="Agent & Job Status sections" />}
      back={{ href: '/workbenches', label: 'Workbenches' }}
      wide
    >
      {tab === 'overview' && <OverviewView onNavigate={setTab} />}
      {tab === 'sources' && <SourcesView />}
      {tab === 'pipeline' && <PipelineHealthView />}
      {tab === 'jobs' && <JobsView />}
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
