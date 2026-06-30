'use client';

import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { useRouter } from 'next/navigation';
import { captureItem } from '@/lib/capture';

const XO_STORAGE_KEY = 'lcars-xo-history';

interface ActionResult {
  type: string;
  success: boolean;
  detail: string;
  id?: string;
}

interface Msg {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  error?: boolean;
  actions?: ActionResult[];
}

const INTENTS: { label: string; prompt: string }[] = [
  { label: 'What needs my decision?', prompt: 'What needs my decision today? Be specific and rank by urgency.' },
  { label: 'Protect or defer?', prompt: 'Given my current capacity and open missions, what should I protect, pause, or defer today?' },
  { label: 'Triage captured missions', prompt: 'I have captured items marked as missions awaiting triage. Help me decide what to promote, defer, or drop.' },
  { label: 'Engineering blockers', prompt: 'What is blocked in engineering right now and what is the single most useful thing I can do about it?' },
];

function newId() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

/** Pull the "→ Next action:" line XO is instructed to end with. */
function extractNextAction(text: string): string | null {
  const m = text.match(/→\s*Next action:\s*(.+)$/im);
  return m ? m[1].trim() : null;
}

export default function XOChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState('');
  const [actionFlash, setActionFlash] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(XO_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as Msg[];
        if (Array.isArray(parsed) && parsed.length > 0) setMessages(parsed);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (messages.length === 0) return;
    try { localStorage.setItem(XO_STORAGE_KEY, JSON.stringify(messages.slice(-30))); } catch { /* ignore */ }
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, streamBuffer]);

  const lastUserMessage = [...messages].reverse().find((m) => m.role === 'user')?.content ?? '';

  async function send(text: string) {
    const body = text.trim();
    if (!body || loading) return;
    const userMsg: Msg = { id: newId(), role: 'user', content: body };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    const history = [...messages, userMsg].map(({ role, content }) => ({ role, content }));
    try {
      const res = await fetch('/api/xo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setMessages((prev) => [
          ...prev,
          { id: newId(), role: 'assistant', content: data.error ?? 'XO is unavailable.', error: true },
        ]);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error('No response body');
      const decoder = new TextDecoder();
      let accumulated = '';
      let lineBuffer = '';
      let capturedActions: ActionResult[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        lineBuffer += decoder.decode(value, { stream: true });
        const lines = lineBuffer.split('\n');
        lineBuffer = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6);
          if (payload === '[DONE]') break;
          try {
            const chunk = JSON.parse(payload);
            if (chunk.error) throw new Error(chunk.error);
            if (chunk.token) { accumulated += chunk.token; setStreamBuffer(accumulated); }
            if (chunk.actions) capturedActions = chunk.actions;
          } catch (e) {
            if (e instanceof Error && e.message !== 'JSON parse') throw e;
          }
        }
      }

      setMessages((prev) => [...prev, {
        id: newId(),
        role: 'assistant',
        content: accumulated || '(no reply)',
        actions: capturedActions.length > 0 ? capturedActions : undefined,
      }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: 'assistant', content: 'Could not reach XO. You can still route or capture below.', error: true },
      ]);
    } finally {
      setLoading(false);
      setStreamBuffer('');
      inputRef.current?.focus();
    }
  }

  async function captureLastAs(type: 'mission' | 'note') {
    const source = lastUserMessage || input.trim();
    if (!source) {
      setActionFlash('Nothing to capture yet — ask or type something first.');
      setTimeout(() => setActionFlash(null), 2500);
      return;
    }
    const res = await captureItem(source, type);
    setActionFlash(res.ok ? `Captured as ${type}. Routed to the Captain's Inbox.` : `Capture failed: ${res.error}`);
    setTimeout(() => setActionFlash(null), 2800);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-13rem)] max-w-[640px] flex-col gap-3">
      <header className="shrink-0 flex items-start justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">Executive Officer</p>
          <h1 className="font-lcars text-2xl font-bold text-science">XO Chat</h1>
          <p className="text-xs text-lcars-muted">Ask, route, clarify. XO turns intent into the next action.</p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={() => {
              setMessages([]);
              try { localStorage.removeItem(XO_STORAGE_KEY); } catch { /* ignore */ }
            }}
            className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-operations transition-colors mt-1"
          >
            Clear
          </button>
        )}
      </header>

      {/* Message history */}
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto rounded-lcars border border-edge bg-space/60 p-3">
        {messages.length === 0 && !loading && (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
            <p className="text-xs text-lcars-muted">Start with one of these:</p>
            <div className="flex flex-wrap justify-center gap-2">
              {INTENTS.map((it) => (
                <button
                  key={it.label}
                  onClick={() => send(it.prompt)}
                  className="rounded-lcars border border-science/40 bg-science/5 px-3 py-2 text-xs text-science hover:bg-science/15"
                >
                  {it.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => {
          const isUser = m.role === 'user';
          const nextAction = !isUser && !m.error ? extractNextAction(m.content) : null;
          const displayContent = nextAction
            ? m.content.replace(/→\s*Next action:.*$/im, '').trimEnd()
            : m.content;
          return (
            <div key={m.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div
                className={[
                  'max-w-[88%] rounded-lcars border px-3.5 py-2.5 text-sm leading-relaxed',
                  isUser
                    ? 'border-command/40 bg-command/10 text-lcars-text'
                    : m.error
                    ? 'border-operations/40 bg-operations/10 text-operations'
                    : 'border-edge bg-panel/60 text-lcars-text/90',
                ].join(' ')}
              >
                {!isUser && !m.error && (
                  <p className="mb-1 text-[10px] uppercase tracking-[0.2em] text-science">XO</p>
                )}
                {isUser ? (
                  <span className="whitespace-pre-wrap">{displayContent}</span>
                ) : (
                  <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-headings:text-lcars-text prose-headings:font-lcars prose-strong:text-lcars-text prose-li:my-0.5 prose-code:text-command prose-code:bg-space/60 prose-code:px-1 prose-code:rounded">
                    <ReactMarkdown>{displayContent}</ReactMarkdown>
                  </div>
                )}
                {m.actions && m.actions.length > 0 && (
                  <div className="mt-2 border-t border-edge pt-2">
                    <p className="mb-1 text-[10px] uppercase tracking-[0.2em] text-engineering">Actions Executed</p>
                    {m.actions.map((a, i) => (
                      <div key={i} className="flex items-start gap-1.5 text-xs">
                        <span>{a.success ? '✅' : '⚠️'}</span>
                        <span className={a.success ? 'text-lcars-text/80' : 'text-operations'}>{a.detail}</span>
                      </div>
                    ))}
                  </div>
                )}
                {nextAction && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-edge pt-2">
                    <span className="text-[10px] uppercase tracking-[0.15em] text-lcars-muted">Next:</span>
                    <span className="text-xs font-semibold text-command">{nextAction}</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && streamBuffer && (
          <div className="flex justify-start">
            <div className="max-w-[88%] rounded-lcars border border-edge bg-panel/60 px-3.5 py-2.5 text-sm leading-relaxed text-lcars-text/90">
              <p className="mb-1 text-[10px] uppercase tracking-[0.2em] text-science">XO</p>
              <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-headings:text-lcars-text prose-headings:font-lcars prose-strong:text-lcars-text prose-li:my-0.5 prose-code:text-command prose-code:bg-space/60 prose-code:px-1 prose-code:rounded">
                <ReactMarkdown>{streamBuffer}</ReactMarkdown>
              </div>
              <span className="inline-block w-1.5 h-3.5 bg-science animate-pulse ml-0.5 align-middle" />
            </div>
          </div>
        )}
        {loading && !streamBuffer && (
          <div className="flex justify-start">
            <div className="rounded-lcars border border-edge bg-panel/60 px-4 py-3">
              <div className="flex h-3 items-center gap-1.5">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="h-1.5 w-1.5 animate-pulse rounded-full bg-science" style={{ animationDelay: `${i * 150}ms` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Action row — works with or without the model */}
      <div className="shrink-0 flex flex-wrap gap-2">
        <button onClick={() => captureLastAs('mission')} className="rounded-lcars border border-engineering/40 bg-engineering/5 px-3 py-1.5 text-xs font-semibold text-engineering hover:bg-engineering/15">
          ★ Capture as mission
        </button>
        <button onClick={() => captureLastAs('note')} className="rounded-lcars border border-command/40 bg-command/5 px-3 py-1.5 text-xs font-semibold text-command hover:bg-command/15">
          ✎ Capture as note
        </button>
        <button onClick={() => router.push('/engineering-queue')} className="rounded-lcars border border-edge px-3 py-1.5 text-xs font-semibold text-lcars-muted hover:text-engineering">
          ⚙ Engineering queue
        </button>
        <button onClick={() => router.push('/alerts')} className="rounded-lcars border border-edge px-3 py-1.5 text-xs font-semibold text-lcars-muted hover:text-operations">
          ◆ Alerts
        </button>
      </div>

      {actionFlash && (
        <div className="shrink-0 rounded-lcars border border-status/40 bg-status/10 px-3 py-2 text-xs text-status">
          {actionFlash}
        </div>
      )}

      {/* Input */}
      <div className="shrink-0 flex items-end gap-2">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="Ask XO, or describe what you want to happen…"
          disabled={loading}
          className="flex-1 resize-none rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-science focus:outline-none disabled:opacity-50"
        />
        <button
          onClick={() => send(input)}
          disabled={loading || !input.trim()}
          className="self-stretch rounded-lcars bg-science px-4 font-lcars text-sm font-bold uppercase tracking-[0.15em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </div>
  );
}
