'use client';

import { useEffect, useState } from 'react';
import { PILLAR_LABEL, DOMAIN_BADGE, type Domain } from './shared';

interface Signal {
  event_id: string;
  raw_title: string;
  source_name: string | null;
  pillar_key: string;
  pillar_name: string | null;
  rank_score: number;
  captain_focus: boolean;
  suggested_angle: string | null;
  domain: 'health' | 'operational';
  canonical_url: string | null;
}

function RankBadge({ score }: { score: number }) {
  const cls = score > 0.8 ? 'bg-green-500/15 text-green-600' : score > 0.7 ? 'bg-yellow-500/15 text-yellow-700' : 'bg-red-500/10 text-red-500';
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-mono font-medium ${cls}`}>{score.toFixed(2)}</span>;
}

function SignalCard({ signal, selected, onToggle }: { signal: Signal; selected: boolean; onToggle: () => void }) {
  return (
    <label className="flex items-start gap-3 rounded-lcars border border-[#d9e1f0] bg-white/30 p-3 cursor-pointer hover:bg-white/50 transition-colors">
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        aria-label={`Select signal: ${signal.raw_title}`}
        className="mt-1"
      />
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap gap-2 items-center mb-1">
          <RankBadge score={signal.rank_score} />
          <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${DOMAIN_BADGE[signal.domain]}`}>
            {signal.domain === 'health' ? 'Health' : 'Operational'}
          </span>
          <span className="text-[10px] text-[#61718c]">
            {PILLAR_LABEL[signal.pillar_key] ?? signal.pillar_name ?? signal.pillar_key}
          </span>
          {signal.captain_focus && (
            <span className="text-[10px] text-amber-600">⭐ Captain Priority</span>
          )}
        </div>
        <p className="font-medium text-sm text-[#18223a] leading-snug">{signal.raw_title}</p>
        {signal.suggested_angle && (
          <p className="text-xs text-[#61718c] italic mt-0.5 line-clamp-2">{signal.suggested_angle}</p>
        )}
        <p className="text-[10px] text-[#61718c]/70 mt-1">
          Source: {signal.source_name ?? '—'}
          {signal.canonical_url && (
            <>
              {' · '}
              <a href={signal.canonical_url} target="_blank" rel="noopener noreferrer" className="text-[#243b7a] hover:underline">
                View source ↗
              </a>
            </>
          )}
        </p>
      </div>
    </label>
  );
}

function BatchPreviewModal({
  signalIds,
  onClose,
  onCreated,
}: {
  signalIds: string[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);

  async function handleCreate() {
    setBusy(true);
    try {
      const res = await fetch('/api/content/signals-to-opportunities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signal_ids: signalIds }),
      });
      const data = await res.json();
      setResult(data);
      if (data.status === 'completed') onCreated();
    } catch (e) {
      setResult({ status: 'failed', error: e instanceof Error ? e.message : 'Request failed' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label="Batch create opportunities" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lcars border border-[#d9e1f0] bg-white p-4 space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-[#18223a]">
          Batch Create ({signalIds.length} signal{signalIds.length === 1 ? '' : 's'})
        </h3>
        <p className="text-xs text-[#61718c]">
          Creates {signalIds.length} comms_content opportunities from the selected signals. This is
          all-or-nothing — if any signal fails validation, nothing is created.
        </p>

        {!result && (
          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={handleCreate}
              disabled={busy}
              className="text-xs border border-green-500/40 rounded px-3 py-1.5 text-green-600 hover:bg-green-500/10 disabled:opacity-50 transition-colors"
            >
              {busy ? 'Creating…' : '✓ Create All'}
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="text-xs border border-[#d9e1f0] rounded px-3 py-1.5 text-[#61718c] hover:text-[#18223a] transition-colors"
            >
              Cancel
            </button>
          </div>
        )}

        {result && result.status === 'completed' && (
          <div className="space-y-2">
            <p className="text-xs text-green-600">
              ✓ Created {result.created} opportunit{result.created === 1 ? 'y' : 'ies'}. Find them in the Pipeline tab.
            </p>
            <button type="button" onClick={onClose} className="text-xs border border-[#d9e1f0] rounded px-3 py-1.5 text-[#61718c] hover:text-[#18223a] transition-colors">
              Close
            </button>
          </div>
        )}

        {result && result.status !== 'completed' && (
          <div className="space-y-2">
            <p className="text-xs text-red-500">
              ✗ Batch creation failed. Reason: {result.error ?? 'Unknown error'}
            </p>
            <p className="text-[10px] text-[#61718c]">Entire batch rolled back — 0 opportunities created.</p>
            <div className="flex gap-2">
              <button type="button" onClick={handleCreate} className="text-xs border border-[#d9e1f0] rounded px-3 py-1.5 text-[#61718c] hover:text-[#18223a] transition-colors">
                Retry
              </button>
              <button type="button" onClick={onClose} className="text-xs border border-[#d9e1f0] rounded px-3 py-1.5 text-[#61718c] hover:text-[#18223a] transition-colors">
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function SignalsTab({ domain }: { domain: Domain }) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minScore, setMinScore] = useState(0.7);
  const [pillarFilter, setPillarFilter] = useState('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showPreview, setShowPreview] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ view: 'content_signals', days: '30', limit: '50' });
      if (domain !== 'both') qs.set('domain', domain);
      const res = await fetch(`/api/intelligence?${qs}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Failed to load signals');
      setSignals(data.signals ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load signals');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    setSelected(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domain]);

  const filtered = signals.filter(
    s => s.rank_score >= minScore && (pillarFilter === 'all' || s.pillar_key === pillarFilter)
  );
  const pillars = [...new Set(signals.map(s => s.pillar_key))];

  function toggle(id: string) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-3 items-center">
        <label className="text-xs text-[#61718c] flex items-center gap-1">
          Min rank score
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={minScore}
            onChange={e => setMinScore(Number(e.target.value))}
            className="w-16 rounded border border-[#d9e1f0] bg-white/40 px-1.5 py-0.5 text-xs text-[#18223a]"
          />
        </label>
        <select
          value={pillarFilter}
          onChange={e => setPillarFilter(e.target.value)}
          className="rounded border border-[#d9e1f0] bg-white/40 px-2 py-1 text-xs text-[#18223a]"
        >
          <option value="all">All pillars</option>
          {pillars.map(p => (
            <option key={p} value={p}>{PILLAR_LABEL[p] ?? p}</option>
          ))}
        </select>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => setShowPreview(true)}
          disabled={selected.size === 0}
          className="text-xs border border-green-500/40 rounded px-3 py-1 text-green-600 hover:bg-green-500/10 disabled:opacity-40 transition-colors"
        >
          ➕ Batch Create ({selected.size} selected)
        </button>
        <button
          type="button"
          onClick={() => setSelected(new Set())}
          disabled={selected.size === 0}
          className="text-xs border border-[#d9e1f0] rounded px-3 py-1 text-[#61718c] hover:text-[#18223a] disabled:opacity-40 transition-colors"
        >
          Clear Selection
        </button>
      </div>

      {loading && <p className="text-sm text-[#61718c]">Loading signals…</p>}
      {error && <p className="rounded-lcars border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-500">{error}</p>}
      {!loading && !error && filtered.length === 0 && (
        <p className="text-sm text-[#61718c]">No signals at or above rank {minScore.toFixed(2)}.</p>
      )}

      <div className="flex flex-col gap-2">
        {filtered.map(s => (
          <SignalCard key={s.event_id} signal={s} selected={selected.has(s.event_id)} onToggle={() => toggle(s.event_id)} />
        ))}
      </div>

      {showPreview && (
        <BatchPreviewModal
          signalIds={[...selected]}
          onClose={() => setShowPreview(false)}
          onCreated={() => {
            setSelected(new Set());
            load();
          }}
        />
      )}
    </div>
  );
}
