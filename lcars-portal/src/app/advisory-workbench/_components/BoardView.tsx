'use client';

// Phase C — Strategic Council. Ported from the legacy Advisory Council
// BoardMode. Reuses every endpoint unchanged: POST /api/advisory
// (action:advice), lib/recommendations + lib/investigate (evidence engines),
// POST /api/advisory-sessions (persist). Skin only. The investigationType/
// investigationReason deep-link contract is preserved.

import { useEffect, useState } from 'react';
import { fetchRecommendations, type RecommendationPackage } from '@/lib/recommendations';
import { fetchInvestigation, type InvestigationRunResult } from '@/lib/investigate';
import { Panel, Dots, useElapsed, COUNCIL, AdvisoryBlock, EvidencePanel } from './shared';
import type { AdvisoryResult, BoardSession } from './types';

const LS_BOARD_LOG = 'lcars-board-log';

export function BoardView({
  investigationType,
  investigationReason,
}: {
  investigationType?: string;
  investigationReason?: string;
}) {
  const [input, setInput] = useState(investigationReason ?? '');
  const [isScenario, setIsScenario] = useState(false);
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<AdvisoryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<BoardSession[]>([]);
  const [showLog, setShowLog] = useState(false);
  const [recommendations, setRecommendations] = useState<RecommendationPackage | null>(null);
  const [investigation, setInvestigation] = useState<InvestigationRunResult | null>(null);
  const elapsed = useElapsed(loading);

  useEffect(() => {
    try { const raw = localStorage.getItem(LS_BOARD_LOG); if (raw) setLog(JSON.parse(raw) as BoardSession[]); } catch { /* ignore */ }
  }, []);

  // The Recommendation Engine's current top priorities are standing evidence
  // for the Board — fetched once per Board visit, best-effort.
  useEffect(() => {
    fetchRecommendations().then(setRecommendations);
  }, []);

  // A specific investigation is only fetched when arrived at via a real
  // contextual link (e.g. /investigate's "Consult the Advisory Council on this").
  useEffect(() => {
    if (investigationType && investigationReason) {
      fetchInvestigation(investigationType, investigationReason).then(setInvestigation);
    }
  }, [investigationType, investigationReason]);

  const submit = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    setLoading(true); setSummary(null); setError(null);
    const question = isScenario ? `Scenario analysis: What would happen if ${trimmed}` : trimmed;
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
    const lines = [`# Advisory Board Export\n`];
    log.forEach((s) => {
      lines.push(`## ${new Date(s.ts).toLocaleString()}\n**Question:** ${s.question}\n`);
      if (s.result.executive_summary) lines.push(`**Summary:** ${s.result.executive_summary}\n`);
      if (s.result.recommendation) lines.push(`**Recommendation:** ${s.result.recommendation}\n`);
      lines.push('---\n');
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'board-export.md'; a.click();
  };

  const perspectives = summary?.officer_perspectives ?? [];
  const actionBtn = 'rounded-md border border-wb-line px-3 py-1 text-[10px] uppercase tracking-widest text-wb-ink2 transition-colors hover:text-wb-sage-deep';

  return (
    <Panel
      title="Advisory Board"
      actions={log.length > 0 ? (
        <div className="flex items-center gap-2">
          <button onClick={() => setShowLog((v) => !v)} className={actionBtn}>{showLog ? 'Hide Log' : `Log (${log.length})`}</button>
          <button onClick={exportLog} className={actionBtn}>Export ↓</button>
        </div>
      ) : undefined}
    >
      <div className="space-y-4">
        {showLog && log.length > 0 && (
          <div className="max-h-56 space-y-2 overflow-y-auto rounded-md border border-wb-line bg-wb-bg p-3">
            <p className="text-[10px] uppercase tracking-[0.15em] text-wb-ink2">Session History</p>
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

        <div className="space-y-2">
          <div className="mb-2 flex items-center gap-3">
            <span className="text-xs uppercase tracking-wider text-wb-ink2">Mode</span>
            {(['Advisory', 'Scenario'] as const).map((m) => {
              const isActive = m === 'Scenario' ? isScenario : !isScenario;
              return (
                <button key={m} onClick={() => setIsScenario(m === 'Scenario')}
                  className={`rounded-md border px-3 py-1 text-[10px] uppercase tracking-widest transition-colors ${isActive ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40'}`}>
                  {m}
                </button>
              );
            })}
            {isScenario && <span className="text-[10px] italic text-wb-sage-deep/70">What would happen if…</span>}
          </div>
          <div className="flex items-end gap-2">
            <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }} rows={3}
              placeholder={isScenario ? 'What would happen if…' : 'Bring a question to the Advisory Board…'} disabled={loading}
              className="min-h-[72px] flex-1 resize-y rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus:outline-none disabled:opacity-50" />
            <button onClick={submit} disabled={loading || !input.trim()}
              className="self-stretch rounded-md bg-wb-sage-deep px-4 text-sm font-semibold uppercase tracking-[0.15em] text-white transition-opacity hover:opacity-80 disabled:opacity-40">
              Convene
            </button>
          </div>
        </div>

        <EvidencePanel recommendations={recommendations} investigation={investigation} />

        {loading && (
          <div className="flex items-center gap-3 py-4">
            <Dots />
            <span className="text-sm text-wb-ink2">Convening Advisory Board…</span>
            <span className="ml-auto font-mono text-[10px] text-wb-ink2">{elapsed}s</span>
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
              <p className="mb-2 text-[10px] uppercase tracking-[0.15em] text-wb-ink2">Officer Perspectives</p>
              {perspectives.length === 0 ? (
                <p className="text-xs text-wb-ink2">
                  {summary.degraded
                    ? 'No specialist perspectives — the live pipeline was unavailable for this convene.'
                    : 'No specialist perspectives were retrieved for this question.'}
                </p>
              ) : (
                <div className="space-y-2">
                  {perspectives.map((op, i) => {
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
          </div>
        )}
      </div>
    </Panel>
  );
}
