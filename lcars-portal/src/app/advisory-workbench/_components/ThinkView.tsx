'use client';

// Think — the default Advisory view (2026-09 redesign, replacing "Ask").
// Same endpoint (POST /api/advisory {action:"advice"}) and the same
// collaboration_router.py auto-routing Ask always used — this is a UI
// simplification, not a new engine. mode: 'board' is kept as the persisted
// advisory-sessions value unchanged (existing rows already use it;
// investigate/page.tsx's deep link still targets ?domain=board, accepted as
// a legacy alias for ?domain=think — see types.ts's normalizeDomain).
//
// What's new: results lead with interpretation (The Read / Why / What I'd
// Challenge / What's Uncertain / Recommendation / Confidence — mission §7)
// before any backend architecture is shown. Reasoning lenses (§10) are
// simple re-framings of the SAME answer — only "Challenge it" makes a fresh
// call, to the real challenge/red-team pass; the rest re-filter perspectives
// and risks already returned by the one /api/advisory call. "Pull apart the
// reasoning" (§8) stays behind progressive disclosure. Talk-to-an-advisor
// (retired from primary nav, §9) is preserved as an Advanced disclosure so
// the capability isn't lost, just no longer the first thing you see.

import { useEffect, useState } from 'react';
import { fetchRecommendations, type RecommendationPackage } from '@/lib/recommendations';
import { fetchInvestigation, type InvestigationRunResult } from '@/lib/investigate';
import { Dots, useElapsed, PullApartReasoning, ThinkResult } from './shared';
import { ConsultView } from './ConsultView';
import { REASONING_LENSES, type AdvisoryResult, type ReasoningGroup, type ReasoningLens, type ThinkSession } from './types';

const LS_BOARD_LOG = 'lcars-board-log';

export function ThinkView({
  investigationType,
  investigationReason,
  prefill,
}: {
  investigationType?: string;
  investigationReason?: string;
  /** Set by a "Something worth considering" notice (mission §17) or an
   * investigation deep link — bumping `prefill.nonce` re-applies `text`
   * even if it's identical to the current input. */
  prefill?: { text: string; nonce: number } | null;
}) {
  const [input, setInput] = useState(investigationReason ?? '');
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<AdvisoryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<ThinkSession[]>([]);
  const [showLog, setShowLog] = useState(false);
  const [showPullApart, setShowPullApart] = useState(false);
  const [openGroup, setOpenGroup] = useState<ReasoningGroup | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [recommendations, setRecommendations] = useState<RecommendationPackage | null>(null);
  const [investigation, setInvestigation] = useState<InvestigationRunResult | null>(null);
  const [challenge, setChallenge] = useState<AdvisoryResult | null>(null);
  const [challengeLoading, setChallengeLoading] = useState(false);
  const elapsed = useElapsed(loading);

  useEffect(() => {
    try { const raw = localStorage.getItem(LS_BOARD_LOG); if (raw) setLog(JSON.parse(raw) as ThinkSession[]); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchRecommendations().then(setRecommendations);
  }, []);

  useEffect(() => {
    if (investigationType && investigationReason) {
      fetchInvestigation(investigationType, investigationReason).then(setInvestigation);
    }
  }, [investigationType, investigationReason]);

  useEffect(() => {
    if (prefill) setInput(prefill.text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill?.nonce]);

  const submit = async () => {
    const question = input.trim();
    if (!question || loading) return;
    setLoading(true); setSummary(null); setError(null); setShowPullApart(false); setOpenGroup(null); setChallenge(null);
    try {
      const res = await fetch('/api/advisory', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'advice', question }) });
      const data = (await res.json()) as { result?: AdvisoryResult; error?: string };
      if (data.error) { setError(data.error); return; }
      const result = data.result ?? (data as unknown as AdvisoryResult);
      setSummary(result);
      const session: ThinkSession = { id: Date.now().toString(), ts: Date.now(), question, result };
      setLog((prev) => { const next = [session, ...prev].slice(0, 30); try { localStorage.setItem(LS_BOARD_LOG, JSON.stringify(next)); } catch { /**/ } return next; });
      fetch('/api/advisory-sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'board', question, result }),
      }).catch(() => { /* best-effort */ });
    } catch (err) { setError((err as Error).message); }
    finally { setLoading(false); }
  };

  const applyLens = async (lens: ReasoningLens) => {
    if (!summary) return;
    setShowPullApart(true);
    if (lens === 'human') { setOpenGroup('Human Systems'); return; }
    if (lens === 'risk') { setOpenGroup('Risk'); return; }
    if (lens === 'practical' || lens === 'longterm') { setOpenGroup('Strategy'); return; }
    // 'challenge' — the one lens that makes a fresh call, to the real
    // adversarial/red-team pass (core/advisory/service.py::request_challenge),
    // not a re-framing of data already on screen.
    setOpenGroup('Challenge');
    const question = (summary.question ?? input).trim();
    if (!question) return;
    setChallengeLoading(true);
    try {
      const res = await fetch('/api/advisory', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'challenge', question }) });
      const data = (await res.json()) as { result?: AdvisoryResult; error?: string };
      if (!data.error) setChallenge(data.result ?? (data as unknown as AdvisoryResult));
    } catch { /* best-effort — the standing disagreement/risks already shown still stand */ }
    finally { setChallengeLoading(false); }
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

  const actionBtn = 'rounded-md border border-wb-line px-3 py-1 text-[10px] uppercase tracking-widest text-wb-ink2 transition-colors hover:text-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep';

  return (
    <div className="space-y-5">
      <div className="mx-auto max-w-xl space-y-3 text-center">
        <h1 className="font-serif text-2xl text-wb-ink">What are you thinking through?</h1>
        <p className="text-[13px] text-wb-ink2">Bring a decision, problem, question, or idea — routed automatically to whichever specialists are relevant, synthesised into one answer.</p>
        <div className="space-y-2 text-left">
          <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }} rows={3}
            placeholder="Bring a decision, problem, question or idea…" disabled={loading}
            className="w-full resize-y rounded-md border border-wb-line bg-wb-bg px-3 py-2.5 text-sm text-wb-ink placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep disabled:opacity-50" />
          <button onClick={submit} disabled={loading || !input.trim()}
            className="w-full rounded-md bg-wb-sage-deep px-4 py-2.5 text-sm font-semibold uppercase tracking-[0.15em] text-white transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep disabled:opacity-40 disabled:cursor-not-allowed">
            Think it through
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
        <div className="mx-auto max-w-xl space-y-4">
          <ThinkResult data={summary} />

          <div className="flex flex-wrap gap-2">
            {REASONING_LENSES.map((l) => (
              <button key={l.key} onClick={() => applyLens(l.key)}
                className="rounded-md border border-wb-line px-3 py-1.5 text-[11px] uppercase tracking-wider text-wb-ink2 transition-colors hover:border-wb-sage-deep/50 hover:text-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep">
                {l.label}
              </button>
            ))}
          </div>

          {openGroup === 'Challenge' && (
            <div className="space-y-1.5 rounded-md border border-wb-crit/30 bg-wb-crit/5 px-4 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-wb-crit-on">Challenge</p>
              {challengeLoading ? (
                <div className="flex items-center gap-2 py-1"><Dots size="sm" /><span className="text-xs text-wb-ink2">Running the adversarial review…</span></div>
              ) : challenge ? (
                <>
                  {challenge.reviewer && <p className="text-[10px] text-wb-ink2">Reviewed by {challenge.reviewer}</p>}
                  <p className="text-sm leading-relaxed text-wb-ink/85">{challenge.disagreement || 'No material disagreement was raised on review.'}</p>
                </>
              ) : (
                <p className="text-xs text-wb-ink2">The adversarial review could not be reached — the standing risks and challenge above still apply.</p>
              )}
            </div>
          )}

          <div>
            <button onClick={() => setShowPullApart((v) => !v)}
              className="text-[11px] font-semibold uppercase tracking-[0.15em] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep">
              {showPullApart ? '▲ Hide' : '▼'} Pull apart the reasoning
            </button>
            {showPullApart && (
              <div className="mt-2">
                <PullApartReasoning data={summary} openGroup={openGroup} onOpenGroup={setOpenGroup} recommendations={recommendations} investigation={investigation} />
              </div>
            )}
          </div>
        </div>
      )}

      <div className="mx-auto max-w-xl space-y-3 border-t border-wb-line pt-4">
        <button onClick={() => setShowAdvanced((v) => !v)}
          className="text-[11px] uppercase tracking-[0.15em] text-wb-ink2 hover:text-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep">
          {showAdvanced ? '▲ Hide' : '▼'} Advanced — talk to an advisor directly
        </button>
        {showAdvanced && (
          <div className="pt-2">
            <ConsultView />
          </div>
        )}
      </div>

      {log.length > 0 && (
        <div className="mx-auto max-w-xl space-y-2 border-t border-wb-line pt-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-[0.15em] text-wb-ink2">Recent</span>
            <div className="flex gap-2">
              <button onClick={() => setShowLog((v) => !v)} className={actionBtn}>{showLog ? 'Hide' : `View (${log.length})`}</button>
              <button onClick={exportLog} className={actionBtn}>Export ↓</button>
            </div>
          </div>
          {showLog && (
            <div className="max-h-56 space-y-2 overflow-y-auto rounded-md border border-wb-line bg-wb-bg p-3">
              {log.map((s) => (
                <div key={s.id} className="flex items-start justify-between gap-2 border-b border-wb-line pb-2 last:border-0">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs text-wb-ink/80">{s.question}</p>
                    <p className="text-[10px] text-wb-ink2">{new Date(s.ts).toLocaleString()}</p>
                  </div>
                  <button onClick={() => { setSummary(s.result); setInput(s.question); setShowLog(false); setShowPullApart(false); setOpenGroup(null); setChallenge(null); }}
                    className="shrink-0 text-[9px] uppercase tracking-widest text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep">View</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
