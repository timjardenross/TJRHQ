'use client';

import { useState, type ReactNode } from 'react';

/**
 * Advisor Hub — USS-TJR-MSN-0092 / MSN-0093 WP6.
 *
 * Unified advisory experience over the shared advisory runtime (core/advisory)
 * via /api/advisory:
 *   - Ask Advisors        → multi-officer, evidence-based recommendation
 *   - Challenge Decision  → red-team review surfaced
 *   - Historical Evidence → evidence + related prior decisions
 *   - Review Lessons      → prior lessons for the topic
 *   - Metrics             → advisory utilisation, success rates, top advisors
 *   - Outcome capture     → close the loop so the system learns
 *
 * Advisory only — Captain TJR decides. No autonomous action.
 */

type Action = 'advice' | 'challenge' | 'lessons' | 'evidence';

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
  question: string;
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

interface LessonsResult {
  query: string;
  narrative: string;
  lessons: LessonRef[];
  similar_missions: { mission_id: string; title: string; outcome_score?: number }[];
}
interface EvidenceResult {
  question: string;
  narrative: string;
  evidence: EvidenceItem[];
  related_decisions: RelatedDecision[];
  lessons: LessonRef[];
}
interface MetricsResult {
  totals: Record<string, number>;
  recommendation_success_rate?: number | null;
  confidence_distribution: Record<string, number>;
  advisor_utilisation: Record<string, number>;
  dashboard: {
    top_advisors: { officer: string; accuracy: number; samples: number }[];
    most_valuable_lessons: { lesson_id: string; uses: number; success_rate?: number | null; signal: string }[];
    historical_effectiveness?: number | null;
  };
}

const ACTIONS: { key: Action; label: string }[] = [
  { key: 'advice', label: 'Ask Advisors' },
  { key: 'challenge', label: 'Challenge Decision' },
  { key: 'evidence', label: 'Historical Evidence' },
  { key: 'lessons', label: 'Review Lessons' },
];

export default function AdvisoryPage() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [advice, setAdvice] = useState<AdvisoryResult | null>(null);
  const [lessons, setLessons] = useState<LessonsResult | null>(null);
  const [evidence, setEvidence] = useState<EvidenceResult | null>(null);
  const [metrics, setMetrics] = useState<MetricsResult | null>(null);
  const [outcomeMsg, setOutcomeMsg] = useState<string | null>(null);

  function clearResults() {
    setError(null);
    setAdvice(null);
    setLessons(null);
    setEvidence(null);
    setMetrics(null);
    setOutcomeMsg(null);
  }

  async function post(body: Record<string, unknown>) {
    const res = await fetch('/api/advisory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error ?? 'Advisory runtime error.');
    return data.result;
  }

  async function run(act: Action) {
    if (!question.trim()) {
      setError('Enter a question or topic first.');
      return;
    }
    setLoading(true);
    clearResults();
    try {
      const result = await post({ action: act, question: question.trim() });
      if (act === 'lessons') setLessons(result as LessonsResult);
      else if (act === 'evidence') setEvidence(result as EvidenceResult);
      else setAdvice(result as AdvisoryResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed.');
    } finally {
      setLoading(false);
    }
  }

  async function showMetrics() {
    setLoading(true);
    clearResults();
    try {
      setMetrics((await post({ action: 'metrics' })) as MetricsResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed.');
    } finally {
      setLoading(false);
    }
  }

  async function recordOutcome(outcome: string) {
    if (!advice?.advisory_id) return;
    setOutcomeMsg('Recording…');
    try {
      const result = (await post({ action: 'outcome', advisoryId: advice.advisory_id, outcome })) as {
        message?: string;
      };
      setOutcomeMsg(result.message ?? 'Recorded.');
    } catch (e) {
      setOutcomeMsg(e instanceof Error ? e.message : 'Failed to record outcome.');
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5 p-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold uppercase tracking-wider text-lcars-text">Advisor Hub</h1>
          <p className="text-sm text-lcars-muted">
            Multi-officer, evidence-based advisory that learns from outcomes. Advisory only — you decide.
          </p>
        </div>
        <button
          type="button"
          onClick={showMetrics}
          disabled={loading}
          className="shrink-0 rounded-lcars border border-edge bg-panel/50 px-3 py-2 text-xs font-semibold uppercase tracking-wider text-lcars-muted hover:border-lcars-muted disabled:opacity-50"
        >
          Metrics
        </button>
      </header>

      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="e.g. Should we prioritise the portal or the Telegram bot next?"
        rows={3}
        className="w-full rounded-lcars border border-edge bg-space/40 p-3 text-sm text-lcars-text focus:border-lcars-muted focus:outline-none"
      />

      <div className="flex flex-wrap gap-2">
        {ACTIONS.map((a) => (
          <button
            key={a.key}
            type="button"
            disabled={loading}
            onClick={() => run(a.key)}
            className="rounded-lcars border border-edge bg-panel/50 px-4 py-2 text-sm font-semibold uppercase tracking-wider text-lcars-text transition-colors hover:border-lcars-muted disabled:opacity-50"
          >
            {a.label}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-lcars-muted">Consulting officers…</p>}
      {error && (
        <p className="rounded-lcars border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">{error}</p>
      )}

      {advice && (
        <>
          <AdviceView data={advice} />
          {advice.advisory_id && (
            <Section title="Close the Loop">
              <p className="mb-2 text-xs text-lcars-muted">
                Record the outcome so advisors learn (ref {advice.advisory_id}):
              </p>
              <div className="flex gap-2">
                {['success', 'partial', 'failure'].map((o) => (
                  <button
                    key={o}
                    type="button"
                    onClick={() => recordOutcome(o)}
                    className="rounded-lcars border border-edge bg-panel/50 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-lcars-text hover:border-lcars-muted"
                  >
                    {o}
                  </button>
                ))}
              </div>
              {outcomeMsg && <p className="mt-2 text-xs text-lcars-muted">{outcomeMsg}</p>}
            </Section>
          )}
        </>
      )}
      {lessons && <LessonsView data={lessons} />}
      {evidence && <EvidenceView data={evidence} />}
      {metrics && <MetricsView data={metrics} />}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lcars border border-edge bg-panel/40 p-4">
      <h2 className="mb-2 text-xs font-bold uppercase tracking-widest text-lcars-muted">{title}</h2>
      <div className="text-sm text-lcars-text">{children}</div>
    </section>
  );
}

function AdviceView({ data }: { data: AdvisoryResult }) {
  return (
    <div className="flex flex-col gap-3">
      {data.decision_mode && (
        <p className="text-xs uppercase tracking-widest text-lcars-muted">
          Mode: {data.decision_mode}
          {data.degraded ? ' · degraded (live retrieval/LLM unavailable)' : ''}
        </p>
      )}

      <Section title="1. Executive Summary">{data.executive_summary || '—'}</Section>
      <Section title="2. Recommendation">
        <p className="whitespace-pre-wrap">{data.recommendation || '—'}</p>
      </Section>

      <Section title="3. Historical Evidence">
        {data.historical_evidence?.length ? (
          <ul className="list-disc pl-5">
            {data.historical_evidence.map((e, i) => (
              <li key={i}>
                <strong>{e.reference}</strong>
                {e.outcome_score != null ? ` (${Math.round(e.outcome_score * 100)}%)` : ''} — {e.detail}
              </li>
            ))}
          </ul>
        ) : (
          'No historical evidence matched.'
        )}
        {data.related_decisions?.length ? (
          <div className="mt-2">
            <p className="font-semibold">Related decisions:</p>
            <ul className="list-disc pl-5">
              {data.related_decisions.map((d, i) => (
                <li key={i}>
                  <code>{d.decision_id}</code>
                  {d.outcome ? ` [${d.outcome}]` : ''} — {d.question}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Section>

      <Section title="4. Related Lessons">
        {data.related_lessons?.length ? (
          <ul className="list-disc pl-5">
            {data.related_lessons.map((l) => (
              <li key={l.lesson_id}>
                <strong>{l.lesson_id}: {l.title}</strong>
                {l.guidance ? ` — ${l.guidance}` : ''}
              </li>
            ))}
          </ul>
        ) : (
          'No prior lessons matched.'
        )}
      </Section>

      <Section title="5. Risks and Challenges">
        {data.risks_and_challenges?.length ? (
          <ul className="list-disc pl-5">
            {data.risks_and_challenges.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        ) : (
          'No specific risks identified.'
        )}
        {data.disagreement && (
          <p className="mt-2">
            <strong>Disagreement surfaced:</strong> {data.disagreement}
          </p>
        )}
      </Section>

      <Section title="6. Confidence Level">
        <p>
          <strong>{data.confidence?.band}</strong>{' '}
          ({Math.round((data.confidence?.value ?? 0) * 100)}%)
          {data.confidence?.basis ? ` — ${data.confidence.basis}` : ''}
        </p>
        {data.learning_note && <p className="mt-1 text-xs italic text-lcars-muted">{data.learning_note}</p>}
        {data.escalation_required && (
          <p className="mt-1 text-amber-300">⚠ Escalation recommended — Captain decision advised.</p>
        )}
      </Section>

      <Section title="7. Officer Perspectives">
        {data.officer_perspectives?.length ? (
          <ul className="list-disc pl-5">
            {data.officer_perspectives.map((o, i) => (
              <li key={i}>
                <strong>{o.officer}</strong> ({o.confidence}%)
                {o.stance ? ` · ${o.stance}` : ''}: {o.recommendation}
              </li>
            ))}
          </ul>
        ) : (
          'Single-officer advisory (no panel).'
        )}
      </Section>

      {data.advisory_note && <p className="text-xs italic text-lcars-muted">{data.advisory_note}</p>}
    </div>
  );
}

function LessonsView({ data }: { data: LessonsResult }) {
  return (
    <div className="flex flex-col gap-3">
      <Section title="Lessons">{data.narrative}</Section>
      {data.lessons?.length ? (
        <Section title="Relevant Lessons">
          <ul className="list-disc pl-5">
            {data.lessons.map((l) => (
              <li key={l.lesson_id}>
                <strong>{l.lesson_id}: {l.title}</strong>
                {l.guidance ? ` — ${l.guidance}` : ''}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {data.similar_missions?.length ? (
        <Section title="Similar Prior Missions">
          <ul className="list-disc pl-5">
            {data.similar_missions.map((s) => (
              <li key={s.mission_id}>
                <code>{s.mission_id}</code>
                {s.outcome_score != null ? ` (${Math.round(s.outcome_score * 100)}%)` : ''} — {s.title}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </div>
  );
}

function EvidenceView({ data }: { data: EvidenceResult }) {
  return (
    <div className="flex flex-col gap-3">
      <Section title="Historical Evidence">{data.narrative}</Section>
      {data.related_decisions?.length ? (
        <Section title="Related Prior Decisions">
          <ul className="list-disc pl-5">
            {data.related_decisions.map((d, i) => (
              <li key={i}>
                <code>{d.decision_id}</code>
                {d.outcome ? ` [${d.outcome}]` : ''} — {d.question}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {data.lessons?.length ? (
        <Section title="Related Lessons">
          <ul className="list-disc pl-5">
            {data.lessons.map((l) => (
              <li key={l.lesson_id}>
                <strong>{l.lesson_id}: {l.title}</strong>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </div>
  );
}

function MetricsView({ data }: { data: MetricsResult }) {
  const sr = data.recommendation_success_rate;
  return (
    <div className="flex flex-col gap-3">
      <Section title="Advisory Metrics">
        <ul className="list-disc pl-5">
          <li>Advisory requests: {data.totals.advisory_requests ?? 0}</li>
          <li>Challenge requests: {data.totals.challenge_requests ?? 0}</li>
          <li>Outcomes recorded: {data.totals.outcomes_recorded ?? 0}</li>
          <li>Recommendation success rate: {sr != null ? `${Math.round(sr * 100)}%` : '—'}</li>
        </ul>
      </Section>
      <Section title="Top Advisors">
        {data.dashboard.top_advisors?.length ? (
          <ul className="list-disc pl-5">
            {data.dashboard.top_advisors.map((r) => (
              <li key={r.officer}>
                {r.officer}: {Math.round(r.accuracy * 100)}% (n={r.samples})
              </li>
            ))}
          </ul>
        ) : (
          'No outcome data yet.'
        )}
      </Section>
      <Section title="Most Valuable Lessons">
        {data.dashboard.most_valuable_lessons?.length ? (
          <ul className="list-disc pl-5">
            {data.dashboard.most_valuable_lessons.map((l) => (
              <li key={l.lesson_id}>
                {l.lesson_id} — used {l.uses}×
                {l.success_rate != null ? `, ${Math.round(l.success_rate * 100)}% success` : ''} ({l.signal})
              </li>
            ))}
          </ul>
        ) : (
          'No lessons surfaced yet.'
        )}
      </Section>
    </div>
  );
}
