'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { LCARSPanel } from '@/components/LCARSPanel';

// ── Types ──────────────────────────────────────────────────────────────────────

type TopTab = 'chat' | 'brief' | 'advisors' | 'intelligence';
type IntelTab = 'awareness' | 'proactive' | 'wellness';

interface OfficerPerspective {
  officer: string;
  recommendation: string;
  confidence: number;
  stance?: string;
}
interface Confidence { value: number; band: string; basis?: string }

interface AdvisoryResult {
  question?: string;
  executive_summary?: string;
  bottom_line?: string;
  recommendation?: string;
  risks_and_challenges?: string[];
  confidence?: Confidence;
  officer_perspectives?: OfficerPerspective[];
  awareness?: unknown[];
  signals?: unknown[];
  cadence?: unknown;
  [key: string]: unknown;
}

interface Msg {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  error?: boolean;
}

// ── Advisory block ─────────────────────────────────────────────────────────────

function AdvisoryBlock({ data }: { data: AdvisoryResult }) {
  const conf = typeof data.confidence === 'object' && data.confidence
    ? data.confidence
    : null;

  return (
    <div className="space-y-3 text-sm">
      {(data.executive_summary || data.bottom_line) && (
        <div className="rounded-lcars border border-command/30 bg-command/10 px-3 py-2">
          <p className="mb-1 text-[10px] uppercase tracking-[0.15em] text-command">Summary</p>
          <p className="text-lcars-text leading-relaxed">{String(data.executive_summary ?? data.bottom_line ?? '')}</p>
        </div>
      )}
      {data.recommendation && (
        <div className="rounded-lcars border border-science/30 bg-science/10 px-3 py-2">
          <p className="mb-1 text-[10px] uppercase tracking-[0.15em] text-science">Recommendation</p>
          <p className="text-lcars-text leading-relaxed">{String(data.recommendation)}</p>
        </div>
      )}
      {Array.isArray(data.risks_and_challenges) && data.risks_and_challenges.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] uppercase tracking-[0.15em] text-operations">Risks</p>
          <ul className="space-y-1">
            {data.risks_and_challenges.map((r, i) => (
              <li key={i} className="flex gap-2 text-lcars-text/80">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-operations" />
                {String(r)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {Array.isArray(data.officer_perspectives) && data.officer_perspectives.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] uppercase tracking-[0.15em] text-medical">Officer Perspectives</p>
          <div className="space-y-1.5">
            {data.officer_perspectives.map((op, i) => (
              <div key={i} className="rounded-lcars border border-edge bg-panel/40 px-2.5 py-1.5">
                <p className="text-[10px] uppercase tracking-wider text-medical">{op.officer}</p>
                <p className="text-lcars-text/80">{op.recommendation}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      {conf && (
        <p className="text-[10px] text-lcars-muted">
          Confidence: {conf.band ?? ''} ({conf.value ?? ''})
          {conf.basis ? ` — ${conf.basis}` : ''}
        </p>
      )}
    </div>
  );
}

// ── Intelligence panel renderers ───────────────────────────────────────────────

function TrendPill({ label, dir }: { label: string; dir: string }) {
  const tone = dir === 'improving' ? 'text-medical border-medical/40 bg-medical/10'
    : dir === 'worsening' ? 'text-operations border-operations/40 bg-operations/10'
    : 'text-lcars-muted border-edge bg-panel/40';
  const arrow = dir === 'improving' ? '↑' : dir === 'worsening' ? '↓' : '–';
  return (
    <span className={`inline-flex items-center gap-1 rounded-lcars border px-2 py-0.5 text-xs ${tone}`}>
      {arrow} {label}
    </span>
  );
}

function AwarenessCard({ data }: { data: Record<string, unknown> }) {
  const narrative = data.narrative as string | undefined;
  const trends = (data.trends ?? {}) as Record<string, string>;
  const improving = (data.improving ?? []) as string[];
  const worsening = (data.worsening ?? []) as string[];
  const priorities = (data.recovery_priorities ?? []) as string[];
  return (
    <div className="space-y-3">
      {narrative && (
        <p className="text-sm text-lcars-text/90 leading-relaxed border-l-2 border-science/50 pl-3">{narrative}</p>
      )}
      {Object.keys(trends).length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-lcars-muted mb-1.5">Trends</p>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(trends).map(([k, v]) => (
              <TrendPill key={k} label={k.replace(/_/g, ' ')} dir={String(v)} />
            ))}
          </div>
        </div>
      )}
      {(improving.length > 0 || worsening.length > 0) && (
        <div className="grid grid-cols-2 gap-3">
          {improving.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-medical mb-1">Improving</p>
              <ul className="space-y-0.5">{improving.map((s, i) => <li key={i} className="text-xs text-lcars-text/80">↑ {s}</li>)}</ul>
            </div>
          )}
          {worsening.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-operations mb-1">Needs attention</p>
              <ul className="space-y-0.5">{worsening.map((s, i) => <li key={i} className="text-xs text-lcars-text/80">↓ {s}</li>)}</ul>
            </div>
          )}
        </div>
      )}
      {priorities.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-lcars-muted mb-1">Recovery priorities</p>
          <ul className="space-y-0.5">{priorities.map((p, i) => <li key={i} className="text-xs text-lcars-text/80">· {p}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

function SignalsCard({ data }: { data: Record<string, unknown> }) {
  const headline = data.headline as string | undefined;
  const note = data.note as string | undefined;
  const attnRequired = data.attention_required as boolean | undefined;
  const triggers = (data.triggers ?? []) as unknown[];
  const opportunities = (data.opportunities ?? []) as unknown[];
  const health = (data.advisory_health ?? {}) as Record<string, unknown>;
  return (
    <div className="space-y-3">
      {headline && (
        <p className={`text-sm font-semibold ${attnRequired ? 'text-operations' : 'text-lcars-text/90'}`}>
          {attnRequired ? '▲ ' : '● '}{headline}
        </p>
      )}
      {triggers.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-operations mb-1">Triggers</p>
          <ul className="space-y-0.5">{triggers.map((t, i) => <li key={i} className="text-xs text-lcars-text/80">· {typeof t === 'string' ? t : JSON.stringify(t)}</li>)}</ul>
        </div>
      )}
      {opportunities.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-science mb-1">Opportunities</p>
          <ul className="space-y-0.5">{opportunities.map((o, i) => <li key={i} className="text-xs text-lcars-text/80">· {typeof o === 'string' ? o : JSON.stringify(o)}</li>)}</ul>
        </div>
      )}
      {typeof health.narrative === 'string' && health.narrative && (
        <p className="text-xs text-lcars-muted border-l border-edge pl-2">{health.narrative}</p>
      )}
      {note && <p className="text-[11px] text-lcars-muted italic">{note}</p>}
    </div>
  );
}

function OperationalCard({ data }: { data: Record<string, unknown> }) {
  const bottomLine = data.bottom_line as string | undefined;
  const note = data.note as string | undefined;
  const sections = (data.sections ?? []) as Array<{ heading: string; items?: string[]; text?: string; suppressed?: number }>;
  return (
    <div className="space-y-3">
      {bottomLine && (
        <p className="text-sm font-semibold text-command border-l-2 border-command/50 pl-3">{bottomLine}</p>
      )}
      {sections.map((s, i) => (
        <div key={i}>
          <p className="text-[10px] uppercase tracking-widest text-lcars-muted mb-1">{s.heading}</p>
          {s.text && <p className="text-xs text-lcars-text/80">{s.text}</p>}
          {s.items && s.items.length > 0 && (
            <ul className="space-y-0.5">{s.items.map((item, j) => <li key={j} className="text-xs text-lcars-text/80">· {item}</li>)}</ul>
          )}
        </div>
      ))}
      {note && <p className="text-[11px] text-lcars-muted italic">{note}</p>}
    </div>
  );
}

function IntelResultCard({ action, data }: { action: string; data: unknown }) {
  if (!data || typeof data !== 'object') return <p className="text-sm text-lcars-muted">No data available.</p>;
  const obj = data as Record<string, unknown>;
  if (action === 'awareness') return <AwarenessCard data={obj} />;
  if (action === 'proactive') return <SignalsCard data={obj} />;
  if (action === 'wellness') return <OperationalCard data={obj} />;
  return (
    <div className="rounded-lcars border border-edge bg-panel/40 px-3 py-2.5 text-xs text-lcars-muted whitespace-pre-wrap">
      {JSON.stringify(data, null, 2)}
    </div>
  );
}

// ── Tab button ─────────────────────────────────────────────────────────────────

function TabBtn({
  label, active, onClick,
}: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={[
        'rounded-lcars border px-4 py-1.5 font-lcars text-xs uppercase tracking-[0.15em] transition-colors',
        active
          ? 'border-command bg-command/10 text-command'
          : 'border-edge text-lcars-muted hover:border-edge/60',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

// ── Chat mode ──────────────────────────────────────────────────────────────────

const QUICK_PROMPTS = [
  'What needs my decision?',
  'Protect or defer?',
  'What changed since yesterday?',
  'Challenge this assumption',
];

const LS_KEY = 'lcars-cos-chat-history';

function ChatMode() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState('');
  const [xoDisabled, setXoDisabled] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load history
  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) setMessages(JSON.parse(raw) as Msg[]);
    } catch { /* ignore */ }
  }, []);

  // Persist history
  useEffect(() => {
    try { localStorage.setItem(LS_KEY, JSON.stringify(messages)); } catch { /* ignore */ }
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamBuffer]);

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setInput('');
    const userMsg: Msg = { id: Date.now().toString(), role: 'user', content: trimmed };
    const history = [...messages, userMsg];
    setMessages(history);
    setLoading(true);
    setStreamBuffer('');

    try {
      const res = await fetch('/api/xo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history.map((m) => ({ role: m.role, content: m.content })) }),
      });

      if (res.status === 503 || res.status === 404) {
        setXoDisabled(true);
        setLoading(false);
        return;
      }

      if (!res.body) throw new Error('No response body');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let acc = '';
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (payload === '[DONE]') break;
          try {
            const parsed = JSON.parse(payload) as { token?: string };
            if (parsed.token) {
              acc += parsed.token;
              setStreamBuffer(acc);
            }
          } catch { /* skip malformed */ }
        }
      }

      const assistantMsg: Msg = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: acc || '(no response)',
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setStreamBuffer('');
    } catch (err) {
      const e = err as Error;
      if (e.message.includes('fetch') || e.message.includes('ECONNREFUSED')) {
        setXoDisabled(true);
      } else {
        setMessages((prev) => [
          ...prev,
          { id: (Date.now() + 1).toString(), role: 'assistant', content: 'Error contacting XO.', error: true },
        ]);
      }
    } finally {
      setLoading(false);
      setStreamBuffer('');
    }
  }, [messages, loading]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  if (xoDisabled) {
    return (
      <LCARSPanel title="Chat — Chief of Staff" accent="command">
        <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
          <p className="text-lcars-muted text-sm">XO model is offline (OLLAMA_CLOUD_ENABLED not set).</p>
          <p className="text-lcars-text/60 text-xs max-w-sm">
            Switch to the <span className="text-command font-semibold">Advisors</span> tab for LLM-backed advisory from CMO, CTO, CDO, and Strategic Advisor.
          </p>
        </div>
      </LCARSPanel>
    );
  }

  return (
    <LCARSPanel title="Chat — Chief of Staff" accent="command"
      actions={
        messages.length > 0 ? (
          <button
            onClick={() => { setMessages([]); localStorage.removeItem(LS_KEY); }}
            disabled={loading}
            className="rounded-lcars border border-edge px-3 py-1 text-[10px] uppercase tracking-widest text-lcars-muted hover:text-operations transition-colors disabled:opacity-40"
          >
            Clear
          </button>
        ) : undefined
      }
    >
      <div className="flex flex-col gap-3" style={{ height: '60vh' }}>
        {/* Message list */}
        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          {messages.length === 0 && !loading && (
            <p className="text-lcars-muted text-sm text-center py-8">
              Chief of Staff standing by. What do you need?
            </p>
          )}
          {messages.map((m) => {
            const isUser = m.role === 'user';
            return (
              <div key={m.id} style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
                <div
                  className={[
                    'rounded-lcars border px-3.5 py-2.5 text-sm leading-relaxed',
                    isUser
                      ? 'border-command/40 bg-command/10 text-lcars-text'
                      : m.error
                      ? 'border-operations/40 bg-operations/10 text-operations'
                      : 'border-edge bg-panel/60 text-lcars-text/90',
                  ].join(' ')}
                  style={{ maxWidth: '90%' }}
                >
                  {!isUser && !m.error && (
                    <p className="mb-1 text-[10px] uppercase tracking-[0.2em] text-science">Chief of Staff</p>
                  )}
                  {isUser ? (
                    <span className="whitespace-pre-wrap">{m.content}</span>
                  ) : (
                    <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-headings:text-lcars-text prose-headings:font-lcars prose-strong:text-lcars-text prose-li:my-0.5 prose-code:text-command prose-code:bg-space/60 prose-code:px-1 prose-code:rounded">
                      <ReactMarkdown>{m.content}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {loading && streamBuffer && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div className="max-w-[90%] rounded-lcars border border-edge bg-panel/60 px-3.5 py-2.5 text-sm leading-relaxed text-lcars-text/90">
                <p className="mb-1 text-[10px] uppercase tracking-[0.2em] text-science">Chief of Staff</p>
                <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-headings:text-lcars-text prose-headings:font-lcars prose-strong:text-lcars-text prose-li:my-0.5 prose-code:text-command prose-code:bg-space/60 prose-code:px-1 prose-code:rounded">
                  <ReactMarkdown>{streamBuffer}</ReactMarkdown>
                </div>
                <span className="inline-block w-1.5 h-3.5 bg-science animate-pulse ml-0.5 align-middle" />
              </div>
            </div>
          )}
          {loading && !streamBuffer && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div className="rounded-lcars border border-edge bg-panel/60 px-4 py-3">
                <div style={{ display: 'flex', height: '12px', alignItems: 'center', gap: '6px' }}>
                  {[0, 1, 2].map((i) => (
                    <span key={i} className="h-1.5 w-1.5 animate-pulse rounded-full bg-science"
                      style={{ animationDelay: `${i * 150}ms` }} />
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Quick prompts */}
        <div className="flex flex-wrap gap-1.5">
          {QUICK_PROMPTS.map((p) => (
            <button
              key={p}
              onClick={() => send(p)}
              disabled={loading}
              className="rounded-lcars border border-edge px-2.5 py-1 text-[10px] uppercase tracking-wider text-lcars-muted hover:border-science hover:text-science transition-colors disabled:opacity-40"
            >
              {p}
            </button>
          ))}
        </div>

        {/* Input */}
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem' }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            placeholder="Message Chief of Staff…"
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
    </LCARSPanel>
  );
}

// ── Brief mode ─────────────────────────────────────────────────────────────────

function BriefMode() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AdvisoryResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchBrief = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch('/api/advisory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'daily-brief' }),
      });
      const data = (await res.json()) as { result?: AdvisoryResult; error?: string };
      if (data.error) { setError(data.error); return; }
      setResult(data.result ?? (data as unknown as AdvisoryResult));
    } catch (err) {
      setError((err as Error).message ?? 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchBrief(); }, [fetchBrief]);

  return (
    <LCARSPanel title="Daily Brief" accent="science"
      actions={
        <button onClick={fetchBrief} disabled={loading}
          className="rounded-lcars border border-edge px-3 py-1 text-[10px] uppercase tracking-widest text-lcars-muted hover:text-science transition-colors disabled:opacity-40">
          Refresh
        </button>
      }
    >
      {loading && (
        <div className="flex items-center gap-3 py-8">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-science"
              style={{ animationDelay: `${i * 150}ms` }} />
          ))}
          <span className="text-lcars-muted text-sm">Fetching brief…</span>
        </div>
      )}
      {error && (
        <div className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations">
          <p className="font-semibold mb-1">Intelligence runtime offline</p>
          <p className="text-operations/80 text-xs">{error}</p>
          <p className="mt-2 text-lcars-muted text-xs">Switch to Advisors tab for direct officer consultation.</p>
        </div>
      )}
      {result && !loading && <AdvisoryBlock data={result} />}
    </LCARSPanel>
  );
}

// ── Advisors mode ──────────────────────────────────────────────────────────────

interface Advisor {
  id: string;
  label: string;
  accent: string;
  officer_id?: string;
}

const ADVISORS: Advisor[] = [
  { id: 'cmo', label: 'CMO', accent: 'text-medical', officer_id: 'cmo' },
  { id: 'cto', label: 'CTO', accent: 'text-engineering', officer_id: 'cto' },
  { id: 'cdo', label: 'CDO', accent: 'text-command', officer_id: 'cdo' },
  { id: 'strategic', label: 'Strategic Advisor', accent: 'text-operations', officer_id: 'strategic' },
  { id: 'staff', label: 'Staff Briefing', accent: 'text-science' },
];

interface AdvisoryMsg {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  structured?: AdvisoryResult;
  error?: boolean;
}

function AdvisorsMode() {
  const [activeAdvisor, setActiveAdvisor] = useState<Advisor>(ADVISORS[0]);
  const [threads, setThreads] = useState<Record<string, AdvisoryMsg[]>>({});
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [threads, activeAdvisor]);

  const messages = threads[activeAdvisor.id] ?? [];

  const send = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    setInput('');
    const userMsg: AdvisoryMsg = { id: Date.now().toString(), role: 'user', content: trimmed };
    setThreads((prev) => ({
      ...prev,
      [activeAdvisor.id]: [...(prev[activeAdvisor.id] ?? []), userMsg],
    }));
    setLoading(true);

    try {
      const body: Record<string, unknown> = { action: 'advice', question: trimmed };
      if (activeAdvisor.officer_id) body.officer_id = activeAdvisor.officer_id;

      const res = await fetch('/api/advisory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = (await res.json()) as { result?: AdvisoryResult; error?: string };
      const assistantMsg: AdvisoryMsg = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.error ?? '',
        structured: data.error ? undefined : (data.result ?? (data as unknown as AdvisoryResult)),
        error: !!data.error,
      };
      setThreads((prev) => ({
        ...prev,
        [activeAdvisor.id]: [...(prev[activeAdvisor.id] ?? []), assistantMsg],
      }));
    } catch (err) {
      setThreads((prev) => ({
        ...prev,
        [activeAdvisor.id]: [
          ...(prev[activeAdvisor.id] ?? []),
          { id: (Date.now() + 1).toString(), role: 'assistant', content: (err as Error).message, error: true },
        ],
      }));
    } finally {
      setLoading(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <div style={{ display: 'flex', gap: '1rem', height: '65vh' }}>
      {/* Sidebar */}
      <div className="flex flex-col gap-1.5 w-40 shrink-0 pt-1">
        {ADVISORS.map((a) => (
          <button
            key={a.id}
            onClick={() => setActiveAdvisor(a)}
            className={[
              'rounded-lcars border px-3 py-2 text-left text-xs font-lcars uppercase tracking-wider transition-colors',
              activeAdvisor.id === a.id
                ? `border-command bg-command/10 ${a.accent}`
                : `border-edge text-lcars-muted hover:border-edge/60`,
            ].join(' ')}
          >
            {a.label}
          </button>
        ))}
      </div>

      {/* Thread */}
      <LCARSPanel title={activeAdvisor.label} accent="command" className="flex-1 min-w-0">
        <div className="flex flex-col gap-3 h-full">
          <div className="flex-1 overflow-y-auto space-y-3 pr-1">
            {messages.length === 0 && !loading && (
              <p className="text-lcars-muted text-sm py-6 text-center">Ask {activeAdvisor.label} a question.</p>
            )}
            {messages.map((m) => {
              const isUser = m.role === 'user';
              return (
                <div key={m.id} style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
                  <div
                    className={[
                      'rounded-lcars border px-3.5 py-2.5 text-sm',
                      isUser ? 'border-command/40 bg-command/10 text-lcars-text'
                        : m.error ? 'border-operations/40 bg-operations/10 text-operations'
                        : 'border-edge bg-panel/60 text-lcars-text/90',
                    ].join(' ')}
                    style={{ maxWidth: '92%' }}
                  >
                    {!isUser && !m.error && (
                      <p className={`mb-1 text-[10px] uppercase tracking-[0.2em] ${activeAdvisor.accent}`}>
                        {activeAdvisor.label}
                      </p>
                    )}
                    {isUser ? (
                      <span className="whitespace-pre-wrap">{m.content}</span>
                    ) : m.structured ? (
                      <AdvisoryBlock data={m.structured} />
                    ) : (
                      <span>{m.content}</span>
                    )}
                  </div>
                </div>
              );
            })}
            {loading && (
              <div style={{ display: 'flex' }}>
                <div className="rounded-lcars border border-edge bg-panel/60 px-4 py-3">
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    {[0, 1, 2].map((i) => (
                      <span key={i} className="h-1.5 w-1.5 animate-pulse rounded-full bg-science"
                        style={{ animationDelay: `${i * 150}ms` }} />
                    ))}
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem' }}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={2}
              placeholder={`Ask ${activeAdvisor.label}…`}
              disabled={loading}
              className="flex-1 resize-none rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-science focus:outline-none disabled:opacity-50"
            />
            <button
              onClick={send}
              disabled={loading || !input.trim()}
              className="self-stretch rounded-lcars bg-science px-4 font-lcars text-sm font-bold uppercase tracking-[0.15em] text-space transition-opacity hover:opacity-80 disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </div>
      </LCARSPanel>
    </div>
  );
}

// ── Intelligence mode ──────────────────────────────────────────────────────────

const INTEL_TABS: { id: IntelTab; label: string; action: string }[] = [
  { id: 'awareness', label: 'Awareness', action: 'awareness' },
  { id: 'proactive', label: 'Signals', action: 'proactive' },
  { id: 'wellness', label: 'Operational', action: 'wellness' },
];

function IntelPanel({ action }: { action: string }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch('/api/advisory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      const data = (await res.json()) as { result?: unknown; error?: string };
      if (data.error) { setError(data.error); return; }
      setResult(data.result ?? data);
    } catch (err) {
      setError((err as Error).message ?? 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [action]);

  useEffect(() => { fetch_(); }, [fetch_]);

  const items = Array.isArray(result) ? result : result ? [result] : [];

  return (
    <div>
      {loading && (
        <div className="flex items-center gap-3 py-6">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-science"
              style={{ animationDelay: `${i * 150}ms` }} />
          ))}
        </div>
      )}
      {error && (
        <div className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations">
          <p className="font-semibold">Intelligence runtime offline</p>
          <p className="text-xs mt-1 text-operations/80">{error}</p>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <p className="text-lcars-muted text-sm py-6">No data available.</p>
      )}
      <div className="space-y-2 mt-2">
        {items.map((item, i) => <IntelResultCard key={i} action={action} data={item} />)}
      </div>
      {!loading && (
        <button onClick={fetch_}
          className="mt-3 rounded-lcars border border-edge px-3 py-1 text-[10px] uppercase tracking-widest text-lcars-muted hover:text-science transition-colors">
          Refresh
        </button>
      )}
    </div>
  );
}

function IntelligenceMode() {
  const [tab, setTab] = useState<IntelTab>('awareness');
  const active = INTEL_TABS.find((t) => t.id === tab)!;

  return (
    <LCARSPanel title="Intelligence" accent="science">
      <div className="flex gap-2 mb-4">
        {INTEL_TABS.map((t) => (
          <TabBtn key={t.id} label={t.label} active={tab === t.id} onClick={() => setTab(t.id)} />
        ))}
      </div>
      <IntelPanel key={active.id} action={active.action} />
    </LCARSPanel>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

const TOP_TABS: { id: TopTab; label: string }[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'brief', label: 'Daily Brief' },
  { id: 'advisors', label: 'Advisors' },
  { id: 'intelligence', label: 'Intelligence' },
];

export default function ChiefOfStaffPage() {
  const [tab, setTab] = useState<TopTab>('chat');

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-lcars text-xl uppercase tracking-[0.2em] text-lcars-text">
            Chief of Staff
          </h1>
          <p className="text-xs text-lcars-muted tracking-wider mt-0.5">
            Personal advisory command centre
          </p>
        </div>
      </div>

      {/* Mode tabs */}
      <div className="flex gap-2 flex-wrap">
        {TOP_TABS.map((t) => (
          <TabBtn key={t.id} label={t.label} active={tab === t.id} onClick={() => setTab(t.id)} />
        ))}
      </div>

      {/* Active mode */}
      {tab === 'chat' && <ChatMode />}
      {tab === 'brief' && <BriefMode />}
      {tab === 'advisors' && <AdvisorsMode />}
      {tab === 'intelligence' && <IntelligenceMode />}
    </div>
  );
}
