'use client';

// Ask — the default Advisory Workbench view (2026-08-09 redesign, replacing
// "Board" as both default and only-thing-you-see-on-load). Renamed from
// BoardView.tsx; same endpoint (POST /api/advisory {action:"advice"}),
// same collaboration_router.py auto-routing this session's work just fixed
// (core/crew/registry/ was missing entirely -> officer_perspectives was
// always empty; now genuinely selects and retrieves from real specialists).
// mode: 'board' is kept as the persisted advisory-sessions value unchanged
// (existing rows already use it; investigate/page.tsx's deep link still
// targets ?domain=board) — only the presentation layer is renamed.
//
// What changed from BoardView and why: the Captain's own review of this
// workbench was "too many roles, the first page doesn't invite me in, ask
// a question and then pull it apart." This view IS that concept — one
// input, no persona/mode picker before it, auto-routed synthesis first,
// individual specialist perspectives pulled apart on demand behind a
// disclosure rather than always-expanded. Dropped the Advisory/Scenario
// mode toggle entirely (an upfront decision competing with just typing);
// a "what would happen if…" framing can still be typed directly. Evidence
// panel moved to sit with the result, not between the input and the
// button, so the ask surface itself stays a single clear action.

import { useEffect, useState } from 'react';
import { fetchRecommendations, type RecommendationPackage } from '@/lib/recommendations';
import { fetchInvestigation, type InvestigationRunResult } from '@/lib/investigate';
import { Dots, useElapsed, COUNCIL, AdvisoryBlock, EvidencePanel } from './shared';
import type { AdvisoryResult, BoardSession } from './types';

const LS_BOARD_LOG = 'lcars-board-log';

export function AskView({
  investigationType,
  investigationReason,
}: {
  investigationType?: string;
  investigationReason?: string;
}) {
  const [input, setInput] = useState(investigationReason ?? '');
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<AdvisoryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<BoardSession[]>([]);
  const [showLog, setShowLog] = useState(false);
  const [showPerspectives, setShowPerspectives] = useState(false);
  const [recommendations, setRecommendations] = useState<RecommendationPackage | null>(null);
  const [investigation, setInvestigation] = useState<InvestigationRunResult | null>(null);
  const elapsed = useElapsed(loading);

  useEffect(() => {
    try { const raw = localStorage.getItem(LS_BOARD_LOG); if (raw) setLog(JSON.parse(raw) as BoardSession[]); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchRecommendations().then(setRecommendations);
  }, []);

  useEffect(() => {
    if (investigationType && investigationReason) {
      fetchInvestigation(investigationType, investigationReason).then(setInvestigation);
    }
  }, [investigationType, investigationReason]);

  const submit = async () => {
    const question = input.trim();
    if (!question || loading) return;
    setLoading(true); setSummary(null); setError(null); setShowPerspectives(false);
    try {
      const res = await fetch('/api/advisory', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'advice', question }) });
      const data = (await res.json()) as { result?: AdvisoryResult; error?: string };
      if (data.error) { setError(data.error); return; }
      const result = data.result ?? (data as unknown as AdvisoryResult);
      setSummary(result);
      const session: BoardSession = { id: Date.now().toString(), ts: Date.now(), question, result };
      setLog((prev) => { const next = [session, ...prev].slice(0, 30); try { localStorage.setItem(LS_BOARD_LOG, JSON.stringify(next)); } catch { /**/ } return next; });
      fetch('/api/advisory-sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'board', question, result }),
      }).catch(() => { /* best-effort */ });
    } catch (err) { setError((err as Error).message); }
    finally { setLoading(false); }
  };

  const exportLog = () => {
    const lines = [`# Advisory Export\n`];
    log.forEach((s) => {
      lines.push(`## ${new Date(s.ts).toLocaleString()}\n**Question:** ${s.question}\n`);
      if (s.result.executive_summary) lines.push(`**Summary:** ${s.result.executive_summary}\n`);
      if (s.result.recommendation) lines.push(`**Recommendation:** ${s.result.recommendation}\n`);
      lines.push('---\n');
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'advisory-export.md'; a.click();
  };

  const perspectives = summary?.officer_perspectives ?? [];
  const actionBtn = 'rounded-md border border-wb-line px-3 py-1 text-[10px] uppercase tracking-widest text-wb-ink2 transition-colors hover:text-wb-sage-deep';

  return (
    <div className="space-y-5">
      {log.length > 0 && (
        <div className="flex justify-end gap-2">
          <button onClick={() => setShowLog((v) => !v)} className={actionBtn}>{showLog ? 'Hide History' : `History (${log.length})`}</button>
          <button onClick={exportLog} className={actionBtn}>Export ↓</button>
        </div>
      )}
      {showLog && log.length > 0 && (
        <div className="max-h-56 space-y-2 overflow-y-auto rounded-md border border-wb-line bg-wb-bg p-3">
          {log.map((s) => (
            <div key={s.id} className="flex items-start justify-between gap-2 border-b border-wb-line pb-2 last:border-0">
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs text-wb-ink/80">{s.question}</p>
                <p className="text-[10px] text-wb-ink2">{new Date(s.ts).toLocaleString()}</p>
              </div>
              <button onClick={() => { setSummary(s.result); setInput(s.question); setShowLog(false); }}
                className="shrink-0 text-[9px] uppercase tracking-widest text-wb-sage-deep hover:underline">View</button>
            </div>
          ))}
        </div>
      )}

      <div className="mx-auto max-w-xl space-y-3 text-center">
        <h1 className="font-serif text-2xl text-wb-ink">Ask</h1>
        <p className="text-[13px] text-wb-ink2">One question — routed automatically to whichever specialists are relevant, synthesised into one answer.</p>
        <div className="space-y-2 text-left">
          <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }} rows={3}
            placeholder="Bring a question…" disabled={loading}
            className="w-full resize-y rounded-md border border-wb-line bg-wb-bg px-3 py-2.5 text-sm text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus:outline-none disabled:opacity-50" />
          <button onClick={submit} disabled={loading || !input.trim()}
            className="w-full rounded-md bg-wb-sage-deep px-4 py-2.5 text-sm font-semibold uppercase tracking-[0.15em] text-white transition-opacity hover:opacity-80 disabled:opacity-40">
            Ask
          </button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center gap-3 py-4">
          <Dots />
          <span className="text-sm text-wb-ink2">Routing to specialists…</span>
          <span className="font-mono text-[10px] text-wb-ink2">{elapsed}s</span>
        </div>
      )}
      {error && (
        <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3 text-sm text-wb-crit-on">
          <p className="mb-1 font-semibold">Advisory runtime offline</p>
          <p className="text-xs text-wb-crit-on/80">{error}</p>
        </div>
      )}
      {summary && !loading && (
        <div className="space-y-4">
          <AdvisoryBlock data={summary} />

          <div>
            <button onClick={() => setShowPerspectives((v) => !v)}
              className="text-[11px] font-semibold uppercase tracking-[0.15em] text-wb-sage-deep hover:underline">
              {showPerspectives ? '▲ Hide' : '▼ Pull apart'} — {perspectives.length} specialist perspective{perspectives.length === 1 ? '' : 's'}
            </button>
            {showPerspectives && (
              <div className="mt-2 space-y-2">
                {perspectives.length === 0 ? (
                  <p className="text-xs text-wb-ink2">
                    {summary.degraded
                      ? 'No specialist perspectives — the live pipeline was unavailable for this convene.'
                      : 'No specialist perspectives were retrieved for this question.'}
                  </p>
                ) : perspectives.map((op, i) => {
                  const advisor = COUNCIL.find((a) => a.label.toLowerCase() === op.officer?.toLowerCase());
                  const accentClass = advisor?.dissent ? 'text-wb-crit-on' : 'text-wb-sage-deep';
                  const stance = op.stance ?? '';
                  const stanceColor = stance === 'supports' ? 'text-wb-ok-on' : stance === 'cautions' ? 'text-wb-warn-on' : 'text-wb-ink2';
                  return (
                    <div key={i} className="space-y-1.5 rounded-md border border-wb-line bg-wb-surface px-4 py-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className={`text-[11px] font-semibold uppercase tracking-wider ${accentClass}`}>{op.officer}</p>
                        {stance && <span className={`text-[9px] uppercase tracking-widest ${stanceColor}`}>{stance}</span>}
                      </div>
                      <p className="text-sm leading-relaxed text-wb-ink/85">{op.recommendation}</p>
                      {op.confidence !== undefined && <p className="text-[9px] text-wb-ink2">Confidence: {op.confidence}%</p>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <EvidencePanel recommendations={recommendations} investigation={investigation} />
        </div>
      )}
    </div>
  );
}
