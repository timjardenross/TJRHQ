'use client';

import { Suspense, useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import { LCARSPanel } from '@/components/LCARSPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { AI_MODELS, DEFAULT_MODEL_ID } from '@/lib/ai-models';
import type { ActionResult } from '@/lib/ai-actions';
import { describeProposalOutcome } from '@/lib/actionProposalCopy';
import { fetchRecommendations, type RecommendationPackage } from '@/lib/recommendations';
import { fetchInvestigation, type InvestigationRunResult } from '@/lib/investigate';

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
  /** MSN-0352: deterministic action-proposal outcomes attached to this
   * message, rendered from the backend's ActionResult objects - never
   * from the model's own prose, so the "only proposed, not performed"
   * distinction cannot be lost or contradicted by how the model phrased
   * its reply. */
  proposals?: ActionResult[];
}

/** MSN-0352: the one place this UI states whether an action was queued or
 * failed. Text comes from describeProposalOutcome() (lib/actionProposalCopy.ts)
 * - a plain, unit-tested function, not JSX authored ad hoc here - so
 * "never claims completion for a mere proposal" is a property that's
 * actually verified, not just a convention. */
function ProposalBlock({ proposals }: { proposals: ActionResult[] }) {
  if (!proposals.length) return null;
  return (
    <div className="mt-2 flex flex-col gap-1.5 border-l-2 border-[#243b7a]/40 pl-3">
      {proposals.map((p, i) => (
        <div key={i} className={`text-xs ${p.success ? 'text-[#61718c]' : 'text-alert-on'}`}>
          <span className="font-semibold">{describeProposalOutcome(p)}</span>
          {p.success && (
            <>
              {' '}
              <a href="/decide" className="underline hover:text-[#243b7a] font-normal">Open Decide →</a>
            </>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Evidence panel ─────────────────────────────────────────────────────────────

/** EOS Phase 2 Priority 4 (Executive Advisory Council): composes the two
 * canonical engines that previously never fed the Council - the
 * Recommendation Engine (core/coordination/recommendation_engine.py, via
 * lib/recommendations.ts) and the Investigation Engine (lib/investigate.ts)
 * - into the Board's evidence, kept structurally and visually separate from
 * officer perspectives (interpretation). Both bridges already degrade to
 * null on any failure (see their own headers), so a fetch problem here
 * just omits the panel rather than fabricating placeholder evidence; there
 * is no synthesis or re-ranking here, only direct passthrough of what each
 * engine already returned. */
function EvidencePanel({
  recommendations,
  investigation,
}: {
  recommendations: RecommendationPackage | null;
  investigation: InvestigationRunResult | null;
}) {
  const hasRecommendations = !!recommendations?.recommendations.length;
  if (!hasRecommendations && !investigation) return null;
  return (
    <div className="rounded-lcars border border-[#d9e1f0] bg-white/40 p-3 space-y-3">
      <p className="text-[10px] uppercase tracking-[0.15em] text-[#61718c]">
        Evidence — sourced directly from the canonical engines, not an officer&apos;s interpretation
      </p>
      {hasRecommendations && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-[#243b7a] mb-1">Recommendation Engine</p>
          <ul className="space-y-1">
            {recommendations!.recommendations.slice(0, 3).map((r) => (
              <li key={r.mission_id} className="text-xs text-[#18223a]/80">
                <span className="text-[#18223a]">{r.title}</span>{' '}
                <span className="text-[#61718c]">({r.mission_id})</span> — {r.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {investigation && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-[#243b7a] mb-1">
            Investigation Engine — {investigation.label}
          </p>
          <p className="text-xs text-[#18223a]/80">{investigation.triggerDescription}</p>
          {investigation.decisionOptions.length > 0 && (
            <ul className="mt-1 space-y-1">
              {investigation.decisionOptions.map((opt) => (
                <li key={opt.id} className="text-xs text-[#18223a]/70">{opt.label}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ── Advisory block ─────────────────────────────────────────────────────────────

function AdvisoryBlock({ data }: { data: AdvisoryResult }) {
  const conf = typeof data.confidence === 'object' && data.confidence ? data.confidence : null;
  return (
    <div className="space-y-3 text-sm">
      {(data.executive_summary || data.bottom_line) && (
        <div className="rounded-lcars border border-[#243b7a]/30 bg-[#243b7a]/10 px-3 py-2">
          <p className="mb-1 text-[10px] uppercase tracking-[0.15em] text-[#243b7a]">Summary</p>
          <p className="text-[#18223a] leading-relaxed">{String(data.executive_summary ?? data.bottom_line ?? '')}</p>
        </div>
      )}
      {data.recommendation && (
        <div className="rounded-lcars border border-[#243b7a]/30 bg-[#243b7a]/10 px-3 py-2">
          <p className="mb-1 text-[10px] uppercase tracking-[0.15em] text-[#243b7a]">Recommendation</p>
          <p className="text-[#18223a] leading-relaxed">{String(data.recommendation)}</p>
        </div>
      )}
      {Array.isArray(data.risks_and_challenges) && data.risks_and_challenges.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] uppercase tracking-[0.15em] text-[#243b7a]">Risks</p>
          <ul className="space-y-1">
            {data.risks_and_challenges.map((r, i) => (
              <li key={i} className="flex gap-2 text-[#18223a]/80">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[#243b7a]" />
                {String(r)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {conf && (
        <p className="text-[10px] text-[#61718c]">
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
        <p className="text-sm font-semibold text-[#243b7a] border-l-2 border-[#243b7a]/50 pl-3">{bottomLine}</p>
      )}
      {sections.map((s, i) => (
        <div key={i}>
          <p className="text-[10px] uppercase tracking-widest text-[#61718c] mb-1">{s.heading}</p>
          {s.text && <p className="text-xs text-[#18223a]/80">{s.text}</p>}
          {s.items && s.items.length > 0 && (
            <ul className="space-y-0.5">{s.items.map((item, j) => <li key={j} className="text-xs text-[#18223a]/80">· {item}</li>)}</ul>
          )}
          {s.suppressed !== undefined && s.suppressed > 0 && (
            <p className="text-[10px] text-[#61718c] mt-0.5">+{s.suppressed} suppressed</p>
          )}
        </div>
      ))}
      {note && <p className="text-[11px] text-[#61718c] italic">{note}</p>}
    </div>
  );
}

// ── Intelligence panel renderers ───────────────────────────────────────────────

function TrendPill({ label, dir }: { label: string; dir: string }) {
  const tone = dir === 'improving' ? 'text-[#243b7a] border-[#243b7a]/40 bg-[#243b7a]/10'
    : dir === 'worsening' ? 'text-[#243b7a] border-[#243b7a]/40 bg-[#243b7a]/10'
    : 'text-[#61718c] border-[#d9e1f0] bg-white/40';
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
      {narrative && <p className="text-sm text-[#18223a]/90 leading-relaxed border-l-2 border-[#243b7a]/50 pl-3">{narrative}</p>}
      {Object.keys(trends).length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-[#61718c] mb-1.5">Trends</p>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(trends).map(([k, v]) => <TrendPill key={k} label={k.replace(/_/g, ' ')} dir={String(v)} />)}
          </div>
        </div>
      )}
      {(improving.length > 0 || worsening.length > 0) && (
        <div className="grid grid-cols-2 gap-3">
          {improving.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-[#243b7a] mb-1">Improving</p>
              <ul className="space-y-0.5">{improving.map((s, i) => <li key={i} className="text-xs text-[#18223a]/80">↑ {s}</li>)}</ul>
            </div>
          )}
          {worsening.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-[#243b7a] mb-1">Needs attention</p>
              <ul className="space-y-0.5">{worsening.map((s, i) => <li key={i} className="text-xs text-[#18223a]/80">↓ {s}</li>)}</ul>
            </div>
          )}
        </div>
      )}
      {priorities.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-[#61718c] mb-1">Recovery priorities</p>
          <ul className="space-y-0.5">{priorities.map((p, i) => <li key={i} className="text-xs text-[#18223a]/80">· {p}</li>)}</ul>
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
        <p className={`text-sm font-semibold ${attnRequired ? 'text-[#243b7a]' : 'text-[#18223a]/90'}`}>
          {attnRequired ? '▲ ' : '● '}{headline}
        </p>
      )}
      {triggers.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-[#243b7a] mb-1">Triggers</p>
          <ul className="space-y-0.5">{triggers.map((t, i) => <li key={i} className="text-xs text-[#18223a]/80">· {typeof t === 'string' ? t : JSON.stringify(t)}</li>)}</ul>
        </div>
      )}
      {opportunities.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-[#243b7a] mb-1">Opportunities</p>
          <ul className="space-y-0.5">{opportunities.map((o, i) => <li key={i} className="text-xs text-[#18223a]/80">· {typeof o === 'string' ? o : JSON.stringify(o)}</li>)}</ul>
        </div>
      )}
      {typeof health.narrative === 'string' && health.narrative && (
        <p className="text-xs text-[#61718c] border-l border-[#d9e1f0] pl-2">{health.narrative}</p>
      )}
      {note && <p className="text-[11px] text-[#61718c] italic">{note}</p>}
    </div>
  );
}

function IntelResultCard({ action, data }: { action: string; data: unknown }) {
  if (!data || typeof data !== 'object') return <p className="text-sm text-[#61718c]">No data available.</p>;
  const obj = data as Record<string, unknown>;
  if (action === 'awareness') return <AwarenessCard data={obj} />;
  if (action === 'proactive') return <SignalsCard data={obj} />;
  if (action === 'wellness') return <OperationalCard data={obj} />;
  return (
    <div className="rounded-lcars border border-[#d9e1f0] bg-white/40 px-3 py-2.5 text-xs text-[#61718c] whitespace-pre-wrap">
      {JSON.stringify(data, null, 2)}
    </div>
  );
}

// ── Tab button ─────────────────────────────────────────────────────────────────

function TabBtn({ label, glyph, active, onClick }: { label: string; glyph?: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2 text-xs uppercase tracking-[0.15em] whitespace-nowrap transition-colors ${
        active
          ? 'border-b-2 border-[#243b7a] text-[#243b7a] font-semibold -mb-px'
          : 'text-[#61718c] hover:text-[#18223a]'
      }`}
    >
      {glyph ? `${glyph} ${label}` : label}
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
      isUrgent ? 'border-[#243b7a]/50 bg-[#243b7a]/10' : 'border-[#243b7a]/30 bg-[#243b7a]/5'
    }`}>
      <span className={`mt-0.5 shrink-0 text-xs font-bold ${isUrgent ? 'text-[#243b7a]' : 'text-[#243b7a]'}`}>
        {isUrgent ? '▲' : '●'}
      </span>
      <div className="flex-1 min-w-0">
        {signals.headline && (
          <p className={`text-xs font-semibold ${isUrgent ? 'text-[#243b7a]' : 'text-[#243b7a]'}`}>{signals.headline}</p>
        )}
        {triggerList.length > 0 && (
          <p className="text-[11px] text-[#61718c] mt-0.5">{triggerList.slice(0, 2).join(' · ')}{triggerList.length > 2 ? ` +${triggerList.length - 2} more` : ''}</p>
        )}
      </div>
      <button onClick={() => setDismissed(true)}
        className="shrink-0 text-[10px] text-[#61718c] hover:text-[#18223a] transition-colors uppercase tracking-widest">
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
  { id: 'xo',               label: 'XO',               subtitle: 'Executive Officer',        accent: 'text-[#243b7a]',    group: 'Command', useXoEndpoint: true },
  { id: 'chief_engineer',   label: 'Chief Engineer',   subtitle: 'Architecture & Engineering', accent: 'text-[#243b7a]', group: 'Command' },
  { id: 'research_officer', label: 'Research Officer', subtitle: 'Intelligence & Analysis',   accent: 'text-[#243b7a]',    group: 'Command' },
  // Operations
  { id: 'number_one',       label: 'Number One',       subtitle: 'Priorities & Sequencing',  accent: 'text-[#243b7a]', group: 'Operations' },
  // Wellness
  { id: 'medical_officer',  label: 'Medical Officer',  subtitle: 'Capacity & Health',         accent: 'text-[#243b7a]',    group: 'Wellness' },
  { id: 'recovery_officer', label: 'Recovery Officer', subtitle: 'Directive 055 Compliance',  accent: 'text-[#243b7a]',    group: 'Wellness' },
  { id: 'wellness_advisor', label: 'Wellness Advisor', subtitle: 'Whole-Person Wellbeing',    accent: 'text-[#243b7a]',    group: 'Wellness' },
  { id: 'recovery_coach',   label: 'Recovery Coach',   subtitle: 'Protocol Optimisation',     accent: 'text-[#243b7a]',    group: 'Wellness' },
  { id: 'performance_coach',label: 'Perf. Coach',      subtitle: 'Capacity Windows',          accent: 'text-[#243b7a]',    group: 'Wellness' },
  // Operational Resilience
  { id: 'or_advisor',       label: 'OR Advisor',       subtitle: 'Operational Resilience',    accent: 'text-[#243b7a]', group: 'Resilience' },
  { id: 'bc_advisor',       label: 'BC Advisor',       subtitle: 'Business Continuity',       accent: 'text-[#243b7a]', group: 'Resilience' },
  { id: 'crisis_advisor',   label: 'Crisis Advisor',   subtitle: 'Crisis Management',         accent: 'text-[#243b7a]', group: 'Resilience' },
  { id: 'executive_risk_advisor', label: 'Risk Advisor', subtitle: 'Executive Risk',          accent: 'text-[#243b7a]', group: 'Resilience' },

  // ── Advisory Board — Independent Strategic Council ──────────────────────────
  { id: 'strategist',            label: 'Strategist',    subtitle: 'Long-Range Strategy',   accent: 'text-[#243b7a]',     group: 'Advisory Board' },
  { id: 'challenger',            label: 'Challenger',    subtitle: "Devil's Advocate",       accent: 'text-alert-on',       group: 'Advisory Board' },
  { id: 'operator',              label: 'Operator',      subtitle: 'Execution Reality',      accent: 'text-[#243b7a]', group: 'Advisory Board' },
  { id: 'external_lens',         label: 'Ext. Lens',     subtitle: 'Market & World View',    accent: 'text-[#243b7a]',     group: 'Advisory Board' },
  { id: 'commercial_realist',    label: 'Commercial',    subtitle: 'Commercial Viability',   accent: 'text-[#243b7a]',     group: 'Advisory Board' },
  { id: 'human_systems_advisor', label: 'Human Systems', subtitle: 'People & Culture',       accent: 'text-[#243b7a]',     group: 'Advisory Board' },
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
  const [threadsLoaded, setThreadsLoaded] = useState(false);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState('');
  const [offlineAdvisors, setOfflineAdvisors] = useState<Set<string>>(new Set());
  // MSN-0335: ported from the now-retired /ai-console, the one real
  // capability it had that this canonical chat surface didn't --
  // letting the Captain pick which model handles the conversation,
  // rather than a fixed backend model per advisor. Not applicable to
  // XO-endpoint advisors (that endpoint has its own fixed backend).
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL_ID);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_CONSULT_KEY);
      if (raw) setThreads(JSON.parse(raw) as Record<string, Msg[]>);
    } catch { /* ignore */ }
    setThreadsLoaded(true);
  }, []);

  // Gated on threadsLoaded (not just present in the closure) because on mount
  // this effect and the load effect above fire in the same commit: without
  // the gate it persists the pre-load `threads` ({}) before the load's
  // setThreads has been applied, clobbering whatever was just read back from
  // localStorage. React Strict Mode's dev-only double-invoke of mount
  // effects makes this race lose every time instead of intermittently.
  useEffect(() => {
    if (!threadsLoaded) return;
    try { localStorage.setItem(LS_CONSULT_KEY, JSON.stringify(threads)); } catch { /* ignore */ }
  }, [threads, threadsLoaded]);

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
      // MSN-0352: capture the backend's deterministic action-proposal
      // outcomes alongside the streamed text - this is the code-side
      // record of what actually happened, independent of the model's prose.
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
      // Persist to Supabase (best-effort)
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

  return (
    <div className="flex flex-col lg:flex-row gap-4 lg:h-[65vh]">
      {/* Sidebar */}
      <div className="flex flex-col gap-3 w-full lg:w-44 shrink-0 pt-1 overflow-y-auto">
        {Object.entries(groups).map(([group, advisors]) => (
          <div key={group}>
            <p className="text-[9px] uppercase tracking-[0.2em] text-[#61718c] mb-1 px-1">{group}</p>
            <div className="flex flex-col gap-1">
              {advisors.map((a) => (
                <button key={a.id} onClick={() => { setActiveAdvisor(a); setStreamBuffer(''); }}
                  className={['rounded-lcars border px-2.5 py-2 text-left transition-colors', activeAdvisor.id === a.id ? `border-[#243b7a] bg-[#243b7a]/10 ${a.accent}` : 'border-[#d9e1f0] text-[#61718c] hover:border-[#d9e1f0]/60'].join(' ')}>
                  <p className={`text-xs font-lcars uppercase tracking-wider ${activeAdvisor.id === a.id ? a.accent : ''}`}>{a.label}</p>
                  <p className="text-[9px] text-[#61718c] leading-tight mt-0.5">{a.subtitle}</p>
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
            className="rounded-lcars border border-[#d9e1f0] px-3 py-1 text-[10px] uppercase tracking-widest text-[#61718c] hover:text-[#243b7a] transition-colors disabled:opacity-40">
            Clear
          </button>
        ) : undefined}>
        {isOffline ? (
          <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
            <p className="text-[#61718c] text-sm">{activeAdvisor.label} is offline (AI model not configured).</p>
            <p className="text-[#18223a]/60 text-xs max-w-sm">Use the <span className="text-[#243b7a] font-semibold">Board</span> tab for advisory via the intelligence runtime.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="overflow-y-auto space-y-3 pr-1" style={{ maxHeight: 'calc(65vh - 200px)' }}>
              {messages.length === 0 && !loading && (
                <p className="text-[#61718c] text-sm text-center py-8">{activeAdvisor.label} standing by.</p>
              )}
              {messages.map((m) => {
                const isUser = m.role === 'user';
                return (
                  <div key={m.id} style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
                    <div className={['rounded-lcars border px-3.5 py-2.5 text-sm leading-relaxed', isUser ? 'border-[#243b7a]/40 bg-[#243b7a]/10 text-[#18223a]' : m.error ? 'border-[#243b7a]/40 bg-[#243b7a]/10 text-[#243b7a]' : 'border-[#d9e1f0] bg-white/60 text-[#18223a]/90'].join(' ')} style={{ maxWidth: '90%' }}>
                      {!isUser && !m.error && <p className={`mb-1 text-[10px] uppercase tracking-[0.2em] ${activeAdvisor.accent}`}>{activeAdvisor.label}</p>}
                      {isUser ? <span className="whitespace-pre-wrap">{m.content}</span> : (
                        <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:text-[#18223a] prose-headings:font-lcars prose-strong:text-[#18223a] prose-li:my-0.5 prose-code:text-[#243b7a] prose-code:bg-[#f5f7fb]/60 prose-code:px-1 prose-code:rounded">
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
                  <div className="max-w-[90%] rounded-lcars border border-[#d9e1f0] bg-white/60 px-3.5 py-2.5 text-sm leading-relaxed text-[#18223a]/90">
                    <p className={`mb-1 text-[10px] uppercase tracking-[0.2em] ${activeAdvisor.accent}`}>{activeAdvisor.label}</p>
                    <div className="prose prose-sm max-w-none prose-p:my-1"><ReactMarkdown>{streamBuffer}</ReactMarkdown></div>
                    <span className="inline-block w-1.5 h-3.5 bg-[#243b7a] animate-pulse ml-0.5 align-middle" />
                  </div>
                </div>
              )}
              {loading && !streamBuffer && (
                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <div className="rounded-lcars border border-[#d9e1f0] bg-white/60 px-4 py-3">
                    <div style={{ display: 'flex', height: '12px', alignItems: 'center', gap: '6px' }}>
                      {[0, 1, 2].map((i) => <span key={i} className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#243b7a]" style={{ animationDelay: `${i * 150}ms` }} />)}
                    </div>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {QUICK_PROMPTS.map((p) => (
                <button key={p} onClick={() => send(p)} disabled={loading}
                  className="rounded-lcars border border-[#d9e1f0] px-2.5 py-1 text-[10px] uppercase tracking-wider text-[#61718c] hover:border-[#243b7a] hover:text-[#243b7a] transition-colors disabled:opacity-40">
                  {p}
                </button>
              ))}
            </div>
            {!activeAdvisor.useXoEndpoint && (
              <div className="flex items-center gap-2">
                <label className="text-[10px] uppercase tracking-[0.2em] text-[#61718c]">Model</label>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="rounded-lcars border border-[#d9e1f0] bg-[#f5f7fb] px-2 py-1 text-xs text-[#18223a] focus:border-[#243b7a] focus:outline-none"
                >
                  {AI_MODELS.filter((m) => m.available).map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
              </div>
            )}
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem' }}>
              <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown} rows={3}
                placeholder={`Message ${activeAdvisor.label}…`} disabled={loading}
                className="flex-1 resize-y rounded-lcars border border-[#d9e1f0] bg-[#f5f7fb] px-3 py-2 text-sm text-[#18223a] placeholder:text-[#61718c] focus:border-[#243b7a] focus:outline-none disabled:opacity-50 min-h-[72px]" />
              <button onClick={() => send(input)} disabled={loading || !input.trim()}
                className="self-stretch rounded-lcars bg-[#243b7a] px-4 font-lcars text-sm font-bold uppercase tracking-[0.15em] text-white transition-opacity hover:opacity-80 disabled:opacity-40">
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

interface BoardSession { id: string; ts: number; question: string; result: AdvisoryResult }
const LS_BOARD_LOG = 'lcars-board-log';

function BoardMode({
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

  // EOS Phase 2 Priority 4: the Recommendation Engine's current top
  // priorities are always relevant standing evidence for the Board, not
  // just on a deep link - fetched once per Board visit, best-effort.
  useEffect(() => {
    fetchRecommendations().then(setRecommendations);
  }, []);

  // A specific investigation is only fetched when arrived at via a real
  // contextual link (e.g. from /investigate's "Consult the Advisory
  // Council on this") - never fabricated, never guessed from the free-text
  // question the Captain types directly into Board.
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
      // Persist to Supabase (best-effort)
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

  return (
    <LCARSPanel title="Advisory Board" accent="science"
      actions={
        log.length > 0 ? (
          <div className="flex items-center gap-2">
            <button onClick={() => setShowLog((v) => !v)} className="rounded-lcars border border-[#d9e1f0] px-3 py-1 text-[10px] uppercase tracking-widest text-[#61718c] hover:text-[#243b7a] transition-colors">
              {showLog ? 'Hide Log' : `Log (${log.length})`}
            </button>
            <button onClick={exportLog} className="rounded-lcars border border-[#d9e1f0] px-3 py-1 text-[10px] uppercase tracking-widest text-[#61718c] hover:text-[#243b7a] transition-colors">
              Export ↓
            </button>
          </div>
        ) : undefined
      }>
      <div className="space-y-4">

        {showLog && log.length > 0 && (
          <div className="rounded-lcars border border-[#d9e1f0] bg-white/40 p-3 space-y-2 max-h-56 overflow-y-auto">
            <p className="text-[10px] uppercase tracking-[0.15em] text-[#61718c]">Session History</p>
            {log.map((s) => (
              <div key={s.id} className="flex items-start justify-between gap-2 border-b border-[#d9e1f0]/40 pb-2 last:border-0">
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-[#18223a]/80 truncate">{s.question}</p>
                  <p className="text-[10px] text-[#61718c]">{new Date(s.ts).toLocaleString()}</p>
                </div>
                <button onClick={() => { setSummary(s.result); setInput(s.question); setShowLog(false); }}
                  className="shrink-0 text-[9px] text-[#243b7a] hover:text-[#243b7a]/70 uppercase tracking-widest">View</button>
              </div>
            ))}
          </div>
        )}

        <div className="space-y-2">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-xs text-[#61718c] uppercase tracking-wider">Mode</span>
            {(['Advisory', 'Scenario'] as const).map((m) => {
              const isActive = m === 'Scenario' ? isScenario : !isScenario;
              return (
                <button key={m} onClick={() => setIsScenario(m === 'Scenario')}
                  className={`rounded-lcars border px-3 py-1 text-[10px] uppercase tracking-widest transition-colors ${isActive ? (m === 'Scenario' ? 'border-[#243b7a] bg-[#243b7a]/10 text-[#243b7a]' : 'border-[#243b7a] bg-[#243b7a]/10 text-[#243b7a]') : 'border-[#d9e1f0] text-[#61718c] hover:border-[#d9e1f0]/60'}`}>
                  {m}
                </button>
              );
            })}
            {isScenario && <span className="text-[10px] text-[#243b7a]/70 italic">What would happen if…</span>}
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem' }}>
            <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }} rows={3}
              placeholder={isScenario ? 'What would happen if…' : 'Bring a question to the Advisory Board…'} disabled={loading}
              className="flex-1 resize-y rounded-lcars border border-[#d9e1f0] bg-[#f5f7fb] px-3 py-2 text-sm text-[#18223a] placeholder:text-[#61718c] focus:border-[#243b7a] focus:outline-none disabled:opacity-50 min-h-[72px]" />
            <button onClick={submit} disabled={loading || !input.trim()}
              className="self-stretch rounded-lcars bg-[#243b7a] px-4 font-lcars text-sm font-bold uppercase tracking-[0.15em] text-white transition-opacity hover:opacity-80 disabled:opacity-40">
              Convene
            </button>
          </div>
        </div>

        <EvidencePanel recommendations={recommendations} investigation={investigation} />

        {loading && (
          <div className="flex items-center gap-3 py-4">
            {[0, 1, 2].map((i) => <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-[#243b7a]" style={{ animationDelay: `${i * 150}ms` }} />)}
            <span className="text-[#61718c] text-sm">Convening Advisory Board…</span>
            <span className="text-[10px] text-[#61718c] font-mono ml-auto">{elapsed}s</span>
          </div>
        )}
        {error && (
          <div className="rounded-lcars border border-[#243b7a]/40 bg-[#243b7a]/10 px-4 py-3 text-sm text-[#243b7a]">
            <p className="font-semibold mb-1">Advisory runtime offline</p>
            <p className="text-[#243b7a]/80 text-xs">{error}</p>
          </div>
        )}
        {summary && !loading && (
          <div className="space-y-4">
            <AdvisoryBlock data={summary} />
            {perspectives.length > 0 && (
              <div>
                <p className="mb-2 text-[10px] uppercase tracking-[0.15em] text-[#61718c]">Officer Perspectives</p>
                <div className="space-y-2">
                  {perspectives.map((op, i) => {
                    const advisor = COUNCIL.find((a) => a.label.toLowerCase() === op.officer?.toLowerCase());
                    const accentClass = advisor?.accent ?? 'text-[#243b7a]';
                    const stance = op.stance ?? '';
                    const stanceColor = stance === 'supports' ? 'text-[#243b7a]' : stance === 'cautions' ? 'text-[#243b7a]' : 'text-[#61718c]';
                    return (
                      <div key={i} className="rounded-lcars border border-[#d9e1f0] bg-white/50 px-4 py-3 space-y-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <p className={`text-[11px] uppercase tracking-wider font-semibold ${accentClass}`}>{op.officer}</p>
                          {stance && <span className={`text-[9px] uppercase tracking-widest ${stanceColor}`}>{stance}</span>}
                        </div>
                        <p className="text-sm text-[#18223a]/85 leading-relaxed">{op.recommendation}</p>
                        {op.confidence !== undefined && <p className="text-[9px] text-[#61718c]">Confidence: {op.confidence}%</p>}
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
      actions={<button onClick={fetchBrief} disabled={loading} className="rounded-lcars border border-[#d9e1f0] px-3 py-1 text-[10px] uppercase tracking-widest text-[#61718c] hover:text-[#243b7a] transition-colors disabled:opacity-40">Refresh</button>}>
      {loading && <div className="flex items-center gap-3 py-8">{[0,1,2].map((i) => <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-[#243b7a]" style={{ animationDelay: `${i*150}ms` }} />)}<span className="text-[#61718c] text-sm">Fetching brief…</span></div>}
      {error && <div className="rounded-lcars border border-[#243b7a]/40 bg-[#243b7a]/10 px-4 py-3 text-sm text-[#243b7a]"><p className="font-semibold mb-1">Intelligence runtime offline</p><p className="text-[#243b7a]/80 text-xs">{error}</p></div>}
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
      actions={<button onClick={fetchPicture} disabled={loading} className="rounded-lcars border border-[#d9e1f0] px-3 py-1 text-[10px] uppercase tracking-widest text-[#61718c] hover:text-[#243b7a] transition-colors disabled:opacity-40">Refresh</button>}>
      {loading && <div className="flex items-center gap-3 py-8">{[0,1,2].map((i) => <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-[#243b7a]" style={{ animationDelay: `${i*150}ms` }} />)}<span className="text-[#61718c] text-sm">Assembling operating picture…</span></div>}
      {error && <div className="rounded-lcars border border-[#243b7a]/40 bg-[#243b7a]/10 px-4 py-3 text-sm text-[#243b7a]"><p className="font-semibold mb-1">Advisory runtime offline</p><p className="text-[#243b7a]/80 text-xs">{error}</p></div>}
      {result && !loading && <OperationalCard data={result} />}
    </LCARSPanel>
  );
}

// ── Intelligence mode ──────────────────────────────────────────────────────────

const INTEL_TABS: { id: IntelTab; label: string; action: string; glyph: string }[] = [
  { id: 'awareness', label: 'Awareness',   action: 'awareness', glyph: '●' },
  { id: 'proactive', label: 'Signals',     action: 'proactive', glyph: '◈' },
  { id: 'wellness',  label: 'Operational', action: 'wellness',  glyph: '↗' },
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
      {loading && <div className="flex items-center gap-3 py-6">{[0,1,2].map((i) => <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-[#243b7a]" style={{ animationDelay: `${i*150}ms` }} />)}</div>}
      {error && <div className="rounded-lcars border border-[#243b7a]/40 bg-[#243b7a]/10 px-4 py-3 text-sm text-[#243b7a]"><p className="font-semibold">Intelligence runtime offline</p><p className="text-xs mt-1 text-[#243b7a]/80">{error}</p></div>}
      {!loading && !error && items.length === 0 && <p className="text-[#61718c] text-sm py-6">No data available.</p>}
      <div className="space-y-2 mt-2">{items.map((item, i) => <IntelResultCard key={i} action={action} data={item} />)}</div>
      {!loading && <button onClick={fetch_} className="mt-3 rounded-lcars border border-[#d9e1f0] px-3 py-1 text-[10px] uppercase tracking-widest text-[#61718c] hover:text-[#243b7a] transition-colors">Refresh</button>}
    </div>
  );
}

function IntelligenceMode() {
  const [tab, setTab] = useState<IntelTab>('awareness');
  const active = INTEL_TABS.find((t) => t.id === tab)!;
  return (
    <LCARSPanel title="Intelligence" accent="science">
      <div className="flex border-b border-[#d9e1f0] mb-4">{INTEL_TABS.map((t) => <TabBtn key={t.id} label={t.label} glyph={t.glyph} active={tab === t.id} onClick={() => setTab(t.id)} />)}</div>
      <IntelPanel key={active.id} action={active.action} />
    </LCARSPanel>
  );
}

// ── Perspectives mode (MSN-0204) ───────────────────────────────────────────────

interface Perspective { name: string; label: string; category: string }
interface PerspectiveResponse { perspective: Perspective; content: string; response: string; loading: boolean; error: string | null }
interface PerspectiveSession { id: string; ts: number; question: string; responses: { label: string; response: string }[] }

const CATEGORIES: { key: string; label: string }[] = [
  { key: 'politics',   label: 'Politics & Leadership' },
  { key: 'business',   label: 'Business & Innovation' },
  { key: 'strategy',   label: 'Strategy' },
  { key: 'philosophy', label: 'Philosophy & Mindfulness' },
  { key: 'resilience', label: 'Human Resilience' },
  { key: 'science',    label: 'Science & Systems' },
  { key: 'command',    label: 'Command' },
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

function useElapsed(active: boolean) {
  const [elapsed, setElapsed] = useState(0);
  const ref = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (active) { setElapsed(0); ref.current = setInterval(() => setElapsed((s) => s + 1), 1000); }
    else { if (ref.current) clearInterval(ref.current); }
    return () => { if (ref.current) clearInterval(ref.current); };
  }, [active]);
  return elapsed;
}

type SelectionMode = 'individual' | 'category' | 'all';
type ResponseMode = 'individual' | 'synthesised';

function PerspectivesMode() {
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

  // Derive the active selection based on mode
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

    // Save to log and optionally synthesise
    setResponses((current) => {
      const completed = current.filter((r) => r.response && !r.loading);
      if (completed.length > 0) {
        const sessionResponses = completed.map((r) => ({ label: r.perspective.label, response: r.response }));
        const session: PerspectiveSession = {
          id: Date.now().toString(), ts: Date.now(), question: trimmed,
          responses: sessionResponses,
        };
        setLog((prev) => { const next = [session, ...prev].slice(0, 50); try { localStorage.setItem(LS_PERSPECTIVES_LOG, JSON.stringify(next)); } catch { /**/ } return next; });
        savePerspectiveCapture(trimmed, sessionResponses);

        // Synthesise if requested and more than one response
        if (responseMode === 'synthesised' && completed.length > 1 && !overrideNames) {
          setSynthesising(true);
          fetch('/api/perspectives', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: trimmed, responses: sessionResponses }),
          })
            .then((r) => r.json())
            .then((d: { synthesis?: string }) => { setSynthesis(d.synthesis ?? ''); })
            .catch(() => { setSynthesis('Synthesis unavailable.'); })
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

  return (
    <LCARSPanel title="Distinguished Perspectives" accent="science"
      actions={
        <div className="flex items-center gap-2">
          {log.length > 0 && (
            <>
              <button onClick={() => setShowLog((v) => !v)}
                className="rounded-lcars border border-[#d9e1f0] px-3 py-1 text-[10px] uppercase tracking-widest text-[#61718c] hover:text-[#243b7a] transition-colors">
                {showLog ? 'Hide Log' : `Log (${log.length})`}
              </button>
              <button onClick={exportSession}
                className="rounded-lcars border border-[#d9e1f0] px-3 py-1 text-[10px] uppercase tracking-widest text-[#61718c] hover:text-[#243b7a] transition-colors">
                Export ↓
              </button>
            </>
          )}
        </div>
      }>
      <div className="space-y-4">

        {/* Session log */}
        {showLog && log.length > 0 && (
          <div className="rounded-lcars border border-[#d9e1f0] bg-white/40 p-3 space-y-3 max-h-64 overflow-y-auto">
            <p className="text-[10px] uppercase tracking-[0.15em] text-[#61718c]">Session History</p>
            {log.map((s) => (
              <div key={s.id} className="space-y-1 border-b border-[#d9e1f0]/40 pb-2 last:border-0">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs text-[#18223a]/80 flex-1">{s.question}</p>
                  <button onClick={() => { setInput(s.question); setShowLog(false); }}
                    className="shrink-0 text-[9px] text-[#243b7a] hover:text-[#243b7a]/70 uppercase tracking-widest">Re-ask</button>
                </div>
                <p className="text-[10px] text-[#61718c]">{new Date(s.ts).toLocaleString()} · {s.responses.map((r) => r.label).join(', ')}</p>
              </div>
            ))}
          </div>
        )}

        {loadingList ? (
          <p className="text-[#61718c] text-sm">Loading perspectives…</p>
        ) : (
          <div className="space-y-3">

            {/* Selection mode row */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] uppercase tracking-[0.15em] text-[#61718c]">Select by</span>
              {/* Category chips */}
              {CATEGORIES.map((cat) => {
                const isActive = selectionMode === 'category' && activeCategory === cat.key;
                const count = available.filter((p) => p.category === cat.key).length;
                if (count === 0) return null;
                return (
                  <button key={cat.key} onClick={() => selectCategory(cat.key)}
                    className={`rounded-lcars border px-3 py-1 text-[10px] font-lcars uppercase tracking-wider transition-colors ${isActive ? 'border-[#243b7a] bg-[#243b7a]/15 text-[#243b7a]' : 'border-[#d9e1f0]/60 text-[#61718c] hover:border-[#243b7a]/40 hover:text-[#18223a]'}`}>
                    {cat.label} <span className="opacity-60">({count})</span>
                  </button>
                );
              })}
              {/* All button */}
              <button onClick={selectAll}
                className={`rounded-lcars border px-3 py-1 text-[10px] font-lcars uppercase tracking-wider transition-colors ${selectionMode === 'all' ? 'border-[#243b7a] bg-[#243b7a]/15 text-[#243b7a]' : 'border-[#d9e1f0]/60 text-[#61718c] hover:border-[#243b7a]/40 hover:text-[#18223a]'}`}>
                All ({available.length})
              </button>
            </div>

            {/* Individual figure chips */}
            <div>
              <p className="text-[10px] uppercase tracking-[0.15em] text-[#61718c] mb-2">
                {selectionMode === 'individual' ? 'Or pick individual voices' : `Active: ${selectionCount} voice${selectionCount !== 1 ? 's' : ''}`}
              </p>
              <div className="flex flex-wrap gap-2">
                {available.map((p) => {
                  const isOn = selectionMode === 'all' || (selectionMode === 'category' && p.category === activeCategory) || selected.has(p.name);
                  return (
                    <button key={p.name} onClick={() => toggleSelect(p.name)}
                      className={`rounded-lcars border px-3 py-1.5 text-xs font-lcars uppercase tracking-wider transition-colors ${isOn ? 'border-[#243b7a] bg-[#243b7a]/10 text-[#243b7a]' : 'border-[#d9e1f0] text-[#61718c] hover:border-[#d9e1f0]/60'}`}>
                      {p.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Response mode toggle */}
            {selectionCount > 1 && (
              <div className="flex items-center gap-3">
                <span className="text-[10px] uppercase tracking-[0.15em] text-[#61718c]">Response</span>
                {(['individual', 'synthesised'] as ResponseMode[]).map((m) => (
                  <button key={m} onClick={() => setResponseMode(m)}
                    className={`rounded-lcars border px-3 py-1 text-[10px] font-lcars uppercase tracking-wider transition-colors ${responseMode === m ? 'border-[#243b7a] bg-[#243b7a]/15 text-[#243b7a]' : 'border-[#d9e1f0]/60 text-[#61718c] hover:border-[#243b7a]/40'}`}>
                    {m === 'individual' ? 'Individual voices' : 'Group synthesis'}
                  </button>
                ))}
              </div>
            )}

            {/* Input + Ask */}
            <div className="flex items-end gap-2">
              <textarea value={input} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); convene(); } }}
                rows={3} placeholder="What would these perspectives say about…?" disabled={selectionCount === 0 || anyLoading}
                className="flex-1 resize-y rounded-lcars border border-[#d9e1f0] bg-[#f5f7fb] px-3 py-2 text-sm text-[#18223a] placeholder:text-[#61718c] focus:border-[#243b7a] focus:outline-none disabled:opacity-50 min-h-[72px]" />
              <button onClick={() => convene()} disabled={selectionCount === 0 || !input.trim() || anyLoading}
                className="self-stretch rounded-lcars bg-[#243b7a] px-4 font-lcars text-sm font-bold uppercase tracking-[0.15em] text-white transition-opacity hover:opacity-80 disabled:opacity-40">
                Ask
              </button>
            </div>
            {selectionCount === 0 && !anyLoading && <p className="text-[10px] text-[#61718c]">Select voices above — by category, all, or individually.</p>}
          </div>
        )}

        {/* Loading state */}
        {(anyLoading || synthesising) && (
          <div className="flex items-center gap-3 py-2">
            {[0,1,2].map((i) => <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-[#243b7a]" style={{ animationDelay: `${i*150}ms` }} />)}
            <span className="text-[#61718c] text-sm">
              {synthesising ? 'Synthesising panel response…' : `Gathering ${totalLoading} perspective${totalLoading !== 1 ? 's' : ''}…`}
            </span>
            <span className="text-[10px] text-[#61718c] font-mono ml-auto">{elapsed}s</span>
          </div>
        )}

        {/* Group synthesis result */}
        {synthesis && !synthesising && (
          <div className="rounded-lcars border border-[#243b7a]/40 bg-[#243b7a]/5">
            <div className="px-4 py-2.5 border-b border-[#243b7a]/30">
              <p className="text-[11px] uppercase tracking-widest text-[#243b7a] font-semibold">Panel Synthesis</p>
            </div>
            <div className="px-5 py-4">
              <div className="prose prose-base max-w-none prose-p:my-2 prose-p:leading-7 prose-headings:text-[#18223a] prose-headings:font-lcars prose-headings:mt-4 prose-headings:mb-2 prose-strong:text-[#18223a] prose-li:my-1 prose-ul:my-2 prose-ol:my-2">
                <ReactMarkdown>{synthesis}</ReactMarkdown>
              </div>
            </div>
          </div>
        )}

        {/* Individual responses */}
        {hasActive && (
          <div className="space-y-4">
            {responseMode === 'synthesised' && synthesis && (
              <p className="text-[10px] uppercase tracking-[0.15em] text-[#61718c]">Individual voices</p>
            )}
            {responses.map((r, i) => (
              <div key={i} className="rounded-lcars border border-[#d9e1f0] bg-white/50">
                <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-[#d9e1f0]/50">
                  <span className="text-[11px] uppercase tracking-widest text-[#243b7a] font-semibold">{r.perspective.label}</span>
                  <div className="flex items-center gap-2">
                    {r.response && !r.loading && (
                      <button onClick={() => convene([r.perspective.name])} disabled={anyLoading || !input.trim()}
                        className="text-[9px] uppercase tracking-widest text-[#61718c] hover:text-[#243b7a] transition-colors disabled:opacity-40">
                        ↺ Regenerate
                      </button>
                    )}
                    {r.loading && (
                      <div className="flex items-center gap-1.5">
                        {[0,1,2].map((j) => <span key={j} className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#243b7a]" style={{ animationDelay: `${j*150}ms` }} />)}
                      </div>
                    )}
                  </div>
                </div>
                <div className="px-5 py-4">
                  {r.error && <p className="text-sm text-[#243b7a]">{r.error}</p>}
                  {!r.loading && !r.error && !r.response && <p className="text-sm text-[#61718c]">No response.</p>}
                  {r.response && !r.loading && (
                    <div className="prose prose-base max-w-none prose-p:my-2 prose-p:leading-7 prose-headings:text-[#18223a] prose-headings:font-lcars prose-headings:mt-4 prose-headings:mb-2 prose-strong:text-[#18223a] prose-li:my-1 prose-ul:my-2 prose-ol:my-2 prose-code:text-[#243b7a] prose-code:bg-[#f5f7fb]/60 prose-code:px-1 prose-code:rounded">
                      <ReactMarkdown>{r.response}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </LCARSPanel>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

const TOP_TABS: { id: TopTab; label: string; glyph: string }[] = [
  { id: 'consult',      label: 'Consult',      glyph: '●' },
  { id: 'board',        label: 'Board',        glyph: '◈' },
  { id: 'perspectives', label: 'Perspectives', glyph: '↗' },
];

/** EOS Phase 2 Priority 4: reads the optional deep-link params a contextual
 * entry point (e.g. /investigate's "Consult the Advisory Council on this")
 * can pass - ?tab=board opens straight to Board, ?investigationType=&
 * investigationReason= carry a real investigation's evidence in. Absent any
 * of these, behaviour is unchanged from before this mission (defaults to
 * Consult, no evidence fetched until the Captain opens Board themselves). */
function AdvisoryCouncilPageInner() {
  const params = useSearchParams();
  const investigationType = params.get('investigationType') ?? undefined;
  const investigationReason = params.get('investigationReason') ?? undefined;
  const [tab, setTab] = useState<TopTab>(
    params.get('tab') === 'board' || (investigationType && investigationReason) ? 'board' : 'consult'
  );

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <h1 className="font-lcars text-xl uppercase tracking-[0.2em] text-[#18223a]">Advisory Council</h1>
        <p className="text-xs text-[#61718c] tracking-wider mt-0.5">Captain&apos;s Advisory Council — Starship Endeavour</p>
      </div>

      {/* Proactive signals banner (MSN-0206) */}
      <ProactiveSignalsBanner />

      {/* Mode tabs */}
      <div className="flex border-b border-[#d9e1f0] overflow-x-auto mb-4">
        {TOP_TABS.map((t) => <TabBtn key={t.id} label={t.label} glyph={t.glyph} active={tab === t.id} onClick={() => setTab(t.id)} />)}
      </div>

      {tab === 'consult'      && <ConsultMode />}
      {tab === 'board'        && <BoardMode investigationType={investigationType} investigationReason={investigationReason} />}
      {tab === 'perspectives' && <PerspectivesMode />}
    </div>
  );
}

export default function AdvisoryCouncilPage() {
  return (
    <Suspense fallback={null}>
      <AdvisoryCouncilPageInner />
    </Suspense>
  );
}
