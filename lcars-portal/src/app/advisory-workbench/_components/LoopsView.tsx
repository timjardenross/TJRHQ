'use client';

// Open Advisory Loops — close out advice sessions that have no recorded outcome.
// Reads GET /api/advisory/loops (open ADV-*.json records).
// Closes via POST /api/advisory { action: "outcome", advisoryId, outcome, note }.

import { useCallback, useEffect, useState } from 'react';
import { Panel } from './shared';

interface Loop {
  advisory_id: string;
  recorded_at: string;
  question: string;
  recommendation: string;
  outcome: string | null;
  confidence_band?: string | null;
  decision_mode?: string;
}

type OutcomeValue = 'success' | 'partial' | 'failure';

const OUTCOME_OPTS: { value: OutcomeValue; label: string; style: string }[] = [
  { value: 'success',  label: '✓ Success',  style: 'border-wb-sage-deep text-wb-sage-deep hover:bg-wb-sage-deep/10' },
  { value: 'partial',  label: '~ Partial',   style: 'border-wb-warn/60 text-wb-warn-on hover:bg-wb-warn/10'         },
  { value: 'failure',  label: '✗ Failure',   style: 'border-wb-crit/60 text-wb-crit-on hover:bg-wb-crit/10'         },
];

function fmt(iso: string) {
  try { return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }); }
  catch { return iso; }
}

export function LoopsView() {
  const [loops, setLoops] = useState<Loop[]>([]);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [closing, setClosing] = useState<Record<string, boolean>>({});
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    fetch('/api/advisory/loops')
      .then((r) => r.json())
      .then((d: { loops?: Loop[] }) => { setLoops(d.loops ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const close = useCallback(async (id: string, outcome: OutcomeValue) => {
    setClosing((prev) => ({ ...prev, [id]: true }));
    setErrors((prev) => { const n = { ...prev }; delete n[id]; return n; });
    try {
      const res = await fetch('/api/advisory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'outcome', advisoryId: id, outcome, note: notes[id] ?? '' }),
      });
      const data = (await res.json()) as { ok?: boolean; error?: string; result?: { ok?: boolean; message?: string } };
      const ok = data.ok ?? data.result?.ok ?? res.ok;
      if (ok) {
        setClosed((prev) => new Set([...prev, id]));
      } else {
        setErrors((prev) => ({ ...prev, [id]: data.error ?? data.result?.message ?? 'Failed to record outcome' }));
      }
    } catch (err) {
      setErrors((prev) => ({ ...prev, [id]: (err as Error).message }));
    } finally {
      setClosing((prev) => ({ ...prev, [id]: false }));
    }
  }, [notes]);

  const visible = loops.filter((l) => !closed.has(l.advisory_id));
  const closedCount = closed.size;

  if (loading) {
    return (
      <Panel title="Open Advisory Loops">
        <p className="text-sm text-wb-ink2">Loading…</p>
      </Panel>
    );
  }

  return (
    <Panel title="Open Advisory Loops">
      <div className="space-y-4">
        {closedCount > 0 && (
          <div className="rounded-md border border-wb-sage-deep/40 bg-wb-sage-deep/5 px-4 py-2.5">
            <p className="text-xs text-wb-sage-deep">
              {closedCount} loop{closedCount !== 1 ? 's' : ''} closed this session.
            </p>
          </div>
        )}

        {visible.length === 0 && (
          <div className="rounded-md border border-wb-line bg-wb-bg px-4 py-10 text-center">
            <p className="text-sm text-wb-ink2">
              {loops.length === 0 ? 'No open advisory loops — all advice has recorded outcomes.' : 'All open loops closed.'}
            </p>
          </div>
        )}

        {visible.map((loop) => {
          const isClosing = !!closing[loop.advisory_id];
          return (
            <div key={loop.advisory_id} className="rounded-md border border-wb-line bg-wb-surface">
              <div className="border-b border-wb-line px-4 py-2.5">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-mono text-[10px] text-wb-ink2">{loop.advisory_id}</p>
                  <p className="text-[10px] text-wb-ink2">{fmt(loop.recorded_at)}</p>
                </div>
              </div>
              <div className="space-y-3 px-4 py-3">
                <div>
                  <p className="mb-1 text-[10px] uppercase tracking-[0.15em] text-wb-ink2">Question asked</p>
                  <p className="text-sm text-wb-ink">{loop.question}</p>
                </div>
                {loop.recommendation && (
                  <div>
                    <p className="mb-1 text-[10px] uppercase tracking-[0.15em] text-wb-ink2">Recommendation given</p>
                    <p className="line-clamp-3 text-sm text-wb-ink/80">{loop.recommendation}</p>
                  </div>
                )}
                <div>
                  <p className="mb-1.5 text-[10px] uppercase tracking-[0.15em] text-wb-ink2">Note (optional)</p>
                  <input
                    type="text"
                    value={notes[loop.advisory_id] ?? ''}
                    onChange={(e) => setNotes((prev) => ({ ...prev, [loop.advisory_id]: e.target.value }))}
                    placeholder="What actually happened?"
                    disabled={isClosing}
                    className="w-full rounded-md border border-wb-line bg-wb-bg px-3 py-1.5 text-sm text-wb-ink placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep disabled:opacity-50"
                  />
                </div>
                {errors[loop.advisory_id] && (
                  <p className="text-xs text-wb-crit-on">{errors[loop.advisory_id]}</p>
                )}
                <div className="flex flex-wrap gap-2">
                  {OUTCOME_OPTS.map(({ value, label, style }) => (
                    <button
                      key={value}
                      onClick={() => close(loop.advisory_id, value)}
                      disabled={isClosing}
                      className={`rounded-md border px-3 py-1.5 text-xs font-medium uppercase tracking-wider transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep disabled:cursor-not-allowed disabled:opacity-40 ${style}`}
                    >
                      {isClosing ? '…' : label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          );
        })}

        <p className="text-[10px] text-wb-ink2">
          {visible.length} open loop{visible.length !== 1 ? 's' : ''} · Closing improves advisory calibration.
        </p>
      </div>
    </Panel>
  );
}
