'use client';

// Phase D — Officer Advisors. Ported from the legacy Advisory Council
// ConsultMode. Reuses every endpoint unchanged: streaming POST /api/ai/chat
// and POST /api/xo, POST /api/advisory-sessions (persist). The MSN-0352
// governance path (backend ActionResult[] → ProposalBlock, never model prose)
// is preserved verbatim. Skin only.

import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { AI_MODELS, DEFAULT_MODEL_ID } from '@/lib/ai-models';
import type { ActionResult } from '@/lib/ai-actions';
import { Panel, Dots, COUNCIL, ProposalBlock } from './shared';
import type { CouncilAdvisor, Msg } from './types';

const LS_CONSULT_KEY = 'lcars-council-consult-history';

const QUICK_PROMPTS = [
  'What needs my decision?',
  'Protect or defer?',
  'What changed since yesterday?',
  'Challenge this assumption',
];

export function ConsultView() {
  const [activeAdvisor, setActiveAdvisor] = useState<CouncilAdvisor>(COUNCIL[0]);
  const [threads, setThreads] = useState<Record<string, Msg[]>>({});
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState('');
  const [offlineAdvisors, setOfflineAdvisors] = useState<Set<string>>(new Set());
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL_ID);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_CONSULT_KEY);
      if (raw) setThreads(JSON.parse(raw) as Record<string, Msg[]>);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    try { localStorage.setItem(LS_CONSULT_KEY, JSON.stringify(threads)); } catch { /* ignore */ }
  }, [threads]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [threads, activeAdvisor, streamBuffer]);

  const messages = threads[activeAdvisor.id] ?? [];

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setInput('');
    const userMsg: Msg = { id: Date.now().toString(), role: 'user', content: trimmed };
    const history = [...(threads[activeAdvisor.id] ?? []), userMsg];
    setThreads((prev) => ({ ...prev, [activeAdvisor.id]: history }));
    setLoading(true);
    setStreamBuffer('');

    const endpoint = activeAdvisor.useXoEndpoint ? '/api/xo' : '/api/ai/chat';
    const body = activeAdvisor.useXoEndpoint
      ? JSON.stringify({ messages: history.map((m) => ({ role: m.role, content: m.content })) })
      : JSON.stringify({ messages: history.map((m) => ({ role: m.role, content: m.content })), role: activeAdvisor.id, model: selectedModel, stream: true });

    try {
      const res = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
      if (res.status === 503 || res.status === 404) {
        setOfflineAdvisors((prev) => new Set([...prev, activeAdvisor.id]));
        setLoading(false);
        return;
      }
      if (!res.body) throw new Error('No response body');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let acc = '', buf = '';
      let proposals: ActionResult[] = [];
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n'); buf = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (payload === '[DONE]') break;
          try {
            const p = JSON.parse(payload) as { token?: string; actions?: ActionResult[] };
            if (p.token) { acc += p.token; setStreamBuffer(acc); }
            if (p.actions?.length) proposals = p.actions;
          } catch { /* skip */ }
        }
      }
      const finalContent = acc || '(no response)';
      setThreads((prev) => ({ ...prev, [activeAdvisor.id]: [...(prev[activeAdvisor.id] ?? []), { id: (Date.now() + 1).toString(), role: 'assistant', content: finalContent, proposals: proposals.length ? proposals : undefined }] }));
      setStreamBuffer('');
      fetch('/api/advisory-sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'consult', advisor_id: activeAdvisor.id, question: trimmed, response: finalContent }),
      }).catch(() => { /* best-effort */ });
    } catch (err) {
      const e = err as Error;
      if (e.message.includes('fetch') || e.message.includes('ECONNREFUSED')) {
        setOfflineAdvisors((prev) => new Set([...prev, activeAdvisor.id]));
      } else {
        setThreads((prev) => ({ ...prev, [activeAdvisor.id]: [...(prev[activeAdvisor.id] ?? []), { id: (Date.now() + 1).toString(), role: 'assistant', content: 'Error contacting advisor.', error: true }] }));
      }
    } finally { setLoading(false); setStreamBuffer(''); }
  }, [activeAdvisor, threads, loading, selectedModel]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } };
  const clearThread = () => { setThreads((prev) => { const next = { ...prev }; delete next[activeAdvisor.id]; return next; }); };
  const isOffline = offlineAdvisors.has(activeAdvisor.id);

  const groups = COUNCIL.reduce<Record<string, CouncilAdvisor[]>>((acc, a) => { (acc[a.group] = acc[a.group] ?? []).push(a); return acc; }, {});
  const groupHasHistory = (advisors: CouncilAdvisor[]) => advisors.some((a) => (threads[a.id]?.length ?? 0) > 0);

  return (
    <div className="flex flex-col gap-4 lg:h-[65vh] lg:flex-row">
      {/* Group-first picker (2026-08 redesign): 18 officers behind 5 group
          chips instead of all always expanded — pick a group, then a
          person within it. Mirrors PerspectivesView's category-first
          pattern, which the Captain's own review flagged as the better of
          the two for the same "too many options" problem. */}
      <div className="flex w-full shrink-0 flex-col gap-3 lg:w-48">
        <div className="flex flex-wrap gap-1.5 lg:flex-col">
          {Object.entries(groups).map(([group, advisors]) => {
            const isOpen = openGroup === group;
            const hasHistory = groupHasHistory(advisors);
            return (
              <button key={group} onClick={() => setOpenGroup(isOpen ? null : group)}
                className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-left text-[10px] uppercase tracking-[0.15em] transition-colors ${isOpen ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40'}`}>
                {group}
                {hasHistory && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-wb-sage-deep" aria-label="has conversation history" />}
                <span className="opacity-60">({advisors.length})</span>
              </button>
            );
          })}
        </div>
        {openGroup && (
          <div className="flex flex-col gap-1">
            {groups[openGroup].map((a) => {
              const active = activeAdvisor.id === a.id;
              const accent = a.dissent ? 'text-wb-crit-on' : 'text-wb-sage-deep';
              return (
                <button key={a.id} onClick={() => { setActiveAdvisor(a); setStreamBuffer(''); }}
                  className={`rounded-md border px-2.5 py-2 text-left transition-colors ${active ? `border-wb-sage-deep bg-wb-sage-deep/10 ${accent}` : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40'}`}>
                  <p className={`text-xs uppercase tracking-wider ${active ? accent : ''}`}>{a.label}</p>
                  <p className="mt-0.5 text-[9px] leading-tight text-wb-ink2">{a.subtitle}</p>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Thread */}
      <Panel title={`${activeAdvisor.label} — ${activeAdvisor.subtitle}`} className="min-w-0 flex-1"
        actions={messages.length > 0 ? (
          <button onClick={clearThread} disabled={loading}
            className="rounded-md border border-wb-line px-3 py-1 text-[10px] uppercase tracking-widest text-wb-ink2 transition-colors hover:text-wb-sage-deep disabled:opacity-40">
            Clear
          </button>
        ) : undefined}>
        {isOffline ? (
          <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
            <p className="text-sm text-wb-ink2">{activeAdvisor.label} is offline (AI model not configured).</p>
            <p className="max-w-sm text-xs text-wb-ink/60">Use the <span className="font-semibold text-wb-sage-deep">Board</span> tab for advisory via the intelligence runtime.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="space-y-3 overflow-y-auto pr-1" style={{ maxHeight: 'calc(65vh - 200px)' }}>
              {messages.length === 0 && !loading && (
                <p className="py-8 text-center text-sm text-wb-ink2">{activeAdvisor.label} standing by.</p>
              )}
              {messages.map((m) => {
                const isUser = m.role === 'user';
                return (
                  <div key={m.id} style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
                    <div className={`rounded-md border px-3.5 py-2.5 text-sm leading-relaxed ${isUser ? 'border-wb-sage-deep/40 bg-wb-sage-deep/10 text-wb-ink' : m.error ? 'border-wb-crit/40 bg-wb-crit/10 text-wb-crit-on' : 'border-wb-line bg-wb-surface text-wb-ink/90'}`} style={{ maxWidth: '90%' }}>
                      {!isUser && !m.error && <p className={`mb-1 text-[10px] uppercase tracking-[0.2em] ${activeAdvisor.dissent ? 'text-wb-crit-on' : 'text-wb-sage-deep'}`}>{activeAdvisor.label}</p>}
                      {isUser ? <span className="whitespace-pre-wrap">{m.content}</span> : (
                        <div className="prose prose-sm max-w-none prose-headings:font-serif prose-headings:text-wb-ink prose-p:my-1 prose-strong:text-wb-ink prose-li:my-0.5">
                          <ReactMarkdown>{m.content}</ReactMarkdown>
                        </div>
                      )}
                      {!isUser && m.proposals && <ProposalBlock proposals={m.proposals} />}
                    </div>
                  </div>
                );
              })}
              {loading && streamBuffer && (
                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <div className="max-w-[90%] rounded-md border border-wb-line bg-wb-surface px-3.5 py-2.5 text-sm leading-relaxed text-wb-ink/90">
                    <p className={`mb-1 text-[10px] uppercase tracking-[0.2em] ${activeAdvisor.dissent ? 'text-wb-crit-on' : 'text-wb-sage-deep'}`}>{activeAdvisor.label}</p>
                    <div className="prose prose-sm max-w-none prose-p:my-1"><ReactMarkdown>{streamBuffer}</ReactMarkdown></div>
                    <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-wb-sage-deep align-middle" />
                  </div>
                </div>
              )}
              {loading && !streamBuffer && (
                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <div className="rounded-md border border-wb-line bg-wb-surface px-4 py-3"><Dots size="sm" /></div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {QUICK_PROMPTS.map((p) => (
                <button key={p} onClick={() => send(p)} disabled={loading}
                  className="rounded-md border border-wb-line px-2.5 py-1 text-[10px] uppercase tracking-wider text-wb-ink2 transition-colors hover:border-wb-sage-deep hover:text-wb-sage-deep disabled:opacity-40">
                  {p}
                </button>
              ))}
            </div>
            {!activeAdvisor.useXoEndpoint && (
              <label className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-wb-ink2">
                Model
                <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}
                  className="rounded-md border border-wb-line bg-wb-bg px-2 py-1 text-xs normal-case tracking-normal text-wb-ink focus:border-wb-sage-deep focus:outline-none">
                  {AI_MODELS.filter((m) => m.available).map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
              </label>
            )}
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem' }}>
              <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown} rows={3}
                placeholder={`Message ${activeAdvisor.label}…`} disabled={loading}
                className="min-h-[72px] flex-1 resize-y rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus:border-wb-sage-deep focus:outline-none disabled:opacity-50" />
              <button onClick={() => send(input)} disabled={loading || !input.trim()}
                className="self-stretch rounded-md bg-wb-sage-deep px-4 text-sm font-semibold uppercase tracking-[0.15em] text-white transition-opacity hover:opacity-80 disabled:opacity-40">
                Send
              </button>
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}
