'use client';

import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { LCARSPanel } from '@/components/LCARSPanel';

// ── Types ──────────────────────────────────────────────────────────────────────

interface OfficerPerspective {
  officer: string;
  recommendation: string;
  confidence: number;
  stance?: string;
}
interface EvidenceItem { reference: string; detail: string; outcome_score?: number | null }
interface LessonRef { lesson_id: string; title: string; guidance?: string }
interface RelatedDecision { decision_id: string; question: string; outcome?: string }
interface Confidence { value: number; band: string; basis?: string }

interface AdvisoryResult {
  question?: string;
  executive_summary?: string;
  recommendation?: string;
  historical_evidence?: EvidenceItem[];
  related_lessons?: LessonRef[];
  risks_and_challenges?: string[];
  confidence?: Confidence;
  officer_perspectives?: OfficerPerspective[];
  related_decisions?: RelatedDecision[];
  decision_mode?: string;
  reviewer?: string | null;
  escalation_required?: boolean;
  disagreement?: string;
  advisory_note?: string;
  advisory_id?: string;
  learning_note?: string;
  degraded?: boolean;
}

interface Msg {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  structured?: AdvisoryResult;
  error?: boolean;
}

// ── Staff roster config ────────────────────────────────────────────────────────

interface StaffMember {
  id: string;
  name: string;
  role: string;
  accent: string;
  description: string;
  apiMode: 'xo' | 'advisory' | 'staff-briefing';
  officer_id?: string;
}

const STAFF: StaffMember[] = [
  {
    id: 'xo',
    name: 'XO',
    role: 'Chief of Staff',
    accent: 'science',
    description: 'Operational command. Turns intent into the next action.',
    apiMode: 'xo',
  },
  {
    id: 'cmo',
    name: 'CMO',
    role: 'Medical Officer',
    accent: 'medical',
    description: 'Health intelligence, recovery, and capacity advice.',
    apiMode: 'advisory',
    officer_id: 'cmo',
  },
  {
    id: 'cto',
    name: 'CTO',
    role: 'Technology Officer',
    accent: 'engineering',
    description: 'Engineering governance, architecture decisions, risk.',
    apiMode: 'advisory',
    officer_id: 'cto',
  },
  {
    id: 'cdo',
    name: 'CDO',
    role: 'Data Officer',
    accent: 'command',
    description: 'Data quality, intelligence depth, analytics decisions.',
    apiMode: 'advisory',
    officer_id: 'cdo',
  },
  {
    id: 'strategic',
    name: 'Strategic Advisor',
    role: 'Strategic Planning',
    accent: 'operations',
    description: 'Long-range thinking, priorities, mission sequencing.',
    apiMode: 'advisory',
    officer_id: 'strategic',
  },
  {
    id: 'staff-briefing',
    name: 'Staff Briefing',
    role: 'All Officers',
    accent: 'command',
    description: 'Full panel convenes. All perspectives synthesised.',
    apiMode: 'staff-briefing',
  },
];

const QUICK_PROMPTS = [
  'What needs my decision?',
  'Protect or defer?',
  'What\'s the risk here?',
  'Synthesise all perspectives',
];

const MAX_MESSAGES = 20;

function newId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

const ACCENT_TEXT: Record<string, string> = {
  science: 'text-science',
  medical: 'text-medical',
  engineering: 'text-engineering',
  command: 'text-command',
  operations: 'text-operations',
};

const ACCENT_BORDER: Record<string, string> = {
  science: 'border-science/50',
  medical: 'border-medical/50',
  engineering: 'border-engineering/50',
  command: 'border-command/50',
  operations: 'border-operations/50',
};

const ACCENT_BG: Record<string, string> = {
  science: 'bg-science/10',
  medical: 'bg-medical/10',
  engineering: 'bg-engineering/10',
  command: 'bg-command/10',
  operations: 'bg-operations/10',
};

// ── Advisory structured renderer ───────────────────────────────────────────────

function AdvisoryBlock({ data }: { data: AdvisoryResult }) {
  return (
    <div className="flex flex-col gap-2 mt-2">
      {data.decision_mode && (
        <p className="text-[10px] uppercase tracking-widest text-lcars-muted">
          Mode: {data.decision_mode}{data.degraded ? ' · degraded' : ''}
        </p>
      )}
      {data.executive_summary && (
        <div className="rounded-lcars border border-science/30 bg-science/5 px-3 py-2">
          <p className="text-[10px] uppercase tracking-widest text-science mb-1">Executive Summary</p>
          <p className="text-sm text-lcars-text leading-relaxed">{data.executive_summary}</p>
        </div>
      )}
      {data.recommendation && (
        <div className="rounded-lcars border border-edge bg-panel/40 px-3 py-2">
          <p className="text-[10px] uppercase tracking-widest text-lcars-muted mb-1">Recommendation</p>
          <p className="text-sm text-lcars-text whitespace-pre-wrap leading-relaxed">{data.recommendation}</p>
        </div>
      )}
      {data.officer_perspectives && data.officer_perspectives.length > 0 && (
        <div className="rounded-lcars border border-edge bg-panel/40 px-3 py-2">
          <p className="text-[10px] uppercase tracking-widest text-lcars-muted mb-2">Officer Perspectives</p>
          <div className="flex flex-col gap-1.5">
            {data.officer_perspectives.map((p, i) => (
              <div key={i} className="flex flex-col gap-0.5">
                <p className="text-[10px] font-bold uppercase tracking-wider text-command">
                  {p.officer} · {p.confidence}%{p.stance ? ` · ${p.stance}` : ''}
                </p>
                <p className="text-xs text-lcars-text/90">{p.recommendation}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      {data.risks_and_challenges && data.risks_and_challenges.length > 0 && (
        <div className="rounded-lcars border border-operations/30 bg-operations/5 px-3 py-2">
          <p className="text-[10px] uppercase tracking-widest text-operations mb-1">Risks</p>
          <ul className="list-disc pl-4 text-xs text-lcars-text/90 space-y-0.5">
            {data.risks_and_challenges.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}
      {data.confidence && (
        <p className="text-xs text-lcars-muted">
          Confidence: <span className="text-lcars-text font-semibold">{data.confidence.band}</span>
          {' '}({Math.round((data.confidence.value ?? 0) * 100)}%)
          {data.confidence.basis ? ` — ${data.confidence.basis}` : ''}
        </p>
      )}
      {data.escalation_required && (
        <p className="text-xs text-operations">Escalation recommended — Captain decision advised.</p>
      )}
      {data.advisory_note && (
        <p className="text-xs italic text-lcars-muted">{data.advisory_note}</p>
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function ExecutiveStaffPage() {
  const [selectedId, setSelectedId] = useState<string>('xo');
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const officer = STAFF.find((s) => s.id === selectedId) ?? STAFF[0];

  // Clear messages when switching officer
  function selectOfficer(id: string) {
    if (id !== selectedId) {
      setSelectedId(id);
      setMessages([]);
      setStreamBuffer('');
    }
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, streamBuffer]);

  async function send(text: string) {
    const body = text.trim();
    if (!body || loading) return;

    const userMsg: Msg = { id: newId(), role: 'user', content: body };
    const nextMessages = [...messages, userMsg].slice(-MAX_MESSAGES);
    setMessages(nextMessages);
    setInput('');
    setLoading(true);

    try {
      if (officer.apiMode === 'xo') {
        // XO streaming API
        const history = nextMessages.map(({ role, content }) => ({ role, content }));
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
            } catch { /* ignore parse errors */ }
          }
        }

        setMessages((prev) => [
          ...prev.slice(0, -0),
          { id: newId(), role: 'assistant' as const, content: accumulated || '(no reply)' },
        ].slice(-MAX_MESSAGES));
      } else {
        // Advisory API (both single-officer and staff-briefing)
        const payload: Record<string, unknown> = {
          action: 'advice',
          question: body,
        };
        if (officer.apiMode === 'advisory' && officer.officer_id) {
          payload.officer_id = officer.officer_id;
        }

        const res = await fetch('/api/advisory', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        const data = await res.json();
        if (!res.ok) {
          setMessages((prev) => [
            ...prev,
            { id: newId(), role: 'assistant', content: data.error ?? 'Advisory unavailable.', error: true },
          ]);
          return;
        }

        const result: AdvisoryResult = data.result ?? data;
        const summary = result.executive_summary ?? result.recommendation ?? '(no response)';
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: 'assistant' as const,
            content: summary,
            structured: result,
          },
        ].slice(-MAX_MESSAGES));
      }
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: 'assistant', content: `Could not reach ${officer.name}. Check connectivity.`, error: true },
      ]);
    } finally {
      setLoading(false);
      setStreamBuffer('');
      inputRef.current?.focus();
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  const accentText = ACCENT_TEXT[officer.accent] ?? 'text-science';
  const accentBorder = ACCENT_BORDER[officer.accent] ?? 'border-science/50';
  const accentBg = ACCENT_BG[officer.accent] ?? 'bg-science/10';

  return (
    <div style={{ display: 'flex', height: 'calc(100dvh - 8rem)', gap: '0.75rem', overflow: 'hidden' }}>

      {/* ── LEFT SIDEBAR ── */}
      <div
        style={{ width: '180px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem', overflowY: 'auto' }}
      >
        <LCARSPanel title="Staff" accent="operations" eyebrow="Executive">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {STAFF.map((s) => {
              const isSelected = s.id === selectedId;
              const sBorder = ACCENT_BORDER[s.accent] ?? 'border-edge';
              const sBg = ACCENT_BG[s.accent] ?? 'bg-panel/40';
              const sText = ACCENT_TEXT[s.accent] ?? 'text-lcars-text';
              return (
                <button
                  key={s.id}
                  onClick={() => selectOfficer(s.id)}
                  className={[
                    'w-full text-left rounded-lcars border px-2.5 py-2 transition-colors',
                    isSelected
                      ? `${sBorder} ${sBg} ${sText}`
                      : 'border-edge bg-space/40 text-lcars-muted hover:border-edge hover:text-lcars-text',
                  ].join(' ')}
                >
                  <p className={`text-xs font-bold font-lcars ${isSelected ? sText : ''}`}>{s.name}</p>
                  <p className="text-[10px] leading-tight mt-0.5 opacity-80">{s.role}</p>
                </button>
              );
            })}
          </div>
        </LCARSPanel>

        {/* Quick prompts */}
        <LCARSPanel title="Quick Prompts" accent="operations">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {QUICK_PROMPTS.map((q) => (
              <button
                key={q}
                onClick={() => send(q)}
                disabled={loading}
                className="w-full text-left rounded-lcars border border-operations/30 bg-operations/5 px-2.5 py-1.5 text-[11px] text-operations hover:bg-operations/15 disabled:opacity-40 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </LCARSPanel>
      </div>

      {/* ── MAIN PANEL ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem', minWidth: 0 }}>
        <LCARSPanel
          title={`${officer.name} — ${officer.role}`}
          accent="science"
          eyebrow="Executive Staff Console"
        >
          {/* Officer banner */}
          <div className={`rounded-lcars border ${accentBorder} ${accentBg} px-3 py-2 mb-3`}>
            <p className={`text-[10px] uppercase tracking-widest ${accentText} font-bold`}>
              {officer.name} · {officer.role}
            </p>
            <p className="text-xs text-lcars-muted mt-0.5">{officer.description}</p>
          </div>

          {/* Message history */}
          <div
            style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.625rem', minHeight: 0, height: 'calc(100dvh - 20rem)' }}
            className="rounded-lcars border border-edge bg-space/60 p-3 mb-3"
          >
            {messages.length === 0 && !loading && (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <p className="text-xs text-lcars-muted text-center">
                  Consulting {officer.name}. Ask a question or use a quick prompt.
                </p>
              </div>
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
                      <p className={`mb-1 text-[10px] uppercase tracking-[0.2em] ${accentText}`}>
                        {officer.name}
                      </p>
                    )}
                    {isUser ? (
                      <span className="whitespace-pre-wrap">{m.content}</span>
                    ) : m.structured ? (
                      <AdvisoryBlock data={m.structured} />
                    ) : (
                      <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-headings:text-lcars-text prose-headings:font-lcars prose-strong:text-lcars-text prose-li:my-0.5 prose-code:text-command prose-code:bg-space/60 prose-code:px-1 prose-code:rounded">
                        <ReactMarkdown>{m.content}</ReactMarkdown>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Streaming buffer (XO only) */}
            {loading && streamBuffer && (
              <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                <div className="max-w-[90%] rounded-lcars border border-edge bg-panel/60 px-3.5 py-2.5 text-sm leading-relaxed text-lcars-text/90">
                  <p className={`mb-1 text-[10px] uppercase tracking-[0.2em] ${accentText}`}>{officer.name}</p>
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
                      <span
                        key={i}
                        className="h-1.5 w-1.5 animate-pulse rounded-full bg-science"
                        style={{ animationDelay: `${i * 150}ms` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem' }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={2}
              placeholder={`Message ${officer.name}…`}
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
            {messages.length > 0 && (
              <button
                onClick={() => setMessages([])}
                disabled={loading}
                className="self-stretch rounded-lcars border border-edge px-3 text-[10px] uppercase tracking-widest text-lcars-muted hover:text-operations transition-colors disabled:opacity-40"
              >
                Clear
              </button>
            )}
          </div>
        </LCARSPanel>
      </div>
    </div>
  );
}
