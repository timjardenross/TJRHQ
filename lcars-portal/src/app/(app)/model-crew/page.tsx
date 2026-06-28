'use client';

import { useEffect, useState, useCallback } from 'react';

interface LoadedModel {
  name: string;
  size_vram?: number;
  expires_at?: string;
}

interface RouterStatus {
  ollama_url?: string;
  ollama_reachable?: boolean;
  loaded_models?: LoadedModel[];
  available_models?: string[];
  router_port?: number;
  recent_avg_ms?: number | null;
  recent_failed?: number;
  error?: string;
}

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

const TASK_COLOR: Record<string, string> = {
  'classify-capture': 'text-yellow-400',
  'summarise-note': 'text-blue-400',
  'intelligence-brief': 'text-purple-400',
  'intelligence-signals': 'text-violet-400',
  'xo-response': 'text-cyan-400',
  'embed': 'text-green-400',
  'escalate': 'text-red-400',
  'fallback-complex': 'text-gray-400',
  'engineering-review': 'text-orange-400',
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
  const successCalls = calls.filter(c => c.success);
  const avgMs = successCalls.length
    ? Math.round(successCalls.reduce((s, c) => s + c.duration_ms, 0) / successCalls.length)
    : null;
  const failedCount = calls.filter(c => !c.success).length;
  const escalatedCount = calls.filter(c => c.escalated).length;

  return (
    <div className="min-h-screen bg-space text-lcars-text p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-lcars-amber">Model Crew</h1>
          <p className="text-lcars-muted text-sm mt-1">On-call Ollama crew — local model routing &amp; status</p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-xs text-lcars-muted">
              refreshed {lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )}
          <button
            onClick={() => void refresh()}
            disabled={loading}
            className="px-4 py-2 rounded border border-edge text-sm text-lcars-muted hover:border-lcars-amber hover:text-lcars-amber transition-colors disabled:opacity-40"
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div className="border border-red-800 bg-red-950/40 rounded p-3 text-red-400 text-sm">
          Router unreachable: {error}
        </div>
      )}

      {/* Status cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="border border-edge rounded p-4 space-y-1">
          <div className="text-xs text-lcars-muted uppercase tracking-wider">Ollama</div>
          <div className={`text-lg font-bold ${reachable ? 'text-green-400' : 'text-red-400'}`}>
            {reachable ? 'Online' : 'Offline'}
          </div>
          <div className="text-xs text-lcars-muted">{status?.ollama_url ?? '—'}</div>
        </div>

        <div className="border border-edge rounded p-4 space-y-1">
          <div className="text-xs text-lcars-muted uppercase tracking-wider">Loaded</div>
          <div className="text-lg font-bold text-lcars-amber">{loaded.length}</div>
          <div className="text-xs text-lcars-muted">
            {loaded.map(m => MODEL_SHORT[m.name] ?? m.name).join(', ') || 'none'}
          </div>
        </div>

        <div className="border border-edge rounded p-4 space-y-1">
          <div className="text-xs text-lcars-muted uppercase tracking-wider">Avg Response</div>
          <div className="text-lg font-bold text-cyan-400">{avgMs != null ? `${avgMs}ms` : '—'}</div>
          <div className="text-xs text-lcars-muted">last {successCalls.length} calls</div>
        </div>

        <div className="border border-edge rounded p-4 space-y-1">
          <div className="text-xs text-lcars-muted uppercase tracking-wider">Failed / Escalated</div>
          <div className="text-lg font-bold">
            <span className={failedCount > 0 ? 'text-red-400' : 'text-lcars-muted'}>{failedCount}</span>
            <span className="text-lcars-muted mx-1">/</span>
            <span className={escalatedCount > 0 ? 'text-yellow-400' : 'text-lcars-muted'}>{escalatedCount}</span>
          </div>
          <div className="text-xs text-lcars-muted">recent {calls.length} calls</div>
        </div>
      </div>

      {/* Loaded models detail */}
      {loaded.length > 0 && (
        <div className="border border-edge rounded p-4">
          <h2 className="text-sm font-semibold text-lcars-muted uppercase tracking-wider mb-3">Currently Loaded</h2>
          <div className="space-y-2">
            {loaded.map(m => (
              <div key={m.name} className="flex items-center justify-between text-sm">
                <span className="text-lcars-text font-mono">{m.name}</span>
                <div className="flex items-center gap-4 text-lcars-muted text-xs">
                  {m.size_vram != null && <span>VRAM: {fmtBytes(m.size_vram)}</span>}
                  {m.expires_at && <span>expires: {fmt(m.expires_at)}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Available models */}
      {available.length > 0 && (
        <div className="border border-edge rounded p-4">
          <h2 className="text-sm font-semibold text-lcars-muted uppercase tracking-wider mb-3">Available Models</h2>
          <div className="flex flex-wrap gap-2">
            {available.map(m => (
              <span key={m} className="px-2 py-1 rounded bg-space/60 border border-edge text-xs font-mono text-lcars-muted">
                {m}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Routing policy */}
      <div className="border border-edge rounded p-4">
        <h2 className="text-sm font-semibold text-lcars-muted uppercase tracking-wider mb-3">Routing Policy</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
          {[
            { task: 'classify-capture', model: 'gemma4:12b', ka: '5m', note: 'auto-escalates to mistral-sm if build/risk/health detected' },
            { task: 'summarise-note', model: 'gemma4:12b', ka: '5m', note: 'fast summary' },
            { task: 'xo-response', model: 'gemma4:12b', ka: '10m', note: 'XO chat reasoning' },
            { task: 'intelligence-brief', model: 'mistral-sm', ka: '15m', note: 'morning brief synthesis' },
            { task: 'intelligence-signals', model: 'mistral-sm', ka: '10m', note: 'proactive signals analysis' },
            { task: 'embed', model: 'nomic-embed', ka: '1m', note: 'semantic search' },
            { task: 'fallback-complex', model: 'glm-5.2:cloud', ka: '—', note: 'cloud fallback, no local keep_alive' },
            { task: 'engineering-review', model: 'qwen3-coder:30b', ka: '10m', note: 'falls back to glm-5.2:cloud if not installed' },
            { task: 'escalate', model: 'mistral-sm', ka: '15m', note: 'forced large model path' },
          ].map(row => (
            <div key={row.task} className="flex items-start gap-3">
              <span className={`font-mono ${TASK_COLOR[row.task] ?? 'text-lcars-text'}`}>{row.task}</span>
              <span className="text-lcars-muted">→ {row.model} [{row.ka}]</span>
              <span className="text-lcars-muted/60">{row.note}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Recent calls */}
      <div className="border border-edge rounded p-4">
        <h2 className="text-sm font-semibold text-lcars-muted uppercase tracking-wider mb-3">
          Recent Calls ({calls.length})
        </h2>
        {calls.length === 0 ? (
          <p className="text-lcars-muted text-sm">No calls logged yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-lcars-muted border-b border-edge">
                  <th className="text-left py-2 pr-4 font-normal">Time</th>
                  <th className="text-left py-2 pr-4 font-normal">Task</th>
                  <th className="text-left py-2 pr-4 font-normal">Model</th>
                  <th className="text-left py-2 pr-4 font-normal">Duration</th>
                  <th className="text-left py-2 pr-4 font-normal">Status</th>
                  <th className="text-left py-2 font-normal">Notes</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((c, i) => (
                  <tr key={i} className="border-b border-edge/30 hover:bg-white/5">
                    <td className="py-1.5 pr-4 font-mono text-lcars-muted">{fmt(c.ts)}</td>
                    <td className={`py-1.5 pr-4 font-mono ${TASK_COLOR[c.task_type] ?? 'text-lcars-text'}`}>
                      {c.task_type}
                    </td>
                    <td className="py-1.5 pr-4 font-mono text-lcars-muted">
                      {MODEL_SHORT[c.model] ?? c.model}
                    </td>
                    <td className="py-1.5 pr-4 text-lcars-text">{c.duration_ms}ms</td>
                    <td className="py-1.5 pr-4">
                      {c.success
                        ? <span className="text-green-400">✓</span>
                        : <span className="text-red-400" title={c.error}>✗</span>}
                    </td>
                    <td className="py-1.5 text-lcars-muted">
                      {c.escalated && (
                        <span className="text-yellow-400 mr-2" title={c.escalation_reason}>⬆ escalated</span>
                      )}
                      {c.error && <span className="text-red-400/70 truncate max-w-xs block">{c.error}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
