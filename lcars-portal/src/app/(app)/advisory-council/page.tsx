'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { LCARSPanel } from '@/components/LCARSPanel';

// ── Types ──────────────────────────────────────────────────────────────────────

type TopTab = 'consult' | 'board' | 'perspectives';
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
  sections?: Array<{ heading: string; items?: string[]; text?: string; suppressed?: number }>;
  triggers?: unknown[];
  attention_required?: boolean;
  headline?: string;
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
  const conf = typeof data.confidence === 'object' && data.confidence ? data.confidence : null;
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
      {conf && (
        <p className="text-[10px] text-lcars-muted">
          Confidence: {conf.band ?? ''} ({conf.value ?? ''})
          {conf.basis ? ` — ${conf.basis}` : ''}
        </p>
      )}
    </div>
  );
}

// ── Operational card ───────────────────────────────────────────────────────────

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
          {s.suppressed !== undefined && s.suppressed > 0 && (
            <p className="text-[10px] text-lcars-muted mt-0.5">+{s.suppressed} suppressed</p>
          )}
        </div>
      ))}
      {note && <p className="text-[11px] text-lcars-muted italic">{note}</p>}
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
      {narrative && <p className="text-sm text-lcars-text/90 leading-relaxed border-l-2 border-science/50 pl-3">{narrative}</p>}
      {Object.keys(trends).length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-lcars-muted mb-1.5">Trends</p>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(trends).map(([k, v]) => <TrendPill key={k} label={k.replace(/_/g, ' ')} dir={String(v)} />)}
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

function TabBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2 text-xs uppercase tracking-[0.15em] whitespace-nowrap transition-colors ${
        active
          ? 'border-b-2 border-command text-command font-semibold -mb-px'
          : 'text-lcars-muted hover:text-lcars-text'
      }`}
    >
      {label}
    </button>
  );
}

// ── Proactive signals banner (MSN-0206) ────────────────────────────────────────

function ProactiveSignalsBanner() {
  const [signals, setSignals] = useState<{ headline?: string; triggers?: unknown[]; attention_required?: boolean } | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    fetch('/api/advisory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'proactive' }),
    })
      .then((r) => r.json())
      .then((data: { result?: AdvisoryResult }) => {
        const r = data.result ?? (data as unknown as AdvisoryResult);
        const triggers = (r?.triggers ?? []) as unknown[];
        if (triggers.length > 0 || r?.attention_required) setSignals(r as typeof signals);
      })
      .catch(() => { /* proactive signals are best-effort */ });
  }, []);

  if (!signals || dismissed) return null;

  const isUrgent = signals.attention_required;
  const triggerList = (signals.triggers ?? []) as string[];

  return (
    <div className={`rounded-lcars border px-3 py-2.5 flex items-start gap-3 text-sm ${
      isUrgent ? 'border-operations/50 bg-operations/10' : 'border-science/30 bg-science/5'
    }`}>
      <span className={`mt-0.5 shrink-0 text-xs font-bold ${isUrgent ? 'text-operations' : 'text-science'}`}>
        {isUrgent ? '▲' : '●'}
      </span>
      <div className="flex-1 min-w-0">
        {signals.headline && (
          <p className={`text-xs font-semibold ${isUrgent ? 'text-operations' : 'text-science'}`}>{signals.headline}</p>
        )}
        {triggerList.length > 0 && (
          <p className="text-[11px] text-lcars-muted mt-0.5">{triggerList.slice(0, 2).join(' · ')}{triggerList.length > 2 ? ` +${triggerList.length - 2} more` : ''}</p>
        )}
      </div>
      <button onClick={() => setDismissed(true)}
        className="shrink-0 text-[10px] text-lcars-muted hover:text-lcars-text transition-colors uppercase tracking-widest">
        Dismiss
      </button>
    </div>
  );
}

// ── Advisor registry (MSN-0205 — extended council) ────────────────────────────

interface CouncilAdvisor {
  id: string;
  label: string;
  subtitle: string;
  accent: string;
  group: string;
  useXoEndpoint?: boolean;
}

const COUNCIL: CouncilAdvisor[] = [
  // Command
  { id: 'xo',               label: 'XO',               subtitle: 'Executive Officer',        accent: 'text-command',    group: 'Command', useXoEndpoint: true },
  { id: 'chief_engineer',   label: 'Chief Engineer',   subtitle: 'Architecture & Engineering', accent: 'text-engineering', group: 'Command' },
  { id: 'research_officer', label: 'Research Officer', subtitle: 'Intelligence & Analysis',   accent: 'text-science',    group: 'Command' },
  // Operations
  { id: 'number_one',       label: 'Number One',       subtitle: 'Priorities & Sequencing',  accent: 'text-operations', group: 'Operations' },
  // Wellness
  { id: 'medical_officer',  label: 'Medical Officer',  subtitle: 'Capacity & Health',         accent: 'text-medical',    group: 'Wellness' },
  { id: 'recovery_officer', label: 'Recovery Officer', subtitle: 'Directive 055 Compliance',  accent: 'text-medical',    group: 'Wellness' },
  { id: 'wellness_advisor', label: 'Wellness Advisor', subtitle: 'Whole-Person Wellbeing',    accent: 'text-medical',    group: 'Wellness' },
  { id: 'recovery_coach',   label: 'Recovery Coach',   subtitle: 'Protocol Optimisation',     accent: 'text-medical',    group: 'Wellness' },
  { id: 'performance_coach',label: 'Perf. Coach',      subtitle: 'Capacity Windows',          accent: 'text-medical',    group: 'Wellness' },
  // Operational Resilience
  { id: 'or_advisor',       label: 'OR Advisor',       subtitle: 'Operational Resilience',    accent: 'text-operations', group: 'Resilience' },
  { id: 'bc_advisor',       label: 'BC Advisor',       subtitle: 'Business Continuity',       accent: 'text-operations', group: 'Resilience' },
  { id: 'crisis_advisor',   label: 'Crisis Advisor',   subtitle: 'Crisis Management',         accent: 'text-operations', group: 'Resilience' },
  { id: 'executive_risk_advisor', label: 'Risk Advisor', subtitle: 'Executive Risk',          accent: 'text-operations', group: 'Resilience' },
];

const LS_CONSULT_KEY = 'lcars-council-consult-history';

// ── Consult mode ───────────────────────────────────────────────────────────────

const QUICK_PROMPTS = [
  'What needs my decision?',
  'Protect or defer?',
  'What changed since yesterday?',
  'Challenge this assumption',
];

function ConsultMode() {
  const [activeAdvisor, setActiveAdvisor] = useState<CouncilAdvisor>(COUNCIL[0]);
  const [threads, setThreads] = useState<Record<string, Msg[]>>({});
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState('');
  const [offlineAdvisors, setOfflineAdvisors] = useState<Set<string>>(new Set());
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
      : JSON.stringify({ messages: history.map((m) => ({ role: m.role, content: m.content })), role: activeAdvisor.id, stream: true });

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
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n'); buf = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (payload === '[DONE]') break;
          try { const p = JSON.parse(payload) as { token?: string }; if (p.token) { acc += p.token; setStreamBuffer(acc); } } catch { /* skip */ }
        }
      }
      setThreads((prev) => ({ ...prev, [activeAdvisor.id]: [...(prev[activeAdvisor.id] ?? []), { id: (Date.now() + 1).toString(), role: 'assistant', content: acc || '(no response)' }] }));
      setStreamBuffer('');
    } catch (err) {
      const e = err as Error;
      if (e.message.includes('fetch') || e.message.includes('ECONNREFUSED')) {
        setOfflineAdvisors((prev) => new Set([...prev, activeAdvisor.id]));
      } else {
        setThreads((prev) => ({ ...prev, [activeAdvisor.id]: [...(prev[activeAdvisor.id] ?? []), { id: (Date.now() + 1).toString(), role: 'assistant', content: 'Error contacting advisor.', error: true }] }));
      }
    } finally { setLoading(false); setStreamBuffer(''); }
  }, [activeAdvisor, threads, loading]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } };
  const clearThread = () => { setThreads((prev) => { const next = { ...prev }; delete next[activeAdvisor.id]; return next; }); };
  const isOffline = offlineAdvisors.has(activeAdvisor.id);

  const groups = COUNCIL.reduce<Record<string, CouncilAdvisor[]>>((acc, a) => { (acc[a.group] = acc[a.group] ?? []).push(a); return acc; }, {});

  return (
    <div style={{ display: 'flex', gap: '1rem', height: '65vh' }}>
      {/* Sidebar */}
      <div className="flex flex-col gap-3 w-44 shrink-0 pt-1 overflow-y-auto">
        {Object.entries(groups).map(([group, advisors]) => (
          <div key={group}>
            <p className="text-[9px] uppercase tracking-[0.2em] text-lcars-muted mb-1 px-1">{group}</p>
            <div className="flex flex-col gap-1">
              {advisors.map((a) => (
                <button key={a.id} onClick={() => { setActiveAdvisor(a); setStreamBuffer(''); }}
                  className={['rounded-lcars border px-2.5 py-2 text-left transition-colors', activeAdvisor.id === a.id ? `border-command bg-command/10 ${a.accent}` : 'border-edge text-lcars-muted hover:border-edge/60'].join(' ')}>
                  <p className={`text-xs font-lcars uppercase tracking-wider ${activeAdvisor.id === a.id ? a.accent : ''}`}>{a.label}</p>
                  <p className="text-[9px] text-lcars-muted leading-tight mt-0.5">{a.subtitle}</p>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Thread */}
      <LCARSPanel title={`${activeAdvisor.label} — ${activeAdvisor.subtitle}`} accent="command" className="flex-1 min-w-0"
        actions={messages.length > 0 ? (
          <button onClick={clearThread} disabled={loading}
            className="rounded-lcars border border-edge px-3 py-1 text-[10px] uppercase tracking-widest text-lcars-muted hover:text-operations transition-colors disabled:opacity-40">
            Clear
          </button>
        ) : undefined}>
        {isOffline ? (
          <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
            <p className="text-lcars-muted text-sm">{activeAdvisor.label} is offline (AI model not configured).</p>
            <p className="text-lcars-text/60 text-xs max-w-sm">Use the <span className="text-command font-semibold">Board</span> tab for advisory via the intelligence runtime.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3 h-full">
            <div className="flex-1 overflow-y-auto space-y-3 pr-1">
              {messages.length === 0 && !loading && (
                <p className="text-lcars-muted text-sm text-center py-8">{activeAdvisor.label} standing by.</p>
              )}
              {messages.map((m) => {
                const isUser = m.role === 'user';
                return (
                  <div key={m.id} style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
                    <div className={['rounded-lcars border px-3.5 py-2.5 text-sm leading-relaxed', isUser ? 'border-command/40 bg-command/10 text-lcars-text' : m.error ? 'border-operations/40 bg-operations/10 text-operations' : 'border-edge bg-panel/60 text-lcars-text/90'].join(' ')} style={{ maxWidth: '90%' }}>
                      {!isUser && !m.error && <p className={`mb-1 text-[10px] uppercase tracking-[0.2em] ${activeAdvisor.accent}`}>{activeAdvisor.label}</p>}
                      {isUser ? <span className="whitespace-pre-wrap">{m.content}</span> : (
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
                    <p className={`mb-1 text-[10px] uppercase tracking-[0.2em] ${activeAdvisor.accent}`}>{activeAdvisor.label}</p>
                    <div className="prose prose-sm prose-invert max-w-none prose-p:my-1"><ReactMarkdown>{streamBuffer}</ReactMarkdown></div>
                    <span className="inline-block w-1.5 h-3.5 bg-science animate-pulse ml-0.5 align-middle" />
                  </div>
                </div>
              )}
              {loading && !streamBuffer && (
                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <div className="rounded-lcars border border-edge bg-panel/60 px-4 py-3">
                    <div style={{ display: 'flex', height: '12px', alignItems: 'center', gap: '6px' }}>
                      {[0, 1, 2].map((i) => <span key={i} className="h-1.5 w-1.5 animate-pulse rounded-full bg-science" style={{ animationDelay: `${i * 150}ms` }} />)}
                    </div>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {QUICK_PROMPTS.map((p) => (
                <button key={p} onClick={() => send(p)} disabled={loading}
                  className="rounded-lcars border border-edge px-2.5 py-1 text-[10px] uppercase tracking-wider text-lcars-muted hover:border-science hover:text-science transition-colors disabled:opacity-40">
                  {p}
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem' }}>
              <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown} rows={2}
                placeholder={`Message ${activeAdvisor.label}…`} disabled={loading}
                className="flex-1 resize-none rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-science focus:outline-none disabled:opacity-50" />
              <button onClick={() => send(input)} disabled={loading || !input.trim()}
                className="self-stretch rounded-lcars bg-science px-4 font-lcars text-sm font-bold uppercase tracking-[0.15em] text-space transition-opacity hover:opacity-80 disabled:opacity-40">
                Send
              </button>
            </div>
          </div>
        )}
      </LCARSPanel>
    </div>
  );
}

// ── Board mode ─────────────────────────────────────────────────────────────────

function BoardMode() {
  const [input, setInput] = useState('');
  const [isScenario, setIsScenario] = useState(false);
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<AdvisoryResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    setLoading(true); setSummary(null); setError(null);
    const question = isScenario ? `Scenario analysis: What would happen if ${trimmed}` : trimmed;
    try {
      const res = await fetch('/api/advisory', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'advice', question }) });
      const data = (await res.json()) as { result?: AdvisoryResult; error?: string };
      if (data.error) { setError(data.error); return; }
      setSummary(data.result ?? (data as unknown as AdvisoryResult));
    } catch (err) { setError((err as Error).message); }
    finally { setLoading(false); }
  };

  const perspectives = summary?.officer_perspectives ?? [];

  return (
    <LCARSPanel title="Advisory Board" accent="science">
      <div className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-xs text-lcars-muted uppercase tracking-wider">Mode</span>
            {(['Advisory', 'Scenario'] as const).map((m) => {
              const isActive = m === 'Scenario' ? isScenario : !isScenario;
              return (
                <button key={m} onClick={() => setIsScenario(m === 'Scenario')}
                  className={`rounded-lcars border px-3 py-1 text-[10px] uppercase tracking-widest transition-colors ${isActive ? (m === 'Scenario' ? 'border-science bg-science/10 text-science' : 'border-command bg-command/10 text-command') : 'border-edge text-lcars-muted hover:border-edge/60'}`}>
                  {m}
                </button>
              );
            })}
            {isScenario && <span className="text-[10px] text-science/70 italic">What would happen if…</span>}
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem' }}>
            <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }} rows={2}
              placeholder={isScenario ? 'What would happen if…' : 'Bring a question to the Advisory Board…'} disabled={loading}
              className="flex-1 resize-none rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-science focus:outline-none disabled:opacity-50" />
            <button onClick={submit} disabled={loading || !input.trim()}
              className="self-stretch rounded-lcars bg-science px-4 font-lcars text-sm font-bold uppercase tracking-[0.15em] text-space transition-opacity hover:opacity-80 disabled:opacity-40">
              Convene
            </button>
          </div>
        </div>

        {loading && (
          <div className="flex items-center gap-3 py-4">
            {[0, 1, 2].map((i) => <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-science" style={{ animationDelay: `${i * 150}ms` }} />)}
            <span className="text-lcars-muted text-sm">Convening Advisory Board…</span>
          </div>
        )}
        {error && (
          <div className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations">
            <p className="font-semibold mb-1">Advisory runtime offline</p>
            <p className="text-operations/80 text-xs">{error}</p>
          </div>
        )}
        {summary && !loading && (
          <div className="space-y-4">
            <AdvisoryBlock data={summary} />
            {perspectives.length > 0 && (
              <div>
                <p className="mb-2 text-[10px] uppercase tracking-[0.15em] text-lcars-muted">Officer Perspectives</p>
                <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
                  {perspectives.map((op, i) => {
                    const advisor = COUNCIL.find((a) => a.label.toLowerCase() === op.officer?.toLowerCase());
                    const accentClass = advisor?.accent ?? 'text-science';
                    const stance = op.stance ?? '';
                    const stanceColor = stance === 'supports' ? 'text-medical' : stance === 'cautions' ? 'text-operations' : 'text-lcars-muted';
                    return (
                      <div key={i} className="rounded-lcars border border-edge bg-panel/50 px-3 py-2.5 space-y-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <p className={`text-[10px] uppercase tracking-wider font-semibold ${accentClass}`}>{op.officer}</p>
                          {stance && <span className={`text-[9px] uppercase tracking-widest ${stanceColor}`}>{stance}</span>}
                        </div>
                        <p className="text-xs text-lcars-text/85 leading-relaxed">{op.recommendation}</p>
                        {op.confidence !== undefined && <p className="text-[9px] text-lcars-muted">Confidence: {op.confidence}%</p>}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
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
    setLoading(true); setError(null); setResult(null);
    try {
      const res = await fetch('/api/advisory', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'daily-brief' }) });
      const data = (await res.json()) as { result?: AdvisoryResult; error?: string };
      if (data.error) { setError(data.error); return; }
      setResult(data.result ?? (data as unknown as AdvisoryResult));
    } catch (err) { setError((err as Error).message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchBrief(); }, [fetchBrief]);

  return (
    <LCARSPanel title="Daily Brief" accent="science"
      actions={<button onClick={fetchBrief} disabled={loading} className="rounded-lcars border border-edge px-3 py-1 text-[10px] uppercase tracking-widest text-lcars-muted hover:text-science transition-colors disabled:opacity-40">Refresh</button>}>
      {loading && <div className="flex items-center gap-3 py-8">{[0,1,2].map((i) => <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-science" style={{ animationDelay: `${i*150}ms` }} />)}<span className="text-lcars-muted text-sm">Fetching brief…</span></div>}
      {error && <div className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations"><p className="font-semibold mb-1">Intelligence runtime offline</p><p className="text-operations/80 text-xs">{error}</p></div>}
      {result && !loading && <AdvisoryBlock data={result} />}
    </LCARSPanel>
  );
}

// ── Picture mode ───────────────────────────────────────────────────────────────

function PictureMode() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchPicture = useCallback(async () => {
    setLoading(true); setError(null); setResult(null);
    try {
      const res = await fetch('/api/advisory', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'captains-picture' }) });
      const data = (await res.json()) as { result?: Record<string, unknown>; error?: string };
      if (data.error) { setError(data.error); return; }
      setResult((data.result ?? data) as Record<string, unknown>);
    } catch (err) { setError((err as Error).message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchPicture(); }, [fetchPicture]);

  return (
    <LCARSPanel title="Operating Picture" accent="command"
      actions={<button onClick={fetchPicture} disabled={loading} className="rounded-lcars border border-edge px-3 py-1 text-[10px] uppercase tracking-widest text-lcars-muted hover:text-command transition-colors disabled:opacity-40">Refresh</button>}>
      {loading && <div className="flex items-center gap-3 py-8">{[0,1,2].map((i) => <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-command" style={{ animationDelay: `${i*150}ms` }} />)}<span className="text-lcars-muted text-sm">Assembling operating picture…</span></div>}
      {error && <div className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations"><p className="font-semibold mb-1">Advisory runtime offline</p><p className="text-operations/80 text-xs">{error}</p></div>}
      {result && !loading && <OperationalCard data={result} />}
    </LCARSPanel>
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
    setLoading(true); setError(null); setResult(null);
    try {
      const res = await fetch('/api/advisory', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }) });
      const data = (await res.json()) as { result?: unknown; error?: string };
      if (data.error) { setError(data.error); return; }
      setResult(data.result ?? data);
    } catch (err) { setError((err as Error).message); }
    finally { setLoading(false); }
  }, [action]);

  useEffect(() => { fetch_(); }, [fetch_]);
  const items = Array.isArray(result) ? result : result ? [result] : [];

  return (
    <div>
      {loading && <div className="flex items-center gap-3 py-6">{[0,1,2].map((i) => <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-science" style={{ animationDelay: `${i*150}ms` }} />)}</div>}
      {error && <div className="rounded-lcars border border-operations/40 bg-operations/10 px-4 py-3 text-sm text-operations"><p className="font-semibold">Intelligence runtime offline</p><p className="text-xs mt-1 text-operations/80">{error}</p></div>}
      {!loading && !error && items.length === 0 && <p className="text-lcars-muted text-sm py-6">No data available.</p>}
      <div className="space-y-2 mt-2">{items.map((item, i) => <IntelResultCard key={i} action={action} data={item} />)}</div>
      {!loading && <button onClick={fetch_} className="mt-3 rounded-lcars border border-edge px-3 py-1 text-[10px] uppercase tracking-widest text-lcars-muted hover:text-science transition-colors">Refresh</button>}
    </div>
  );
}

function IntelligenceMode() {
  const [tab, setTab] = useState<IntelTab>('awareness');
  const active = INTEL_TABS.find((t) => t.id === tab)!;
  return (
    <LCARSPanel title="Intelligence" accent="science">
      <div className="flex gap-2 mb-4">{INTEL_TABS.map((t) => <TabBtn key={t.id} label={t.label} active={tab === t.id} onClick={() => setTab(t.id)} />)}</div>
      <IntelPanel key={active.id} action={active.action} />
    </LCARSPanel>
  );
}

// ── Perspectives mode (MSN-0204) ───────────────────────────────────────────────

interface Perspective { name: string; label: string }
interface PerspectiveResponse { perspective: Perspective; content: string; response: string; loading: boolean; error: string | null }

function PerspectivesMode() {
  const [available, setAvailable] = useState<Perspective[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [input, setInput] = useState('');
  const [responses, setResponses] = useState<PerspectiveResponse[]>([]);
  const [loadingList, setLoadingList] = useState(true);

  useEffect(() => {
    fetch('/api/perspectives')
      .then((r) => r.json())
      .then((d: { perspectives?: Perspective[] }) => { setAvailable(d.perspectives ?? []); setLoadingList(false); })
      .catch(() => setLoadingList(false));
  }, []);

  const toggleSelect = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  };

  const convene = async () => {
    const trimmed = input.trim();
    if (!trimmed || selected.size === 0) return;
    const chosen = available.filter((p) => selected.has(p.name));

    // Initialise response slots
    setResponses(chosen.map((p) => ({ perspective: p, content: '', response: '', loading: true, error: null })));

    // Fetch content for each perspective then call /api/ai/chat
    await Promise.all(chosen.map(async (p, idx) => {
      try {
        const contentRes = await fetch(`/api/perspectives?name=${p.name}`);
        const contentData = (await contentRes.json()) as { content?: string; error?: string };
        if (contentData.error || !contentData.content) throw new Error(contentData.error ?? 'No content');

        const chatRes = await fetch('/api/ai/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: [{ role: 'user', content: trimmed }],
            systemPrompt: contentData.content,
            stream: false,
          }),
        });
        const chatData = (await chatRes.json()) as { content?: string; error?: string };
        if (chatData.error) throw new Error(chatData.error);

        setResponses((prev) => prev.map((r, i) => i === idx ? { ...r, response: chatData.content ?? '', loading: false } : r));
      } catch (err) {
        setResponses((prev) => prev.map((r, i) => i === idx ? { ...r, loading: false, error: (err as Error).message } : r));
      }
    }));
  };

  const hasActive = responses.length > 0;

  return (
    <LCARSPanel title="Distinguished Perspectives" accent="science">
      <div className="space-y-4">
        <div className="space-y-3">
          {loadingList ? (
            <p className="text-lcars-muted text-sm">Loading perspectives…</p>
          ) : (
            <div>
              <p className="text-[10px] uppercase tracking-[0.15em] text-lcars-muted mb-2">Select perspectives</p>
              <div className="flex flex-wrap gap-2">
                {available.map((p) => {
                  const isOn = selected.has(p.name);
                  return (
                    <button key={p.name} onClick={() => toggleSelect(p.name)}
                      className={`rounded-lcars border px-3 py-1.5 text-xs font-lcars uppercase tracking-wider transition-colors ${isOn ? 'border-science bg-science/10 text-science' : 'border-edge text-lcars-muted hover:border-edge/60'}`}>
                      {p.label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem' }}>
            <textarea value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); convene(); } }}
              rows={2} placeholder="What would these perspectives emphasise?" disabled={selected.size === 0}
              className="flex-1 resize-none rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-science focus:outline-none disabled:opacity-50" />
            <button onClick={convene} disabled={selected.size === 0 || !input.trim()}
              className="self-stretch rounded-lcars bg-science px-4 font-lcars text-sm font-bold uppercase tracking-[0.15em] text-space transition-opacity hover:opacity-80 disabled:opacity-40">
              Ask
            </button>
          </div>
          {selected.size === 0 && <p className="text-[10px] text-lcars-muted">Select at least one perspective above.</p>}
        </div>

        {hasActive && (
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
            {responses.map((r, i) => (
              <div key={i} className="rounded-lcars border border-edge bg-panel/50 px-3 py-3 space-y-2">
                <p className="text-[10px] uppercase tracking-widest text-science font-semibold">{r.perspective.label}</p>
                {r.loading && (
                  <div className="flex items-center gap-2">
                    {[0,1,2].map((j) => <span key={j} className="h-1.5 w-1.5 animate-pulse rounded-full bg-science" style={{ animationDelay: `${j*150}ms` }} />)}
                  </div>
                )}
                {r.error && <p className="text-xs text-operations">{r.error}</p>}
                {r.response && !r.loading && (
                  <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-headings:text-lcars-text prose-headings:font-lcars prose-strong:text-lcars-text prose-li:my-0.5 prose-code:text-command text-xs">
                    <ReactMarkdown>{r.response}</ReactMarkdown>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </LCARSPanel>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

const TOP_TABS: { id: TopTab; label: string }[] = [
  { id: 'consult',      label: 'Consult' },
  { id: 'board',        label: 'Board' },
  { id: 'perspectives', label: 'Perspectives' },
];

export default function AdvisoryCouncilPage() {
  const [tab, setTab] = useState<TopTab>('consult');

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <h1 className="font-lcars text-xl uppercase tracking-[0.2em] text-lcars-text">Advisory Council</h1>
        <p className="text-xs text-lcars-muted tracking-wider mt-0.5">Captain&apos;s Advisory Council — Starship Endeavour</p>
      </div>

      {/* Proactive signals banner (MSN-0206) */}
      <ProactiveSignalsBanner />

      {/* Mode tabs */}
      <div className="flex border-b border-edge overflow-x-auto mb-4">
        {TOP_TABS.map((t) => <TabBtn key={t.id} label={t.label} active={tab === t.id} onClick={() => setTab(t.id)} />)}
      </div>

      {tab === 'consult'      && <ConsultMode />}
      {tab === 'board'        && <BoardMode />}
      {tab === 'perspectives' && <PerspectivesMode />}
    </div>
  );
}
