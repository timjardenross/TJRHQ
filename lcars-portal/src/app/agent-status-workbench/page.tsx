'use client';

/**
 * Agent & Job Status Workbench — live view of every scheduled platform job.
 *
 * Data source: /api/agent-status, which reads the latest domain_heartbeats
 * row per job. The Event Bus (core_events) is not used here — it has zero
 * agent lifecycle events (confirmed 2026-08-23).
 *
 * Auto-refreshes every 30 seconds. Matches WorkbenchShell, Card, Badge, and
 * stateToneClasses patterns established by mission-workbench and
 * captains-chair-workbench.
 */

import { useEffect, useRef, useState } from 'react';
import { Badge, Card, WorkbenchShell } from '@/components/ui';
import { stateToneClasses } from '@/lib/departments';
import type { StateTone } from '@/lib/types';
import type { AgentStatusEntry } from '@/app/api/agent-status/route';

const REFRESH_INTERVAL_MS = 30_000;

/** Maps domain_heartbeats status values to the design-system StateTone. */
function statusToTone(status: AgentStatusEntry['status']): StateTone {
  switch (status) {
    case 'ok':      return 'ok';
    case 'failed':  return 'crit';
    case 'skipped': return 'warn';
    default:        return 'unknown';
  }
}

/** Maps domain_heartbeats status to a Badge variant label. */
function statusLabel(status: AgentStatusEntry['status']): string {
  switch (status) {
    case 'ok':      return 'OK';
    case 'failed':  return 'Failed';
    case 'skipped': return 'Skipped';
    default:        return 'Unknown';
  }
}

/** Maps domain_heartbeats status to a Badge status prop. */
function statusToBadge(status: AgentStatusEntry['status']): 'success' | 'error' | 'warning' | 'neutral' {
  switch (status) {
    case 'ok':      return 'success';
    case 'failed':  return 'error';
    case 'skipped': return 'warning';
    default:        return 'neutral';
  }
}

/** Renders an ISO-8601 timestamp as a relative string, e.g. "3m ago". */
function relativeTime(isoTimestamp: string | null): string {
  if (!isoTimestamp) return 'Never';
  const diffMs = Date.now() - new Date(isoTimestamp).getTime();
  if (diffMs < 0) return 'Just now';
  const diffSeconds = Math.floor(diffMs / 1000);
  if (diffSeconds < 60)  return `${diffSeconds}s ago`;
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60)  return `${diffMinutes}m ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24)    return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

/** Groups job entries by their domain field, preserving insertion order. */
function groupByDomain(jobs: AgentStatusEntry[]): Map<string, AgentStatusEntry[]> {
  const groups = new Map<string, AgentStatusEntry[]>();
  for (const job of jobs) {
    const existing = groups.get(job.domain);
    if (existing) {
      existing.push(job);
    } else {
      groups.set(job.domain, [job]);
    }
  }
  return groups;
}

const DOMAIN_LABELS: Record<string, string> = {
  intelligence:   'Intelligence',
  health:         'Health',
  'human-systems': 'Human Systems',
  platform:       'Platform',
  'emergency-alerts': 'Emergency Alert Hub',
};

function JobRow({ job }: { job: AgentStatusEntry }) {
  const tone = statusToTone(job.status);
  const classes = stateToneClasses(tone);

  return (
    <tr className="border-b border-wb-line last:border-0">
      <td className="py-3 pr-4">
        <div className="flex items-center gap-2.5">
          <span
            className={`inline-block h-2 w-2 shrink-0 rounded-full ${classes.dot}`}
            aria-hidden
          />
          <span className="text-[13px] font-medium text-wb-ink">{job.label}</span>
        </div>
      </td>
      <td className="py-3 pr-4">
        <Badge status={statusToBadge(job.status)}>{statusLabel(job.status)}</Badge>
      </td>
      <td className="py-3 pr-4 text-[12px] tabular-nums text-wb-ink2">
        <div>{relativeTime(job.lastRun)}</div>
        <div className="text-[10px] normal-case tracking-normal text-wb-ink2/70">{job.cadenceLabel}</div>
      </td>
      <td className="py-3 text-[12px] text-wb-ink2 max-w-[260px] truncate" title={job.lastAction ?? undefined}>
        {job.lastAction ?? <span className="italic">—</span>}
      </td>
    </tr>
  );
}

function DomainSection({ domain, jobs }: { domain: string; jobs: AgentStatusEntry[] }) {
  const label = DOMAIN_LABELS[domain] ?? domain;
  const failedCount = jobs.filter(j => j.status === 'failed').length;

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between border-b border-wb-line pb-3">
        <div>
          <h2 className="font-serif text-lg text-wb-ink">{label}</h2>
          <p className="text-[11px] uppercase tracking-wide text-wb-ink2">
            {jobs.length} job{jobs.length !== 1 ? 's' : ''}
            {failedCount > 0 && (
              <span className="ml-2 text-state-crit-on">{failedCount} failed</span>
            )}
          </p>
        </div>
        {failedCount > 0 && (
          <Badge status="error">{failedCount} Failed</Badge>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-wb-line">
              <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Job</th>
              <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Status</th>
              <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Last Run</th>
              <th className="pb-2 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Last Action</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <JobRow key={job.domainKey} job={job} />
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function AgentStatusWorkbench() {
  const [jobs, setJobs] = useState<AgentStatusEntry[]>([]);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function fetchStatus(withSpinner: boolean) {
    if (withSpinner) setIsLoading(true);
    try {
      const res = await fetch('/api/agent-status', { cache: 'no-store' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.error ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setJobs(data.jobs ?? []);
      setFetchedAt(data.fetchedAt ?? null);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load agent status');
    } finally {
      if (withSpinner) setIsLoading(false);
    }
  }

  useEffect(() => {
    fetchStatus(true);
    intervalRef.current = setInterval(() => fetchStatus(false), REFRESH_INTERVAL_MS);
    return () => {
      if (intervalRef.current !== null) clearInterval(intervalRef.current);
    };
  }, []);

  const groups = groupByDomain(jobs);
  const totalFailed = jobs.filter(j => j.status === 'failed').length;
  const totalUnknown = jobs.filter(j => j.status === 'unknown').length;

  const summaryRight = fetchedAt
    ? `Refreshes every 30s · Updated ${relativeTime(fetchedAt)}`
    : 'Refreshes every 30s';

  return (
    <WorkbenchShell
      title="Agent & Job Status"
      eyebrow="Platform Operations"
      tagline="USS TJR · Agent Status · Scheduler job state from domain_heartbeats — auto-refreshes every 30s"
      right={<span className="hidden sm:inline">{summaryRight}</span>}
    >
      <div className="flex flex-col gap-4">
        {/* Summary strip */}
        <Card>
          {isLoading ? (
            <p className="text-[13px] italic text-wb-ink2">Loading agent status…</p>
          ) : loadError ? (
            <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
              <p className="text-[13px] font-semibold text-wb-crit-on">Failed to load agent status</p>
              <p className="mt-1 text-[12px] text-wb-ink2">{loadError}</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
                <p className="text-2xl font-bold text-wb-ink">{jobs.length}</p>
                <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Total Jobs</p>
              </div>
              <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
                <p className="text-2xl font-bold text-state-ok-on">{jobs.filter(j => j.status === 'ok').length}</p>
                <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Healthy</p>
              </div>
              <div className={`rounded-md border p-3 text-center ${totalFailed > 0 ? 'border-state-crit/40 bg-state-crit/10' : 'border-wb-line bg-wb-bg'}`}>
                <p className={`text-2xl font-bold ${totalFailed > 0 ? 'text-state-crit-on' : 'text-wb-ink'}`}>{totalFailed}</p>
                <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Failed</p>
              </div>
              <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
                <p className="text-2xl font-bold text-state-unknown-on">{totalUnknown}</p>
                <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Unknown</p>
              </div>
            </div>
          )}
        </Card>

        {/* Per-domain job tables */}
        {!isLoading && !loadError && Array.from(groups.entries()).map(([domain, domainJobs]) => (
          <DomainSection key={domain} domain={domain} jobs={domainJobs} />
        ))}
      </div>
    </WorkbenchShell>
  );
}
