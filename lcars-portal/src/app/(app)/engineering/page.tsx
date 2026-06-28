'use client';

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import type { StatusTone } from '@/lib/types';

// ── Types ─────────────────────────────────────────────────────────────────────

interface BuildRequest {
  request_id: string;
  title: string;
  summary: string | null;
  status: string;
  source: string | null;
  created_at: string;
}

interface AgentPerf {
  task_type: string;
  success: boolean;
  cost_usd: number | null;
  tokens_used: number | null;
  time_to_pr_seconds: number | null;
  created_at: string;
}

interface BatchJob {
  batch_id: string;
  status: string;
  total_requests: number | null;
  succeeded_requests: number | null;
  failed_requests: number | null;
  created_at: string;
  completed_at: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const BUILD_STATUS_TONE: Record<string, StatusTone> = {
  engineering_running:   'command',
  engineering_delivered: 'status',
  pending:               'neutral',
  approved:              'status',
  rejected:              'operations',
};

function buildTone(status: string): StatusTone {
  return BUILD_STATUS_TONE[status] ?? 'neutral';
}

function buildLabel(status: string): string {
  return status.replace('engineering_', '').replace(/_/g, ' ').toUpperCase();
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return '—';
  return new Date(ts).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

function fmtDuration(s: number | null | undefined): string {
  if (!s) return '—';
  if (s < 60) return `${s}s`;
  return `${Math.round(s / 60)}m`;
}

// ── Cognitive Load Reduction (D-055) ─────────────────────────────────────────

function cogLoadScore(perfs: AgentPerf[], jobs: BatchJob[], requests: BuildRequest[]): {
  score: number;
  label: string;
  tone: StatusTone;
  signals: { label: string; value: string; contribution: string }[];
} {
  // Automation success rate (0-40 pts)
  const successRate = perfs.length
    ? perfs.filter(p => p.success).length / perfs.length
    : 0;
  const automationPts = Math.round(successRate * 40);

  // Batch throughput (0-30 pts)
  const totalBatchReqs = jobs.reduce((s, j) => s + (j.total_requests ?? 0), 0);
  const succeededBatch = jobs.reduce((s, j) => s + (j.succeeded_requests ?? 0), 0);
  const batchRate = totalBatchReqs > 0 ? succeededBatch / totalBatchReqs : 0;
  const batchPts = Math.round(batchRate * 30);

  // Build pipeline activity (0-30 pts) — delivered or approved = friction removed
  const delivered = requests.filter(r => ['engineering_delivered', 'approved'].includes(r.status)).length;
  const pipelinePts = requests.length > 0 ? Math.round(Math.min(delivered / requests.length, 1) * 30) : 0;

  const score = automationPts + batchPts + pipelinePts;
  const label = score >= 80 ? 'High reduction' : score >= 50 ? 'Moderate reduction' : score >= 25 ? 'Low reduction' : 'Insufficient data';
  const tone: StatusTone = score >= 80 ? 'status' : score >= 50 ? 'command' : score >= 25 ? 'operations' : 'neutral';

  return {
    score,
    label,
    tone,
    signals: [
      {
        label: 'Automation success',
        value: perfs.length ? `${Math.round(successRate * 100)}%` : '—',
        contribution: `${automationPts} / 40 pts`,
      },
      {
        label: 'Batch throughput',
        value: totalBatchReqs > 0 ? `${Math.round(batchRate * 100)}%` : '—',
        contribution: `${batchPts} / 30 pts`,
      },
      {
        label: 'Pipeline delivery',
        value: requests.length > 0 ? `${delivered} / ${requests.length}` : '—',
        contribution: `${pipelinePts} / 30 pts`,
      },
    ],
  };
}

function CognitiveLoadPanel({ perfs, jobs, requests }: { perfs: AgentPerf[]; jobs: BatchJob[]; requests: BuildRequest[] }) {
  const { score, label, tone, signals } = cogLoadScore(perfs, jobs, requests);
  const hasData = perfs.length > 0 || jobs.length > 0 || requests.length > 0;

  return (
    <LCARSPanel
      title="Cognitive Load Reduction"
      accent="engineering"
      eyebrow="D-055 · Chief Engineer mandate — reduce friction, return time to Captain"
      actions={hasData ? <StatusBadge label={label} tone={tone} /> : undefined}
    >
      <p className="mb-4 text-xs text-lcars-muted leading-relaxed">
        Chief Engineer mandate: reduce cognitive load through automation and simplification.
        This score measures how effectively the engineering system is removing decision overhead
        and returning time and energy to Captain TJR.
      </p>

      {!hasData ? (
        <p className="text-sm text-lcars-muted italic">No engineering data available yet.</p>
      ) : (
        <>
          {/* Score hero */}
          <div className="mb-4 flex items-center gap-4 rounded-lcars border border-engineering/40 bg-engineering/5 px-5 py-4">
            <span className="font-lcars text-5xl font-bold text-engineering-on">{score}</span>
            <div>
              <p className="font-lcars text-sm font-semibold uppercase tracking-wider text-engineering-on">{label}</p>
              <p className="text-xs text-lcars-muted mt-0.5">out of 100</p>
            </div>
            <div className="flex-1 ml-4">
              <div className="h-3 rounded-full bg-edge/30 overflow-hidden">
                <div
                  className="h-full rounded-full bg-engineering transition-all"
                  style={{ width: `${score}%` }}
                />
              </div>
            </div>
          </div>

          {/* Signal breakdown */}
          <div className="grid gap-2 sm:grid-cols-3">
            {signals.map((s) => (
              <div key={s.label} className="rounded-lcars border border-edge bg-space/40 p-3">
                <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{s.label}</p>
                <p className="font-lcars text-lg font-bold text-engineering-on mt-0.5">{s.value}</p>
                <p className="text-[10px] text-lcars-muted mt-0.5">{s.contribution}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </LCARSPanel>
  );
}

// ── Build Request Inbox ───────────────────────────────────────────────────────

function BuildInbox({ requests }: { requests: BuildRequest[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (!requests.length) {
    return <p className="text-xs text-lcars-muted italic">No build requests found.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {requests.map((r) => {
        const tone = buildTone(r.status);
        const isOpen = expanded === r.request_id;
        return (
          <div key={r.request_id} className="rounded-lcars border border-edge bg-panel-2/60">
            <div className="flex flex-wrap items-start gap-3 p-3">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-lcars-text leading-snug">{r.title}</p>
                <p className="text-[10px] text-lcars-muted mt-0.5">{fmt(r.created_at)}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <StatusBadge label={buildLabel(r.status)} tone={tone} />
                {r.summary && (
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : r.request_id)}
                    className="rounded-md border border-edge px-2 py-1 text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:border-command hover:text-command-on transition-colors"
                  >
                    {isOpen ? 'Less' : 'More'}
                  </button>
                )}
              </div>
            </div>
            {isOpen && r.summary && (
              <div className="border-t border-edge px-3 pb-3 pt-2">
                <p className="text-xs leading-relaxed text-lcars-text/80">{r.summary}</p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Agent Performance ─────────────────────────────────────────────────────────

function AgentPerformancePanel({ perfs }: { perfs: AgentPerf[] }) {
  if (!perfs.length) return null;

  const successCount = perfs.filter((p) => p.success).length;
  const totalCost = perfs.reduce((a, p) => a + (p.cost_usd ?? 0), 0);

  return (
    <LCARSPanel title="Agent Performance" accent="engineering" eyebrow="Recent task telemetry">
      <div className="mb-4 grid grid-cols-3 gap-3">
        <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Tasks</p>
          <p className="font-lcars text-xl font-bold text-engineering-on mt-0.5">{perfs.length}</p>
        </div>
        <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Success rate</p>
          <p className="font-lcars text-xl font-bold text-status-on mt-0.5">
            {Math.round((successCount / perfs.length) * 100)}%
          </p>
        </div>
        <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Total cost</p>
          <p className="font-lcars text-xl font-bold text-command-on mt-0.5">
            ${totalCost.toFixed(3)}
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {perfs.map((p, i) => (
          <div key={i} className="flex flex-wrap items-center gap-3 rounded-lcars border border-edge bg-space/40 px-3 py-2">
            <StatusBadge label={p.success ? 'OK' : 'FAIL'} tone={p.success ? 'status' : 'operations'} />
            <span className="text-xs text-lcars-text flex-1 min-w-0 truncate">{p.task_type}</span>
            <div className="flex gap-3 text-[10px] text-lcars-muted shrink-0">
              {p.tokens_used && <span>{p.tokens_used.toLocaleString()} tok</span>}
              {p.cost_usd != null && <span>${p.cost_usd.toFixed(3)}</span>}
              {p.time_to_pr_seconds && <span>{fmtDuration(p.time_to_pr_seconds)}</span>}
            </div>
          </div>
        ))}
      </div>
    </LCARSPanel>
  );
}

// ── Batch Jobs ────────────────────────────────────────────────────────────────

function BatchJobsPanel({ jobs }: { jobs: BatchJob[] }) {
  if (!jobs.length) return null;

  return (
    <LCARSPanel title="Batch Jobs" accent="engineering" eyebrow="Recent batch job runs">
      <div className="flex flex-col gap-2">
        {jobs.map((j) => {
          const tone: StatusTone =
            j.status === 'completed' ? 'status' :
            j.status === 'running'   ? 'command' :
            j.status === 'failed'    ? 'operations' : 'neutral';
          const pct = j.total_requests
            ? Math.round(((j.succeeded_requests ?? 0) / j.total_requests) * 100)
            : null;
          return (
            <div key={j.batch_id} className="rounded-lcars border border-edge bg-panel-2/60 p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-mono text-xs text-lcars-text">{j.batch_id}</p>
                  <p className="text-[10px] text-lcars-muted mt-0.5">{fmt(j.created_at)}</p>
                </div>
                <StatusBadge label={j.status.toUpperCase()} tone={tone} />
              </div>
              {j.total_requests != null && (
                <div className="mt-2 flex gap-3 text-[10px] text-lcars-muted">
                  <span>{j.total_requests} total</span>
                  <span className="text-status-on">{j.succeeded_requests ?? 0} ok</span>
                  {(j.failed_requests ?? 0) > 0 && (
                    <span className="text-operations-on">{j.failed_requests} failed</span>
                  )}
                  {pct != null && <span className="ml-auto">{pct}%</span>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </LCARSPanel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function EngineeringPage() {
  const [requests, setRequests]  = useState<BuildRequest[]>([]);
  const [perfs,    setPerfs]     = useState<AgentPerf[]>([]);
  const [jobs,     setJobs]      = useState<BatchJob[]>([]);
  const [isLive,   setIsLive]    = useState(false);
  const [loading,  setLoading]   = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const supabase = createSupabaseBrowserClient();
        const [reqRes, perfRes, jobRes] = await Promise.all([
          supabase
            .from('build_request_inbox')
            .select('request_id, title, summary, status, source, created_at')
            .order('created_at', { ascending: false })
            .limit(10),
          supabase
            .from('agent_performance')
            .select('task_type, success, cost_usd, tokens_used, time_to_pr_seconds, created_at')
            .order('created_at', { ascending: false })
            .limit(10),
          supabase
            .from('batch_jobs')
            .select('batch_id, status, total_requests, succeeded_requests, failed_requests, created_at, completed_at')
            .order('created_at', { ascending: false })
            .limit(8),
        ]);
        if (reqRes.data?.length) { setRequests(reqRes.data as BuildRequest[]); setIsLive(true); }
        if (perfRes.data?.length) setPerfs(perfRes.data as AgentPerf[]);
        if (jobRes.data?.length)  setJobs(jobRes.data as BatchJob[]);
      } catch {
        // fall through to empty state
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Engineering Deck"
        accent="engineering"
        eyebrow="Build Pipeline · Agent Runtime"
      >
        <p className="text-xs text-lcars-muted">
          Live build request inbox, agent performance telemetry, and batch job status.
        </p>
        <p className="mt-2 text-[10px] uppercase tracking-wider text-lcars-muted">
          {loading ? 'Loading…' : isLive ? '● Live · Supabase' : '○ No data'}
        </p>
      </LCARSPanel>

      <CognitiveLoadPanel perfs={perfs} jobs={jobs} requests={requests} />

      <LCARSPanel
        title="Build Request Inbox"
        accent="engineering"
        eyebrow={loading ? 'Loading…' : `${requests.length} requests`}
      >
        <BuildInbox requests={requests} />
      </LCARSPanel>

      <AgentPerformancePanel perfs={perfs} />

      <BatchJobsPanel jobs={jobs} />
    </div>
  );
}
