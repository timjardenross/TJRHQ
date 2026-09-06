'use client';

// SYSTEM STATUS (Command-Experience vNext, Phase 2, mission §9.7) — tiny by
// design. Reads the canonical HQ Status summary (hqStatusInterpreter.ts's
// buildCaptainChairSummary(), via useHqStatusSummary()) — never a raw
// failed-job count. A DEGRADED HQ needs no action; only ATTENTION does,
// and that same item also appears in Needs You (mission: "the same item
// may appear in NEEDS YOU").

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { stateToneClasses } from '@/lib/departments';
import type { HqStatusSummary } from '@/lib/captainsChairData';

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
        <p className={`text-sm font-semibold ${stateToneClasses('unknown').text}`}>Status unknown — HQ Status is unavailable.</p>
      </WorkbenchPanel>
    );
  }

  if (data.posture === 'NORMAL') {
    return (
      <WorkbenchPanel title="System Status">
        <p className={`text-sm font-medium ${stateToneClasses('ok').text}`}>✓ HQ operating normally</p>
      </WorkbenchPanel>
    );
  }

  if (data.posture === 'ATTENTION') {
    return (
      <WorkbenchPanel title="System Status">
        <p className={`text-sm font-semibold ${stateToneClasses('crit').text}`}>HQ NEEDS YOU</p>
        <p className="mt-1 text-sm text-wb-ink/80">{data.summary}</p>
        <Link href="/agent-status-workbench" className="mt-2 inline-block text-[11px] text-wb-sage-deep hover:underline">Review →</Link>
      </WorkbenchPanel>
    );
  }

  // DEGRADED or UNKNOWN — worth a glance, no action required yet.
  return (
    <WorkbenchPanel title="System Status">
      <p className={`text-sm font-medium ${stateToneClasses('warn').text}`}>⚠ {data.summary}</p>
      <p className="mt-1 text-[12.5px] text-wb-ink2">No action required yet.</p>
    </WorkbenchPanel>
  );
}
