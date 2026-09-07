'use client';

// Officer Advisors — the 18-role roster, retired from Advisory's primary
// nav (mission §9: it doesn't map cleanly to Ask's actual specialist
// registry) and now mounted as an "Advanced" disclosure inside ThinkView
// instead. Endpoints unchanged: streaming POST /api/ai/chat and POST
// /api/xo, POST /api/advisory-sessions (persist, mode:'consult'). The
// MSN-0352 governance path (backend ActionResult[] → ProposalBlock, never
// model prose) is preserved verbatim.

import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { AI_MODELS, DEFAULT_MODEL_ID } from '@/lib/ai-models';
import type { ActionResult } from '@/lib/ai-actions';
import { Panel, Dots, COUNCIL, ProposalBlock } from './shared';
import type { CouncilAdvisor, Msg } from './types';

const LS_CONSULT_KEY = 'lcars-council-consult-history';

const actionBtn = 'rounded-md border border-wb-line px-3 py-1 text-[10px] uppercase tracking-widest text-wb-ink2 transition-colors hover:text-wb-sage-deep focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep';
const chipBase = 'rounded-md border px-3 py-1 text-[10px] uppercase tracking-wider transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep';
const chipOff  = 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40 hover:text-wb-ink';
const chipOn   = 'border-wb-sage-deep bg-wb-sage-deep/15 text-wb-sage-deep';
const voiceOff = 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40';
const voiceOn  = 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep';

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

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); }
  };
  const clearThread = () => {
    setThreads((prev) => { const next = { ...prev }; delete next[activeAdvisor.id]; return next; });
  };

  const isOffline = offlineAdvisors.has(activeAdvisor.id);
  const groups = COUNCIL.reduce<Record<string, CouncilAdvisor[]>>((acc, a) => {
    (acc[a.group] = acc[a.group] ?? []).push(a);
    return acc;
  }, {});
  const groupHasHistory = (advisors: CouncilAdvisor[]) => advisors.some((a) => (threads[a.id]?.length ?? 0) > 0);

  return (
    <Panel
      title="Officer Advisors"
      actions={messages.length > 0 ? (
        <button onClick={clearThread} disabled={loading} className={actionBtn + ' disabled:opacity-40 disabled:cursor-not-allowed'}>
          Clear thread
        </button>
      ) : undefined}
    >
      <div className="space-y-4">

        {/* Group selector — horizontal chips, mirrors Perspectives category row */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] uppercase tracking-[0.15em] text-wb-ink2">Group</span>
          {Object.entries(groups).map(([group, advisors]) => {
            const isOpen = openGroup === group;
            const hasHistory = groupHasHistory(advisors);
            return (
              <button key={group} onClick={() => setOpenGroup(isOpen ? null : group)}
                className={`${chipBase} ${isOpen ? chipOn : chipOff} flex items-center gap-1.5`}>
                {group}
                {hasHistory && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-wb-sage-deep" aria-label="has conversation history" />}
                <span className="opacity-60">({advisors.length})</span>
              </button>
            );
          })}
        </div>

        {/* Officer pills within selected group — mirrors Perspectives voice pills */}
        {openGroup && (
          <div>
            <p className="mb-2 text-[10px] uppercase tracking-[0.15em] text-wb-ink2">
              Active: <span className="text-wb-ink">{activeAdvisor.label}</span>
            </p>
            <div className="flex flex-wrap gap-2">
              {groups[openGroup].map((a) => {
                const isActive = activeAdvisor.id === a.id;
                const accentOn = a.dissent ? 'border-wb-crit/60 bg-wb-crit/10 text-wb-crit-on' : voiceOn;
                return (
                  <button key={a.id} onClick={() => { setActiveAdvisor(a); setStreamBuffer(''); }}
                    className={`rounded-md border px-3 py-1.5 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep ${isActive ? accentOn : voiceOff}`}>
                    <p className="text-xs uppercase tracking-wider">{a.label}</p>
                    <p className="mt-0.5 text-[9px] leading-tight text-wb-ink2">{a.subtitle}</p>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Model selector — only for non-XO advisors */}
        {!activeAdvisor.useXoEndpoint && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-[0.2em] text-wb-ink2">Model</span>
            <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}
              className="rounded-md border border-wb-line bg-wb-bg px-2 py-1 text-xs text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep">
              {AI_MODELS.filter((m) => m.available).map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
          </div>
        )}

        {/* Input row — identical to Perspectives */}
        <div className="flex items-end gap-2">
          <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown} rows={3}
            placeholder={isOffline ? `${activeAdvisor.label} is offline.` : `Message ${activeAdvisor.label}…`}
            disabled={loading || isOffline}
            className="min-h-[72px] flex-1 resize-y rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-sm text-wb-ink placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep disabled:opacity-50" />
          <button onClick={() => send(input)} disabled={loading || !input.trim() || isOffline}
            className="self-stretch rounded-md bg-wb-sage-deep px-4 text-sm font-semibold uppercase tracking-[0.15em] text-white transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep disabled:opacity-40 disabled:cursor-not-allowed">
            Send
          </button>
        </div>

        {/* Loading indicator — identical to Perspectives */}
        {loading && (
          <div className="flex items-center gap-3 py-2">
            <Dots />
            <span className="text-sm text-wb-ink2">
              {streamBuffer ? `${activeAdvisor.label} responding…` : `Contacting ${activeAdvisor.label}…`}
            </span>
          </div>
        )}

        {/* Thread — response cards matching Perspectives card style */}
        {(messages.length > 0 || (loading && streamBuffer)) && (
          <div className="space-y-4">
            {messages.map((m) => {
              if (m.role === 'user') {
                return (
                  <div key={m.id} className="rounded-md border border-wb-line bg-wb-bg px-4 py-3">
                    <p className="mb-1 text-[10px] uppercase tracking-[0.15em] text-wb-ink2">You</p>
                    <p className="whitespace-pre-wrap text-sm text-wb-ink">{m.content}</p>
                  </div>
                );
              }
              const accent = activeAdvisor.dissent ? 'text-wb-crit-on' : 'text-wb-sage-deep';
              const borderAccent = activeAdvisor.dissent ? 'border-wb-crit/40' : 'border-wb-sage-deep/40';
              return (
                <div key={m.id} className={`rounded-md border bg-wb-surface ${m.error ? 'border-wb-crit/40' : borderAccent}`}>
                  <div className={`border-b px-4 py-2.5 ${m.error ? 'border-wb-crit/30' : 'border-wb-sage-deep/30'}`}>
                    <p className={`text-[11px] font-semibold uppercase tracking-widest ${m.error ? 'text-wb-crit-on' : accent}`}>
                      {activeAdvisor.label}
                    </p>
                  </div>
                  <div className="px-5 py-4">
                    {m.error
                      ? <p className="text-sm text-wb-crit-on">{m.content}</p>
                      : (
                        <div className="prose prose-base prose-headings:font-serif prose-headings:text-wb-ink prose-p:my-2 prose-p:leading-7 prose-strong:text-wb-ink">
                          <ReactMarkdown>{m.content}</ReactMarkdown>
                        </div>
                      )}
                    {!m.error && m.proposals && <ProposalBlock proposals={m.proposals} />}
                  </div>
                </div>
              );
            })}

            {/* Streaming card */}
            {loading && streamBuffer && (
              <div className={`rounded-md border bg-wb-surface ${activeAdvisor.dissent ? 'border-wb-crit/40' : 'border-wb-sage-deep/40'}`}>
                <div className={`border-b px-4 py-2.5 ${activeAdvisor.dissent ? 'border-wb-crit/30' : 'border-wb-sage-deep/30'}`}>
                  <p className={`text-[11px] font-semibold uppercase tracking-widest ${activeAdvisor.dissent ? 'text-wb-crit-on' : 'text-wb-sage-deep'}`}>
                    {activeAdvisor.label}
                  </p>
                </div>
                <div className="px-5 py-4">
                  <div className="prose prose-base prose-headings:font-serif prose-headings:text-wb-ink prose-p:my-2 prose-p:leading-7 prose-strong:text-wb-ink">
                    <ReactMarkdown>{streamBuffer}</ReactMarkdown>
                  </div>
                  <span aria-hidden="true" className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-wb-sage-deep align-middle" />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}

        {isOffline && (
          <div className="rounded-md border border-wb-line bg-wb-bg px-4 py-6 text-center">
            <p className="text-sm text-wb-ink2">{activeAdvisor.label} is offline (AI model not configured).</p>
            <p className="mt-1 text-xs text-wb-ink/60">Use <span className="font-semibold text-wb-sage-deep">Think</span> for advisory via the intelligence runtime.</p>
          </div>
        )}
      </div>
    </Panel>
  );
}
