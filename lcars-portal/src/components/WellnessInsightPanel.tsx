'use client';

import { useEffect, useState } from 'react';
import { LCARSPanel } from './LCARSPanel';
import { DataSourceIndicator } from './DataSourceIndicator';

interface HealthInsights {
  created_at:            string | null;
  llm_narrative:         string | null;
  risk_flags:            string[] | null;
  positive_flags:        string[] | null;
  wins_this_week:        string[] | null;
  cpap_compliance_rate:  number | null;
  dow_pain_pattern:      string | null;
}

interface DailyLog {
  log_date:                  string | null;
  sleep_hours:               number | null;
  sleep_quality:             string | null;
  cpap_compliant:            boolean | null;
  nervous_system_state:      string | null;
  sitting_tolerance_minutes: number | null;
  mood:                      string | null;
  energy:                    string | null;
}

interface WellnessData {
  insights: HealthInsights | null;
  daily:    DailyLog | null;
}

function FlagChips({ items, tone }: { items: string[]; tone: 'risk' | 'positive' }) {
  if (!items.length) return null;
  const cls = tone === 'risk'
    ? 'border-operations/60 bg-operations/10 text-operations'
    : 'border-status/60 bg-status/10 text-status';
  return (
    <div className="flex flex-wrap gap-1.5 mt-1">
      {items.map((f, i) => (
        <span key={i} className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${cls}`}>
          {f}
        </span>
      ))}
    </div>
  );
}

export function WellnessInsightPanel() {
  const [data, setData]       = useState<WellnessData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/wellness')
      .then(r => r.json())
      .then(setData)
      .catch(() => setData({ insights: null, daily: null }))
      .finally(() => setLoading(false));
  }, []);

  const insights = data?.insights ?? null;
  const daily    = data?.daily ?? null;

  const hasData = !loading && (insights !== null || daily !== null);
  const date    = insights?.created_at ?? daily?.log_date ?? null;

  return (
    <LCARSPanel
      title="Wellness Intelligence"
      accent="medical"
      eyebrow={date ? `Health Insights · ${date}` : 'Health Insights · Wellness & Recovery Officer'}
      actions={<DataSourceIndicator live={hasData} loading={loading} />}
    >
      {loading && (
        <p className="text-xs text-lcars-muted animate-pulse">Fetching health intelligence…</p>
      )}

      {!loading && !hasData && (
        <p className="text-xs text-lcars-muted">
          No health insights available yet. Log a check-in to generate the first wellness brief.
        </p>
      )}

      {/* LLM Narrative */}
      {insights?.llm_narrative && (
        <div className="rounded-lcars border border-medical/40 bg-medical/5 p-4 mb-3">
          <p className="text-[10px] uppercase tracking-wider text-medical mb-2">Medical Officer Assessment</p>
          <p className="text-sm text-lcars-text/90 leading-relaxed">{insights.llm_narrative}</p>
        </div>
      )}

      {/* Risk + Positive flags */}
      {(insights?.risk_flags?.length || insights?.positive_flags?.length) ? (
        <div className="grid gap-3 sm:grid-cols-2 mb-3">
          {insights?.risk_flags?.length ? (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Risk Flags</p>
              <FlagChips items={insights.risk_flags} tone="risk" />
            </div>
          ) : null}
          {insights?.positive_flags?.length ? (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Positive Flags</p>
              <FlagChips items={insights.positive_flags} tone="positive" />
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Wins this week */}
      {insights?.wins_this_week?.length ? (
        <div className="mb-3">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-1.5">Wins This Week</p>
          <div className="flex flex-col gap-1">
            {insights.wins_this_week.map((w, i) => (
              <div key={i} className="flex gap-2 rounded-lcars border border-edge bg-space/40 px-3 py-2 text-xs text-lcars-text/90">
                <span className="text-status shrink-0">✓</span>
                {w}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Today's daily log signals */}
      {daily && (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {daily.sleep_hours != null && (
            <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Sleep</p>
              <p className="text-xs text-lcars-text/90 mt-0.5 font-mono">
                {daily.sleep_hours}h
                {daily.cpap_compliant === true  ? ' ✓' : ''}
                {daily.cpap_compliant === false ? ' ✗' : ''}
              </p>
            </div>
          )}
          {daily.nervous_system_state && (
            <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Nervous System</p>
              <p className="text-xs text-lcars-text/90 mt-0.5 capitalize">{daily.nervous_system_state}</p>
            </div>
          )}
          {daily.energy && (
            <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Energy</p>
              <p className="text-xs text-lcars-text/90 mt-0.5 capitalize">{daily.energy}</p>
            </div>
          )}
          {daily.sitting_tolerance_minutes != null && (
            <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Sitting Tolerance</p>
              <p className="text-xs text-lcars-text/90 mt-0.5">{daily.sitting_tolerance_minutes} min</p>
            </div>
          )}
        </div>
      )}

      {/* CPAP compliance + DOW pain pattern */}
      {(insights?.cpap_compliance_rate != null || insights?.dow_pain_pattern) && (
        <div className="grid gap-2 sm:grid-cols-2 mt-3">
          {insights?.cpap_compliance_rate != null && (
            <div className="rounded-lcars border border-edge bg-space/40 p-3">
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">CPAP Compliance (7d)</p>
              <p className="font-lcars text-lg font-semibold text-command mt-0.5">
                {Math.round(insights.cpap_compliance_rate * 100)}%
              </p>
            </div>
          )}
          {insights?.dow_pain_pattern && (
            <div className="rounded-lcars border border-edge bg-space/40 p-3">
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Pain Pattern</p>
              <p className="text-sm text-lcars-text/90 mt-0.5">{insights.dow_pain_pattern}</p>
            </div>
          )}
        </div>
      )}
    </LCARSPanel>
  );
}
