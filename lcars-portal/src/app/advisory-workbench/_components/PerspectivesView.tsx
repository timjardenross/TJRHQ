'use client';

// Phase B — Distinguished Voices. Ported from the legacy Advisory Council
// PerspectivesMode. Reuses every endpoint unchanged: GET /api/perspectives
// (list + persona content), POST /api/ai/chat (per voice), POST
// /api/perspectives (synthesis), and the captured_items capture. Skin only.

import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { Panel, Dots, useElapsed } from './shared';
import type { Perspective, PerspectiveResponse, PerspectiveSession } from './types';

const CATEGORIES: { key: string; label: string }[] = [
  { key: 'politics', label: 'Politics & Leadership' },
  { key: 'business', label: 'Business & Innovation' },
  { key: 'strategy', label: 'Strategy' },
  { key: 'philosophy', label: 'Philosophy & Mindfulness' },
  { key: 'resilience', label: 'Human Resilience' },
  { key: 'science', label: 'Science & Systems' },
  { key: 'command', label: 'Command' },
];

const LS_PERSPECTIVES_LOG = 'lcars-perspectives-log';

async function savePerspectiveCapture(question: string, responses: { label: string; response: string }[]) {
  try {
    const supabase = createSupabaseBrowserClient();
    const raw = [`Question: ${question}\n`];
    responses.forEach((r) => { raw.push(`\n### ${r.label}\n${r.response}`); });
    const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const now = new Date();
    await supabase.from('captured_items').insert({
      captured_by:          'captain-tjr',
      captured_at:          now.toISOString(),
      source_type:          'channel_message',
      source_channel_id:    'portal-floating-capture',
      source_message_id:    id,
      source_message_ts:    String(now.getTime()),
      item_type:            'text_note',
      title:                `Advisory Perspectives: ${question.slice(0, 80)}${question.length > 80 ? '…' : ''}`,
      raw_text:             raw.join('').slice(0, 10240),
      classification:       'reference',
      importance:           'medium',
      processing_status:    'routed',
      review_status:        'reviewed',
      requires_review:      false,
      ai_enrichment_status: 'not_enriched',
    });
  } catch { /* best-effort — never block UI */ }
}

type SelectionMode = 'individual' | 'category' | 'all';
type ResponseMode = 'individual' | 'synthesised';

export function PerspectivesView() {
  const [available, setAvailable] = useState<Perspective[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [selectionMode, setSelectionMode] = useState<SelectionMode>('individual');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [responseMode, setResponseMode] = useState<ResponseMode>('individual');
  const [input, setInput] = useState('');
  const [responses, setResponses] = useState<PerspectiveResponse[]>([]);
  const [synthesis, setSynthesis] = useState<string>('');
  const [synthesising, setSynthesising] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [anyLoading, setAnyLoading] = useState(false);
  const [log, setLog] = useState<PerspectiveSession[]>([]);
  const [showLog, setShowLog] = useState(false);
  const elapsed = useElapsed(anyLoading || synthesising);

  useEffect(() => {
    fetch('/api/perspectives')
      .then((r) => r.json())
      .then((d: { perspectives?: Perspective[] }) => { setAvailable(d.perspectives ?? []); setLoadingList(false); })
      .catch(() => setLoadingList(false));
    try {
      const raw = localStorage.getItem(LS_PERSPECTIVES_LOG);
      if (raw) setLog(JSON.parse(raw) as PerspectiveSession[]);
    } catch { /* ignore */ }
  }, []);

  const activeNames: string[] = (() => {
    if (selectionMode === 'all') return available.map((p) => p.name);
    if (selectionMode === 'category' && activeCategory) return available.filter((p) => p.category === activeCategory).map((p) => p.name);
    return [...selected];
  })();

  const toggleSelect = (name: string) => {
    setSelectionMode('individual');
    setActiveCategory(null);
    setSelected((prev) => { const next = new Set(prev); next.has(name) ? next.delete(name) : next.add(name); return next; });
  };

  const selectCategory = (key: string) => {
    if (selectionMode === 'category' && activeCategory === key) {
      setSelectionMode('individual');
      setActiveCategory(null);
    } else {
      setSelectionMode('category');
      setActiveCategory(key);
      setSelected(new Set());
    }
  };

  const selectAll = () => {
    if (selectionMode === 'all') {
      setSelectionMode('individual');
      setSelected(new Set());
    } else {
      setSelectionMode('all');
      setActiveCategory(null);
      setSelected(new Set());
    }
  };

  const askPerspective = async (p: Perspective, trimmed: string, idx: number) => {
    try {
      const contentRes = await fetch(`/api/perspectives?name=${p.name}`);
      const contentData = (await contentRes.json()) as { content?: string; error?: string };
      if (contentData.error || !contentData.content) throw new Error(contentData.error ?? 'No content');
      const chatRes = await fetch('/api/ai/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: [{ role: 'user', content: trimmed }], systemPrompt: contentData.content, stream: false }),
      });
      const chatData = (await chatRes.json()) as { content?: string; error?: string };
      if (chatData.error) throw new Error(chatData.error);
      setResponses((prev) => prev.map((r, i) => i === idx ? { ...r, response: chatData.content ?? '', loading: false } : r));
    } catch (err) {
      setResponses((prev) => prev.map((r, i) => i === idx ? { ...r, loading: false, error: (err as Error).message } : r));
    }
  };

  const convene = async (overrideNames?: string[]) => {
    const trimmed = input.trim();
    if (!trimmed) return;
    const names = overrideNames ?? activeNames;
    if (names.length === 0) return;
    const chosen = available.filter((p) => names.includes(p.name));

    setSynthesis('');
    setResponses((prev) => {
      if (overrideNames) {
        return prev.map((r) => names.includes(r.perspective.name) ? { ...r, response: '', loading: true, error: null } : r);
      }
      return chosen.map((p) => ({ perspective: p, content: '', response: '', loading: true, error: null }));
    });
    setAnyLoading(true);

    await Promise.all(chosen.map((p, i) => {
      const idx = overrideNames ? responses.findIndex((r) => r.perspective.name === p.name) : i;
      return askPerspective(p, trimmed, idx);
    }));

    setAnyLoading(false);

    setResponses((current) => {
      const completed = current.filter((r) => r.response && !r.loading);
      if (completed.length > 0) {
        const sessionResponses = completed.map((r) => ({ label: r.perspective.label, response: r.response }));
        const session: PerspectiveSession = { id: Date.now().toString(), ts: Date.now(), question: trimmed, responses: sessionResponses };
        setLog((prev) => { const next = [session, ...prev].slice(0, 50); try { localStorage.setItem(LS_PERSPECTIVES_LOG, JSON.stringify(next)); } catch { /**/ } return next; });
        savePerspectiveCapture(trimmed, sessionResponses);

        if (responseMode === 'synthesised' && completed.length > 1 && !overrideNames) {
          setSynthesising(true);
          fetch('/api/perspectives', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: trimmed, responses: sessionResponses }),
          })
            .then((r) => r.json())
            .then((d: { synthesis?: string; error?: string }) => {
              // Never fail silently: if the panel synthesis didn't come back,
              // say so rather than collapsing to just the individual voices.
              setSynthesis(d.synthesis || `Panel synthesis unavailable${d.error ? ` — ${d.error}` : '.'}`);
            })
            .catch(() => { setSynthesis('Panel synthesis unavailable — could not reach the synthesis service.'); })
            .finally(() => setSynthesising(false));
        }
      }
      return current;
    });
  };

  const exportSession = () => {
    const lines: string[] = [`# Advisory Perspectives Export\n`];
    log.forEach((s) => {
      lines.push(`## ${new Date(s.ts).toLocaleString()}`);
      lines.push(`**Question:** ${s.question}\n`);
      s.responses.forEach((r) => { lines.push(`### ${r.label}\n${r.response}\n`); });
      lines.push('---\n');
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'perspectives-export.md'; a.click();
  };

  const hasActive = responses.length > 0;
  const totalLoading = responses.filter((r) => r.loading).length;
  const selectionCount = activeNames.length;

  const actionBtn = 'rounded-md border border-wb-line px-3 py-1 text-[10px] uppercase tracking-widest text-wb-ink2 transition-colors hover:text-wb-sage-deep';

  return (
    <Panel
      title="Distinguished Perspectives"
      actions={log.length > 0 ? (
        <div className="flex items-center gap-2">
          <button onClick={() => setShowLog((v) => !v)} className={actionBtn}>{showLog ? 'Hide Log' : `Log (${log.length})`}</button>
          <button onClick={exportSession} className={actionBtn}>Export ↓</button>
        </div>
      ) : undefined}
    >
      <div className="space-y-4">
        {showLog && log.length > 0 && (
          <div className="max-h-64 space-y-3 overflow-y-auto rounded-md border border-wb-line bg-wb-bg p-3">
            <p className="text-[10px] uppercase tracking-[0.15em] text-wb-ink2">Session History</p>
            {log.map((s) => (
              <div key={s.id} className="space-y-1 border-b border-wb-line pb-2 last:border-0">
                <div className="flex items-start justify-between gap-2">
                  <p className="flex-1 text-xs text-wb-ink/80">{s.question}</p>
                  <button onClick={() => { setInput(s.question); setShowLog(false); }} className="shrink-0 text-[9px] uppercase tracking-widest text-wb-sage-deep hover:underline">Re-ask</button>
                </div>
                <p className="text-[10px] text-wb-ink2">{new Date(s.ts).toLocaleString()} · {s.responses.map((r) => r.label).join(', ')}</p>
              </div>
            ))}
          </div>
        )}

        {loadingList ? (
          <p className="text-sm text-wb-ink2">Loading perspectives…</p>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] uppercase tracking-[0.15em] text-wb-ink2">Select by</span>
              {CATEGORIES.map((cat) => {
                const isActive = selectionMode === 'category' && activeCategory === cat.key;
                const count = available.filter((p) => p.category === cat.key).length;
                if (count === 0) return null;
                return (
                  <button key={cat.key} onClick={() => selectCategory(cat.key)}
                    className={`rounded-md border px-3 py-1 text-[10px] uppercase tracking-wider transition-colors ${isActive ? 'border-wb-sage-deep bg-wb-sage-deep/15 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40 hover:text-wb-ink'}`}>
                    {cat.label} <span className="opacity-60">({count})</span>
                  </button>
                );
              })}
              <button onClick={selectAll}
                className={`rounded-md border px-3 py-1 text-[10px] uppercase tracking-wider transition-colors ${selectionMode === 'all' ? 'border-wb-sage-deep bg-wb-sage-deep/15 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40 hover:text-wb-ink'}`}>
                All ({available.length})
              </button>
            </div>

            <div>
              <p className="mb-2 text-[10px] uppercase tracking-[0.15em] text-wb-ink2">
                {selectionMode === 'individual' ? 'Or pick individual voices' : `Active: ${selectionCount} voice${selectionCount !== 1 ? 's' : ''}`}
              </p>
              <div className="flex flex-wrap gap-2">
                {available.map((p) => {
                  const isOn = selectionMode === 'all' || (selectionMode === 'category' && p.category === activeCategory) || selected.has(p.name);
                  return (
                    <button key={p.name} onClick={() => toggleSelect(p.name)}
                      className={`rounded-md border px-3 py-1.5 text-xs uppercase tracking-wider transition-colors ${isOn ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40'}`}>
                      {p.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {selectionCount > 1 && (
              <div className="flex items-center gap-3">
                <span className="text-[10px] uppercase tracking-[0.15em] text-wb-ink2">Response</span>
                {(['individual', 'synthesised'] as ResponseMode[]).map((m) => (
                  <button key={m} onClick={() => setResponseMode(m)}
                    className={`rounded-md border px-3 py-1 text-[10px] uppercase tracking-wider transition-colors ${responseMode === m ? 'border-wb-sage-deep bg-wb-sage-deep/15 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40'}`}>
                    {m === 'individual' ? 'Individual voices' : 'Group synthesis'}
                  </button>
                ))}
              </div>
            )}

            <div className="flex items-end gap-2">
              <textarea value={input} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); convene(); } }}
                rows={3} placeholder="What would these perspectives say about…?" disabled={selectionCount === 0 || anyLoading}
                className="min-h-[72px] flex-1 resize-y rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus:outline-none disabled:opacity-50" />
              <button onClick={() => convene()} disabled={selectionCount === 0 || !input.trim() || anyLoading}
                className="self-stretch rounded-md bg-wb-sage-deep px-4 text-sm font-semibold uppercase tracking-[0.15em] text-white transition-opacity hover:opacity-80 disabled:opacity-40">
                Ask
              </button>
            </div>
            {selectionCount === 0 && !anyLoading && <p className="text-[10px] text-wb-ink2">Select voices above — by category, all, or individually.</p>}
          </div>
        )}

        {(anyLoading || synthesising) && (
          <div className="flex items-center gap-3 py-2">
            <Dots />
            <span className="text-sm text-wb-ink2">
              {synthesising ? 'Synthesising panel response…' : `Gathering ${totalLoading} perspective${totalLoading !== 1 ? 's' : ''}…`}
            </span>
            <span className="ml-auto font-mono text-[10px] text-wb-ink2">{elapsed}s</span>
          </div>
        )}

        {synthesis && !synthesising && (
          <div className="rounded-md border border-wb-sage-deep/40 bg-wb-sage-deep/5">
            <div className="border-b border-wb-sage-deep/30 px-4 py-2.5">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-wb-sage-deep">Panel Synthesis</p>
            </div>
            <div className="px-5 py-4">
              <div className="prose prose-base max-w-none prose-headings:font-serif prose-headings:text-wb-ink prose-p:my-2 prose-p:leading-7 prose-strong:text-wb-ink">
                <ReactMarkdown>{synthesis}</ReactMarkdown>
              </div>
            </div>
          </div>
        )}

        {hasActive && (
          <div className="space-y-4">
            {responseMode === 'synthesised' && synthesis && (
              <p className="text-[10px] uppercase tracking-[0.15em] text-wb-ink2">Individual voices</p>
            )}
            {responses.map((r, i) => (
              <div key={i} className="rounded-md border border-wb-line bg-wb-surface">
                <div className="flex items-center justify-between gap-3 border-b border-wb-line px-4 py-2.5">
                  <span className="text-[11px] font-semibold uppercase tracking-widest text-wb-sage-deep">{r.perspective.label}</span>
                  <div className="flex items-center gap-2">
                    {r.response && !r.loading && (
                      <button onClick={() => convene([r.perspective.name])} disabled={anyLoading || !input.trim()}
                        className="text-[9px] uppercase tracking-widest text-wb-ink2 transition-colors hover:text-wb-sage-deep disabled:opacity-40">
                        ↺ Regenerate
                      </button>
                    )}
                    {r.loading && <Dots size="sm" />}
                  </div>
                </div>
                <div className="px-5 py-4">
                  {r.error && <p className="text-sm text-wb-crit-on">{r.error}</p>}
                  {!r.loading && !r.error && !r.response && <p className="text-sm text-wb-ink2">No response.</p>}
                  {r.response && !r.loading && (
                    <div className="prose prose-base max-w-none prose-headings:font-serif prose-headings:text-wb-ink prose-p:my-2 prose-p:leading-7 prose-strong:text-wb-ink">
                      <ReactMarkdown>{r.response}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}
