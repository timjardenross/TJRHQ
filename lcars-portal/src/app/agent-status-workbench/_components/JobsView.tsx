'use client';

/**
 * Automations tab (formerly "Jobs") — the detailed scheduler/job table
 * (spec §11-§12): per-domain job state from domain_heartbeats, now also
 * showing which HQ Status capability each job feeds and its criticality,
 * so a failure here can be read against the interpreted Status tab instead
 * of in isolation. Behaviour otherwise unchanged: same 30s auto-refresh,
 * same grouping, same tone/badge mapping.
 */

import { useEffect, useRef, useState } from 'react';
import { Badge, Card } from '@/components/ui';
import { stateToneClasses } from '@/lib/departments';
import type { AgentStatusEntry } from '@/app/api/agent-status/route';
import { CAPABILITIES } from '@/lib/hqStatusInterpreter';
import { relativeTime, jobStatusToTone, jobStatusToBadge, jobStatusLabel } from './shared';

const CAPABILITY_LABEL_BY_KEY = new Map(CAPABILITIES.map((c) => [c.key, c.label]));

const CRITICALITY_LABEL: Record<AgentStatusEntry['criticality'], string> = {
  critical: 'Critical',
  important: 'Important',
  supporting: 'Supporting',
  background: 'Background',
};

const REFRESH_INTERVAL_MS = 30_000;

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
  intelligence: 'Intelligence',
  health: 'Health',
  'human-systems': 'Human Systems',
  platform: 'Platform',
  'emergency-alerts': 'Emergency Alert Hub',
};

function JobRow({ job }: { job: AgentStatusEntry }) {
  const tone = jobStatusToTone(job.status);
  const classes = stateToneClasses(tone);

  return (
    <tr className="border-b border-wb-line last:border-0">
      <td className="py-3 pr-4">
        <div className="flex items-center gap-2.5">
          <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${classes.dot}`} aria-hidden />
          <div>
            <span className="text-[13px] font-medium text-wb-ink">{job.label}</span>
            <div className="text-[10px] text-wb-ink2/70">
              {CAPABILITY_LABEL_BY_KEY.get(job.capability) ?? job.capability} · {CRITICALITY_LABEL[job.criticality]}
            </div>
          </div>
        </div>
      </td>
      <td className="py-3 pr-4">
        <Badge status={jobStatusToBadge(job.status)}>{jobStatusLabel(job.status)}</Badge>
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
  const failedCount = jobs.filter((j) => j.status === 'failed').length;

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between border-b border-wb-line pb-3">
        <div>
          <h2 className="font-serif text-lg text-wb-ink">{label}</h2>
          <p className="text-[11px] uppercase tracking-wide text-wb-ink2">
            {jobs.length} job{jobs.length !== 1 ? 's' : ''}
            {failedCount > 0 && <span className="ml-2 text-state-crit-on">{failedCount} failed</span>}
          </p>
        </div>
        {failedCount > 0 && <Badge status="error">{failedCount} Failed</Badge>}
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
            {jobs.map((job) => <JobRow key={job.domainKey} job={job} />)}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function JobsView() {
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
  const totalFailed = jobs.filter((j) => j.status === 'failed').length;
  const totalUnknown = jobs.filter((j) => j.status === 'unknown').length;
  const totalNonLive = jobs.filter((j) => j.status === 'retired' || j.status === 'disabled').length;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[11px] text-wb-ink2">
        Scheduler job state from domain_heartbeats — auto-refreshes every 30s
        {fetchedAt && <> · Updated {relativeTime(fetchedAt)}</>}
      </p>

      <Card>
        {isLoading ? (
          <p className="text-[13px] italic text-wb-ink2">Loading agent status…</p>
        ) : loadError ? (
          <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
            <p className="text-[13px] font-semibold text-wb-crit-on">Failed to load agent status</p>
            <p className="mt-1 text-[12px] text-wb-ink2">{loadError}</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
              <p className="text-2xl font-bold text-wb-ink">{jobs.length}</p>
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Total Jobs</p>
            </div>
            <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
              <p className="text-2xl font-bold text-state-ok-on">{jobs.filter((j) => j.status === 'ok').length}</p>
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
            <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
              <p className="text-2xl font-bold text-wb-ink2">{totalNonLive}</p>
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Retired / Disabled</p>
            </div>
          </div>
        )}
      </Card>

      {!isLoading && !loadError && Array.from(groups.entries()).map(([domain, domainJobs]) => (
        <DomainSection key={domain} domain={domain} jobs={domainJobs} />
      ))}
    </div>
  );
}
