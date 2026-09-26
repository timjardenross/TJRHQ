'use client';

// SYSTEM STATUS (Command-Experience vNext, Phase 2, mission §9.7) — tiny by
// design. Reads the canonical HQ Status summary (hqStatusInterpreter.ts's
// buildCaptainChairSummary(), via useHqStatusSummary()) — never a raw
// failed-job count. A DEGRADED HQ needs no action; only ATTENTION does,
// and that same item also appears in Needs You (mission: "the same item
// may appear in NEEDS YOU").

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { EvidenceMeta } from '@/components/EvidenceMeta';
import { stateToneClasses } from '@/lib/departments';
import type { HqStatusSummary } from '@/lib/captainsChairData';
import { OperationalStateBadge } from '@/components/OperationalState';

export function SystemStatus({ data, loading, error }: { data: HqStatusSummary | null; loading: boolean; error: string | null }) {
  if (loading) {
    return (
      <WorkbenchPanel title="System Status">
        <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>
      </WorkbenchPanel>
    );
  }

  if (error || !data) {
    return (
      <WorkbenchPanel title="System Status">
        <div className="flex flex-wrap items-center gap-2"><OperationalStateBadge state="unavailable" /><p className={`text-sm font-semibold ${stateToneClasses('unknown').text}`}>HQ Status is unavailable.</p></div>
        <EvidenceMeta source="Agent status overview (/api/agent-status-workbench/overview)" state="unavailable" />
      </WorkbenchPanel>
    );
  }

  if (data.posture === 'NORMAL') {
    return (
      <WorkbenchPanel title="System Status">
        <div className="flex flex-wrap items-center gap-2"><OperationalStateBadge state="nominal" /><p className={`text-sm font-medium ${stateToneClasses('ok').text}`}>HQ operating normally</p></div>
        <EvidenceMeta source="Agent status overview" observedAt={data.observedAt} />
      </WorkbenchPanel>
    );
  }

  if (data.posture === 'ATTENTION') {
    return (
      <WorkbenchPanel title="System Status">
        <div className="flex flex-wrap items-center gap-2"><OperationalStateBadge state="attention" /><p className={`text-sm font-semibold ${stateToneClasses('crit').text}`}>HQ NEEDS YOU</p></div>
        <p className="mt-1 text-sm text-wb-ink2">{data.summary}</p>
        <EvidenceMeta source="Agent status overview" observedAt={data.observedAt} />
        <Link href="/agent-status-workbench" className="mt-2 inline-block text-[11px] text-wb-sage-deep hover:underline">Review →</Link>
      </WorkbenchPanel>
    );
  }

  // DEGRADED or UNKNOWN — worth a glance, no action required yet.
  return (
    <WorkbenchPanel title="System Status">
      <div className="flex flex-wrap items-center gap-2"><OperationalStateBadge state="degraded" /><p className={`text-sm font-medium ${stateToneClasses('warn').text}`}>{data.summary}</p></div>
      <p className="mt-1 text-[12.5px] text-wb-ink2">No action required yet.</p>
      <EvidenceMeta source="Agent status overview" observedAt={data.observedAt} state={data.posture === 'UNKNOWN' ? 'unavailable' : undefined} />
    </WorkbenchPanel>
  );
}
