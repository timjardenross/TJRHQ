'use client';

// Moved out of the (app) route group and off its bespoke dark
// "bg-space/lcars-amber" theme onto the shared WorkbenchShell/wb-* design
// system, 2026-09-06 — a Captain walkthrough of the new Settings page
// (AI & Automation → Advanced → "View current model routing") surfaced
// this page as visibly the odd one out: a fully dark, third visual system
// rendered inside the (app) group's light LCARS chrome. Same data, same
// refresh behaviour — /api/model/status and /api/model/recent-calls are
// unchanged; only the presentation moved onto Card/Badge/WorkbenchShell.
import { useEffect, useState, useCallback } from 'react';
import { Badge, Card, WorkbenchShell, type BadgeStatus } from '@/components/ui';

interface LoadedModel {
  name: string;
  size_vram?: number;
  expires_at?: string;
}

interface RoutingPolicyEntry {
  task_type: string;
  model: string;
  keep_alive: string;
}

interface RouterStatus {
  ollama_url?: string;
  ollama_reachable?: boolean;
  loaded_models?: LoadedModel[];
  available_models?: string[];
  router_port?: number;
  recent_avg_ms?: number | null;
  recent_failed?: number;
  routing_policy?: RoutingPolicyEntry[];
  error?: string;
}

// Editorial annotations for routing behaviours that are not machine-readable
// from the backend's TASK_POLICY (escalation / fallback logic lives in code).
// The task→model→keep_alive mapping itself is rendered from live status data,
// so these notes never carry the model names that previously drifted.
const ROUTING_NOTES: Record<string, string> = {
  'classify-capture': 'auto-escalates to the large model if build/risk/health triggers detected',
  'embed': 'semantic search embeddings',
  'intelligence-brief': 'morning brief synthesis',
  'intelligence-signals': 'proactive signals analysis',
  'xo-response': 'XO chat reasoning',
  'fallback-complex': 'cloud fallback, no local keep_alive',
  'escalate': 'forced large-model path',
  'engineering-review': 'falls back to the cloud model if the code model is not installed',
};

interface CallEntry {
  ts: string;
  task_type: string;
  model: string;
  keep_alive: string;
  duration_ms: number;
  escalated: boolean;
  escalation_reason?: string;
  prompt_len?: number;
  response_len?: number;
  success: boolean;
  error?: string;
}

const MODEL_SHORT: Record<string, string> = {
  'gemma3:4b': 'gemma3:4b',
  'mistral-small3.2:24b': 'mistral-sm',
  'gemma3:12b': 'gemma3:12b',
  'nomic-embed-text': 'nomic-embed',
};

function fmt(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return ts;
  }
}

function fmtBytes(b?: number): string {
  if (!b) return '—';
  return b > 1_000_000_000 ? `${(b / 1_000_000_000).toFixed(1)}GB` : `${(b / 1_000_000).toFixed(0)}MB`;
}

export default function ModelCrewPage() {
  const [status, setStatus] = useState<RouterStatus | null>(null);
  const [calls, setCalls] = useState<CallEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, callsRes] = await Promise.all([
        fetch('/api/model/status', { cache: 'no-store' }),
        fetch('/api/model/recent-calls?n=30', { cache: 'no-store' }),
      ]);
      const statusData = await statusRes.json();
      const callsData = await callsRes.json();
      setStatus(statusData);
      setCalls(callsData.calls ?? []);
      setLastRefresh(new Date());
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = setInterval(() => void refresh(), 30_000);
    return () => clearInterval(interval);
  }, [refresh]);

  const reachable = status?.ollama_reachable ?? false;
  const loaded = status?.loaded_models ?? [];
  const available = status?.available_models ?? [];
  const routingPolicy = status?.routing_policy ?? [];
  const successCalls = calls.filter((c) => c.success);
  const avgMs = successCalls.length
    ? Math.round(successCalls.reduce((s, c) => s + c.duration_ms, 0) / successCalls.length)
    : null;
  const failedCount = calls.filter((c) => !c.success).length;
  const escalatedCount = calls.filter((c) => c.escalated).length;

  return (
    <WorkbenchShell
      title="Model Crew"
      eyebrow="On-call Ollama crew — local model routing & status"
      tagline="TJR HQ · Model Crew — read-only routing status. For failures, escalations and job health over time, see HQ Status."
      right={
        <>
          {lastRefresh && (
            <span>refreshed {lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
          )}
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="rounded-md border border-wb-line px-3 py-1.5 text-[12px] text-wb-ink2 transition-colors hover:border-wb-sage-deep hover:text-wb-ink disabled:opacity-40"
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </>
      }
    >
      {error && (
        <Card variant="outlined" className="mb-6 border-wb-crit text-[13px] text-wb-crit-on">
          Router unreachable: {error}
        </Card>
      )}

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card>
          <div className="text-[10px] uppercase tracking-wider text-wb-ink2">Ollama</div>
          <div className="mt-1">
            <Badge status={reachable ? 'success' : 'error'}>{reachable ? 'Online' : 'Offline'}</Badge>
          </div>
          <div className="mt-1 truncate text-[11px] text-wb-ink2">{status?.ollama_url ?? '—'}</div>
        </Card>

        <Card>
          <div className="text-[10px] uppercase tracking-wider text-wb-ink2">Loaded</div>
          <div className="mt-1 text-lg font-semibold text-wb-ink">{loaded.length}</div>
          <div className="text-[11px] text-wb-ink2">{loaded.map((m) => MODEL_SHORT[m.name] ?? m.name).join(', ') || 'none'}</div>
        </Card>

        <Card>
          <div className="text-[10px] uppercase tracking-wider text-wb-ink2">Avg Response</div>
          <div className="mt-1 text-lg font-semibold text-wb-ink">{avgMs != null ? `${avgMs}ms` : '—'}</div>
          <div className="text-[11px] text-wb-ink2">last {successCalls.length} calls</div>
        </Card>

        <Card>
          <div className="text-[10px] uppercase tracking-wider text-wb-ink2">Failed / Escalated</div>
          <div className="mt-1 text-lg font-semibold">
            <span className={failedCount > 0 ? 'text-wb-crit-on' : 'text-wb-ink2'}>{failedCount}</span>
            <span className="mx-1 text-wb-ink2">/</span>
            <span className={escalatedCount > 0 ? 'text-wb-warn-on' : 'text-wb-ink2'}>{escalatedCount}</span>
          </div>
          <div className="text-[11px] text-wb-ink2">recent {calls.length} calls</div>
        </Card>
      </div>

      {loaded.length > 0 && (
        <Card title="Currently Loaded" className="mb-6">
          <div className="flex flex-col gap-2">
            {loaded.map((m) => (
              <div key={m.name} className="flex items-center justify-between text-[13px]">
                <span className="font-mono text-wb-ink">{m.name}</span>
                <div className="flex items-center gap-4 text-[11px] text-wb-ink2">
                  {m.size_vram != null && <span>VRAM: {fmtBytes(m.size_vram)}</span>}
                  {m.expires_at && <span>expires: {fmt(m.expires_at)}</span>}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {available.length > 0 && (
        <Card title="Available Models" className="mb-6">
          <div className="flex flex-wrap gap-2">
            {available.map((m) => (
              <span key={m} className="rounded-md border border-wb-line bg-wb-surface-raised px-2 py-1 font-mono text-[11px] text-wb-ink2">
                {m}
              </span>
            ))}
          </div>
        </Card>
      )}

      <Card title="Routing Policy" className="mb-6">
        {routingPolicy.length > 0 ? (
          <div className="grid grid-cols-1 gap-2 text-[12px] md:grid-cols-2">
            {routingPolicy.map((row) => (
              <div key={row.task_type} className="flex items-start gap-3">
                <span className="font-mono text-wb-ink">{row.task_type}</span>
                <span className="text-wb-ink2">
                  → {MODEL_SHORT[row.model] ?? row.model} [{row.keep_alive === '0' ? '—' : row.keep_alive}]
                </span>
                {ROUTING_NOTES[row.task_type] && <span className="text-wb-ink2/70">{ROUTING_NOTES[row.task_type]}</span>}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[13px] text-wb-ink2">
            Routing policy is defined in the model router backend (TASK_POLICY) and is only shown here when the router is
            reachable. It is not currently available.
          </p>
        )}
      </Card>

      <Card title={`Recent Calls (${calls.length})`}>
        {calls.length === 0 ? (
          <p className="text-[13px] text-wb-ink2">No calls logged yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-wb-line">
                  <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Time</th>
                  <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Task</th>
                  <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Model</th>
                  <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Duration</th>
                  <th className="pb-2 pr-4 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Status</th>
                  <th className="pb-2 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Notes</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((c, i) => {
                  const statusBadge: BadgeStatus = c.success ? 'success' : 'error';
                  return (
                    <tr key={i} className="border-b border-wb-line last:border-0">
                      <td className="py-2 pr-4 font-mono text-[12px] text-wb-ink2">{fmt(c.ts)}</td>
                      <td className="py-2 pr-4 font-mono text-[12px] text-wb-ink">{c.task_type}</td>
                      <td className="py-2 pr-4 font-mono text-[12px] text-wb-ink2">{MODEL_SHORT[c.model] ?? c.model}</td>
                      <td className="py-2 pr-4 text-[12px] text-wb-ink">{c.duration_ms}ms</td>
                      <td className="py-2 pr-4">
                        <Badge status={statusBadge}>{c.success ? 'OK' : 'Failed'}</Badge>
                      </td>
                      <td className="py-2 text-[12px] text-wb-ink2">
                        {c.escalated && (
                          <span className="mr-2 text-wb-warn-on" title={c.escalation_reason}>
                            ⬆ escalated
                          </span>
                        )}
                        {c.error && <span className="block max-w-xs truncate text-wb-crit-on/80">{c.error}</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </WorkbenchShell>
  );
}
