'use client';

import { useEffect, useState, type ReactNode } from 'react';

/**
 * Intelligence Centre — USS-TJR-MSN-0097.
 *
 * Makes advisory intelligence visible, understandable and actionable. Four
 * views over the existing advisory runtime (via /api/advisory):
 *   - Dashboard   (recent advice, confidence, advisor participation)
 *   - Performance (accuracy, calibration, advisor ranking)
 *   - Timeline    (what changed, recent events)
 *   - Operational (proactive scan: signals, triggers, opportunities, health)
 *
 * Discoverability only — no new intelligence, no officers, no autonomy.
 */

type Tab = 'briefing' | 'dashboard' | 'performance' | 'timeline' | 'operational' | 'trust';

const TABS: { key: Tab; label: string; action: string }[] = [
  { key: 'briefing', label: 'Briefing', action: 'daily-brief' },
  { key: 'dashboard', label: 'Dashboard', action: 'metrics' },
  { key: 'performance', label: 'Performance', action: 'calibration' },
  { key: 'timeline', label: 'Timeline', action: 'timeline' },
  { key: 'operational', label: 'Operational', action: 'proactive' },
  { key: 'trust', label: 'Trust', action: 'data-quality' },
];

async function fetchAction(action: string): Promise<unknown> {
  const res = await fetch('/api/advisory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error ?? 'Intelligence runtime error.');
  return data.result;
}

export default function IntelligencePage() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const action = TABS.find((t) => t.key === tab)!.action;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    fetchAction(action)
      .then((r) => !cancelled && setData(r as Record<string, unknown>))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : 'Failed.'))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [tab]);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 p-4">
      <header>
        <h1 className="text-xl font-semibold uppercase tracking-wider text-lcars-text">
          Intelligence Centre
        </h1>
        <p className="text-sm text-lcars-muted">
          Advisory intelligence — visible, measurable, understandable. Informational only.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            aria-pressed={tab === t.key}
            className={[
              'rounded-lcars border px-4 py-2 text-sm font-semibold uppercase tracking-wider transition-colors',
              tab === t.key
                ? 'border-lcars-muted bg-panel/70 text-lcars-text'
                : 'border-edge bg-panel/40 text-lcars-muted hover:border-lcars-muted',
            ].join(' ')}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-lcars-muted">Loading…</p>}
      {error && (
        <p className="rounded-lcars border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">{error}</p>
      )}

      {!loading && data && tab === 'briefing' && <Briefing d={data} />}
      {!loading && data && tab === 'dashboard' && <Dashboard d={data} />}
      {!loading && data && tab === 'performance' && <Performance d={data} />}
      {!loading && data && tab === 'timeline' && <Timeline d={data} />}
      {!loading && data && tab === 'operational' && <Operational d={data} />}
      {!loading && data && tab === 'trust' && <Trust d={data} />}
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lcars border border-edge bg-panel/40 p-4">
      <h2 className="mb-2 text-xs font-bold uppercase tracking-widest text-lcars-muted">{title}</h2>
      <div className="text-sm text-lcars-text">{children}</div>
    </section>
  );
}

function pct(n: unknown): string {
  return typeof n === 'number' ? `${Math.round(n * 100)}%` : '—';
}

function Briefing({ d }: { d: any }) {
  return (
    <div className="flex flex-col gap-3">
      <Card title="Headline">
        <p className="font-semibold">{d.headline}</p>
        <p className="mt-1 text-xs text-lcars-muted">{d.note}</p>
      </Card>
      <Card title="Overnight">{d.what_changed_overnight || '—'}</Card>
      <div className="grid gap-3 sm:grid-cols-3">
        <Card title="Operating Picture">{d.operating_picture || '—'}</Card>
        <Card title="Wellness">{d.wellness || '—'}</Card>
        <Card title="Strategic">{d.strategic || '—'}</Card>
      </div>
      {(d.may_require_action ?? []).length > 0 && (
        <Card title="May Require Action">
          <ul className="list-disc pl-5">
            {d.may_require_action.map((t: any, i: number) => (
              <li key={i}>[{t.level}] <strong>{t.trigger_type}</strong>: {t.message}</li>
            ))}
          </ul>
        </Card>
      )}
      {(d.deserves_attention ?? []).length > 0 && (
        <Card title="Deserves Attention">
          <ul className="list-disc pl-5">
            {d.deserves_attention.map((t: any, i: number) => (
              <li key={i}>[{t.level}] <strong>{t.trigger_type}</strong>: {t.message}</li>
            ))}
          </ul>
        </Card>
      )}
      {(d.opportunities ?? []).length > 0 && (
        <Card title="Opportunities">
          <ul className="list-disc pl-5">
            {d.opportunities.map((o: any, i: number) => (
              <li key={i}>💡 <strong>{o.opportunity_type}</strong>: {o.message}</li>
            ))}
          </ul>
        </Card>
      )}
      {(d.forecasts ?? []).length > 0 && (
        <Card title="Forecasts">
          <ul className="list-disc pl-5">
            {d.forecasts.map((f: any, i: number) => (
              <li key={i}>
                <strong>{f.metric}</strong> ({f.confidence}, n={f.sample_size}): {f.projection}
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card title="Data Capture">{d.capture_prompt || '—'}</Card>
    </div>
  );
}

function Trust({ d }: { d: any }) {
  const gaps = d.capture_gaps ?? {};
  const trust = d.trust ?? {};
  return (
    <div className="flex flex-col gap-3">
      <Card title="Trust">
        <p>{trust.narrative}</p>
        <ul className="mt-2 list-disc pl-5">
          <li>Data completeness: {pct(trust.data_completeness)}</li>
          <li>Evidence quality: {pct(trust.evidence_quality)}</li>
          <li>Recommendation quality: {pct(trust.recommendation_quality)}</li>
          <li>Recognises uncertainty: {trust.recognises_uncertainty ? 'yes' : 'no'}</li>
        </ul>
      </Card>
      <Card title="Capture Gaps">
        <p>{gaps.narrative}</p>
        <ul className="mt-2 list-disc pl-5">
          {(gaps.gaps ?? [])
            .filter((g: any) => g.missing_count > 0 || g.standing)
            .map((g: any, i: number) => (
              <li key={i}>
                <strong>{g.kind}</strong> ({g.missing_count}): {g.why}
                <div className="text-xs text-lcars-muted">How: {g.how_to_capture}</div>
              </li>
            ))}
        </ul>
      </Card>
    </div>
  );
}

function Dashboard({ d }: { d: any }) {
  const totals = d.totals ?? {};
  const dash = d.dashboard ?? {};
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Card title="Activity">
        <ul className="space-y-1">
          <li>Advisory requests: {totals.advisory_requests ?? 0}</li>
          <li>Challenge requests: {totals.challenge_requests ?? 0}</li>
          <li>Outcomes recorded: {totals.outcomes_recorded ?? 0}</li>
          <li>Success rate: {pct(d.recommendation_success_rate)}</li>
        </ul>
      </Card>
      <Card title="Confidence Distribution">
        <ul className="space-y-1">
          {Object.entries(d.confidence_distribution ?? {}).map(([band, n]) => (
            <li key={band}>{band}: {n as number}</li>
          ))}
          {Object.keys(d.confidence_distribution ?? {}).length === 0 && <li>No data yet.</li>}
        </ul>
      </Card>
      <Card title="Advisor Participation">
        <ul className="space-y-1">
          {Object.entries(d.advisor_utilisation ?? {}).map(([o, n]) => (
            <li key={o}>{o}: {n as number}</li>
          ))}
          {Object.keys(d.advisor_utilisation ?? {}).length === 0 && <li>No data yet.</li>}
        </ul>
      </Card>
      <Card title="Recent Advice">
        <ul className="space-y-1">
          {(dash.recent_advice ?? []).map((r: any) => (
            <li key={r.advisory_id}>
              <span className="text-lcars-muted">{(r.recorded_at ?? '').slice(0, 10)}</span> {r.question}
              {r.outcome ? ` → ${r.outcome}` : ''}
            </li>
          ))}
          {(dash.recent_advice ?? []).length === 0 && <li>No advice recorded yet.</li>}
        </ul>
      </Card>
    </div>
  );
}

function Performance({ d }: { d: any }) {
  const ca = d.confidence_alignment ?? {};
  const ce = d.challenge_effectiveness ?? {};
  return (
    <div className="flex flex-col gap-3">
      <Card title="Recommendation Accuracy">
        <p>
          Overall: <strong>{pct(d.overall_accuracy)}</strong> (n={d.total_outcomes ?? 0})
          {!d.sufficient_data && <span className="text-lcars-muted"> · provisional</span>}
        </p>
      </Card>
      <Card title="Advisor Ranking">
        {(d.officer_ranking ?? []).length ? (
          <ul className="space-y-1">
            {d.officer_ranking.map((r: any) => (
              <li key={r.officer}>{r.officer}: {pct(r.accuracy)} (n={r.samples})</li>
            ))}
          </ul>
        ) : (
          'No officer outcome data yet.'
        )}
      </Card>
      <Card title="Confidence Calibration">
        <p>{ca.interpretation ?? '—'}</p>
      </Card>
      <Card title="Challenge Effectiveness">
        <p>{ce.note ?? '—'}</p>
      </Card>
    </div>
  );
}

function Timeline({ d }: { d: any }) {
  const span = d.span ?? {};
  return (
    <div className="flex flex-col gap-3">
      <Card title="History Span">
        <p>
          {span.earliest ?? '—'} → {span.latest ?? '—'} · {span.count ?? 0} events
        </p>
      </Card>
      <Card title="Recent Events">
        <ul className="space-y-1">
          {(d.events ?? []).slice(0, 25).map((e: any, i: number) => (
            <li key={i}>
              <span className="text-lcars-muted">{e.date}</span>{' '}
              <span className="uppercase text-xs">[{e.kind}]</span> {e.title}
              {e.outcome ? ` → ${e.outcome}` : ''}
            </li>
          ))}
          {(d.events ?? []).length === 0 && <li>No events on record.</li>}
        </ul>
      </Card>
    </div>
  );
}

function Operational({ d }: { d: any }) {
  const plan = d.notification_plan?.summary ?? {};
  return (
    <div className="flex flex-col gap-3">
      <Card title="Headline">
        <p>{d.headline}</p>
        <p className="mt-1 text-xs text-lcars-muted">{d.note}</p>
      </Card>
      <Card title="Emerging Signals">
        {(d.emerging_signals ?? []).length ? (
          <ul className="space-y-1">
            {d.emerging_signals.map((s: any, i: number) => (
              <li key={i}>
                <strong>{s.name}</strong> — {s.direction} ({s.severity}): {s.detail}
              </li>
            ))}
          </ul>
        ) : (
          'No emerging signals.'
        )}
      </Card>
      <Card title="Triggers">
        {(d.triggers ?? []).length ? (
          <ul className="space-y-1">
            {d.triggers.map((t: any, i: number) => (
              <li key={i}>[{t.level}] <strong>{t.trigger_type}</strong>: {t.message}</li>
            ))}
          </ul>
        ) : (
          'No active triggers.'
        )}
      </Card>
      <Card title="Opportunities">
        {(d.opportunities ?? []).length ? (
          <ul className="space-y-1">
            {d.opportunities.map((o: any, i: number) => (
              <li key={i}>💡 <strong>{o.opportunity_type}</strong>: {o.message}</li>
            ))}
          </ul>
        ) : (
          'No opportunities surfaced.'
        )}
      </Card>
      <Card title="Notification Routing">
        <p>Interrupt: {plan.interrupt ?? 0} · Daily brief: {plan.daily_brief ?? 0} · Wait: {plan.wait ?? 0}</p>
      </Card>
      <Card title="Advisory Health">
        <p>{d.advisory_health?.narrative ?? '—'}</p>
      </Card>
    </div>
  );
}
