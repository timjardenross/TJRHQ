'use client';

import { useState, type ReactNode } from 'react';

/**
 * Advisors — USS-TJR-MSN-0092 WP5.
 *
 * Surfaces the shared advisory runtime (core/advisory) in the portal via
 * /api/advisory. Three actions, one engine:
 *   - Ask Advisors      → multi-officer, evidence-based recommendation
 *   - Challenge Decision → red-team review surfaced
 *   - Review Lessons     → prior lessons for the topic
 *
 * Advisory only — Captain TJR decides. No autonomous action.
 */

type Action = 'advice' | 'challenge' | 'lessons';

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
  degraded?: boolean;
}

interface LessonsResult {
  query: string;
  narrative: string;
  lessons: LessonRef[];
  similar_missions: { mission_id: string; title: string; outcome_score?: number }[];
}

const ACTIONS: { key: Action; label: string }[] = [
  { key: 'advice', label: 'Ask Advisors' },
  { key: 'challenge', label: 'Challenge Decision' },
  { key: 'lessons', label: 'Review Lessons' },
];

export default function AdvisoryPage() {
  const [question, setQuestion] = useState('');
  const [action, setAction] = useState<Action>('advice');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [advice, setAdvice] = useState<AdvisoryResult | null>(null);
  const [lessons, setLessons] = useState<LessonsResult | null>(null);

  async function run(act: Action) {
    if (!question.trim()) {
      setError('Enter a question or topic first.');
      return;
    }
    setAction(act);
    setLoading(true);
    setError(null);
    setAdvice(null);
    setLessons(null);
    try {
      const res = await fetch('/api/advisory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: act, question: question.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? 'Advisory runtime error.');
        return;
      }
      if (act === 'lessons') setLessons(data.result as LessonsResult);
      else setAdvice(data.result as AdvisoryResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5 p-4">
      <header>
        <h1 className="text-xl font-semibold uppercase tracking-wider text-lcars-text">Advisors</h1>
        <p className="text-sm text-lcars-muted">
          Multi-officer, evidence-based advisory. Advisory only — you decide.
        </p>
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
        <p className="rounded-lcars border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </p>
      )}

      {advice && <AdviceView data={advice} />}
      {lessons && <LessonsView data={lessons} />}
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
