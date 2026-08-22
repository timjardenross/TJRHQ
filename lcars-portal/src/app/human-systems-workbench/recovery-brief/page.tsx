'use client';

// Recovery Brief — wb-native replacement for the retired (app)/recovery-brief
// LCARS page. Leads with what the nervous system needs today; mission detail
// stays one link away on the Captain's Chair. References zero components
// rooted in the legacy LCARS system (see WorkbenchPanel.tsx/WorkbenchBadge.tsx
// for the established pattern this follows).
//
// RecoveryConfidencePanel and WellnessInsightPanel are NOT imported here —
// their content/data-fetching logic is ported inline below on wb-native
// markup, same as this session's other LCARS→wb migrations. Both source
// files are otherwise untouched; they still serve other (app) pages.

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { WorkbenchShell } from '@/components/ui';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { WorkbenchBadge } from '@/components/WorkbenchBadge';
import { DataSourceIndicator } from '@/components/DataSourceIndicator';
import { useROSData } from '@/lib/useROSData';
import { useRecoveryConfidence } from '@/lib/useRecoveryConfidence';
import { stateToneClasses } from '@/lib/departments';
import { recoveryBrief as mockBrief } from '@/lib/mockData';
import type { RecoveryPostureBand, StateTone } from '@/lib/types';

// ── Posture → state tone ───────────────────────────────────────────────────
// Mirrors ROSPanels.tsx / MobileOperatingPicture.tsx exactly (established
// 2026-08-10 fix): posture is a STATE, not a department, so it belongs on
// stateToneClasses (ok/warn/crit/unknown), never a department identity
// colour. Don't reinvent this mapping.
const POSTURE_STATE_TONE: Record<RecoveryPostureBand, StateTone> = {
  STRONG: 'ok',
  STABLE: 'ok',
  FRAGILE: 'warn',
  REST: 'crit',
  UNKNOWN: 'unknown',
};

// State-tone badge (mirrors ROSPanels.tsx's local StateBadge — WorkbenchBadge
// only carries StatusTone/department semantics, not the ok/warn/crit/unknown
// state system posture needs).
function StateBadge({ label, tone }: { label: string; tone: StateTone }) {
  const c = stateToneClasses(tone);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${c.text} ${c.border} ${c.bg}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} aria-hidden="true" />
      {label}
    </span>
  );
}

// ── Recovery Confidence (ported from RecoveryConfidencePanel) ─────────────

function escalationLevel(confidence: number, pulses: number): 0 | 1 | 2 | 3 {
  const hour = new Date().getHours();
  if (confidence === 0 && pulses === 0) {
    if (hour >= 14) return 3;
    if (hour >= 9) return 2;
    return 1;
  }
  if (confidence <= 25) return 2;
  if (confidence <= 50) return 1;
  return 0;
}

function escalationBorder(level: 0 | 1 | 2 | 3): string {
  if (level === 3) return stateToneClasses('crit').border;
  if (level === 2) return stateToneClasses('warn').border;
  return 'border-wb-line';
}

function PulseDot({ done, label }: { done: boolean; label: string }) {
  const c = stateToneClasses(done ? 'ok' : 'unknown');
  return (
    <div className="flex flex-col items-center gap-1">
      <span className={`h-2.5 w-2.5 rounded-full ${done ? c.dot : 'bg-wb-border'}`} aria-hidden="true" />
      <span className="text-[9px] uppercase tracking-wide text-wb-ink2">{label}</span>
    </div>
  );
}

function ConfidenceBar({ score }: { score: number }) {
  const tone: StateTone = score >= 75 ? 'ok' : score >= 50 ? 'warn' : 'crit';
  const c = stateToneClasses(tone);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-end">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${c.text} ${c.border} ${c.bg}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} aria-hidden="true" />
          {score}%
        </span>
      </div>
      <div className="h-3 rounded-full bg-wb-border/40 overflow-hidden">
        <div className={`h-full rounded-full ${c.dot} transition-all`} style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

function RecoveryConfidenceSection() {
  const { confidence, isLoading } = useRecoveryConfidence();
  if (isLoading) return null;

  const level = escalationLevel(confidence.recovery_confidence, confidence.pulses_completed);
  const border = escalationBorder(level);
  const bannerTone: StateTone = level === 3 ? 'crit' : 'warn';
  const bc = stateToneClasses(bannerTone);

  return (
    <WorkbenchPanel
      title="Recovery Confidence"
      eyebrow={confidence.confidence_label}
      actions={<WorkbenchBadge label="Pulse tracking" tone="medical" />}
    >
      <div className={`rounded-lg border ${border} bg-wb-bg/60 p-4 flex flex-col gap-4`}>
        {level >= 2 && (
          <div className={`rounded-md border ${bc.border} ${bc.bg} px-3 py-2 flex items-center gap-2`}>
            <span
              className={`h-1.5 w-1.5 rounded-full shrink-0 ${bc.dot} ${level === 3 ? 'animate-pulse' : ''}`}
              aria-hidden="true"
            />
            <span className={`text-xs font-bold uppercase tracking-widest shrink-0 ${bc.text}`}>
              {level === 3 ? 'Critical' : 'Attention'}
            </span>
            <span className="text-xs text-wb-ink/80">
              {level === 3
                ? 'No telemetry today — log a pulse to restore baseline.'
                : 'Recovery confidence below threshold — pulses needed.'}
            </span>
          </div>
        )}

        <ConfidenceBar score={confidence.recovery_confidence} />

        <div className="flex justify-between">
          <PulseDot done={confidence.morning_done} label="Morning" />
          <PulseDot done={confidence.midday_done} label="Midday" />
          <PulseDot done={confidence.end_of_day_done} label="End of day" />
          <PulseDot done={confidence.evening_done} label="Evening" />
        </div>

        {confidence.pulses_completed > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {confidence.latest_energy && (
              <div className="rounded-md border border-wb-line bg-wb-bg/60 p-2 text-center">
                <p className="text-[9px] uppercase tracking-wider text-wb-ink2">Energy</p>
                <p className="text-xs text-wb-ink/90 mt-0.5 capitalize">{confidence.latest_energy}</p>
              </div>
            )}
            {confidence.latest_nervous_system && (
              <div className="rounded-md border border-wb-line bg-wb-bg/60 p-2 text-center">
                <p className="text-[9px] uppercase tracking-wider text-wb-ink2">Nervous system</p>
                <p className="text-xs text-wb-ink/90 mt-0.5 capitalize">{confidence.latest_nervous_system}</p>
              </div>
            )}
            {confidence.latest_body_signals && (
              <div className="rounded-md border border-wb-line bg-wb-bg/60 p-2 text-center">
                <p className="text-[9px] uppercase tracking-wider text-wb-ink2">Body signals</p>
                <p className="text-xs text-wb-ink/90 mt-0.5 capitalize">{confidence.latest_body_signals}</p>
              </div>
            )}
            {confidence.latest_readiness && (
              <div className="rounded-md border border-wb-line bg-wb-bg/60 p-2 text-center">
                <p className="text-[9px] uppercase tracking-wider text-wb-ink2">Readiness</p>
                <p className="text-xs text-wb-ink/90 mt-0.5 capitalize">{confidence.latest_readiness}</p>
              </div>
            )}
          </div>
        )}

        <Link
          href="/medical/pulse"
          className="text-center rounded-lg bg-wb-sage-deep px-4 py-2 text-xs font-bold uppercase tracking-[0.2em] text-white hover:opacity-80 transition-opacity focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        >
          {confidence.pulses_completed === 0
            ? 'Log First Pulse →'
            : `Log Next Pulse (${confidence.pulses_missing} remaining) →`}
        </Link>
      </div>
    </WorkbenchPanel>
  );
}

// ── Wellness Intelligence (ported from WellnessInsightPanel) ──────────────

interface HealthInsights {
  created_at: string | null;
  llm_narrative: string | null;
  risk_flags: string[] | null;
  positive_flags: string[] | null;
  wins_this_week: string[] | null;
  cpap_compliance_rate: number | null;
  dow_pain_pattern: string | null;
}

interface DailyLog {
  log_date: string | null;
  sleep_hours: number | null;
  sleep_quality: string | null;
  cpap_compliant: boolean | null;
  nervous_system_state: string | null;
  sitting_tolerance_minutes: number | null;
  mood: string | null;
  energy: string | null;
}

interface WellnessData {
  insights: HealthInsights | null;
  daily: DailyLog | null;
}

function FlagChips({ items, tone }: { items: string[]; tone: StateTone }) {
  if (!items.length) return null;
  const c = stateToneClasses(tone);
  return (
    <div className="flex flex-wrap gap-1.5 mt-1">
      {items.map((f, i) => (
        <span
          key={i}
          className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${c.text} ${c.border} ${c.bg}`}
        >
          {f}
        </span>
      ))}
    </div>
  );
}

function WellnessIntelligenceSection() {
  const [data, setData] = useState<WellnessData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/wellness')
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ insights: null, daily: null }))
      .finally(() => setLoading(false));
  }, []);

  const insights = data?.insights ?? null;
  const daily = data?.daily ?? null;
  const hasData = !loading && (insights !== null || daily !== null);
  const date = insights?.created_at ?? daily?.log_date ?? null;
  const winsTone = stateToneClasses('ok');

  return (
    <WorkbenchPanel
      title="Wellness Intelligence"
      eyebrow={date ? `Health Insights · ${date}` : 'Health Insights · Wellness & Recovery Officer'}
      actions={<DataSourceIndicator live={hasData} loading={loading} />}
    >
      {loading && <p className="text-xs text-wb-ink2 animate-pulse">Fetching health intelligence…</p>}

      {!loading && !hasData && (
        <p className="text-xs text-wb-ink2">
          No health insights available yet. Log a check-in to generate the first wellness brief.
        </p>
      )}

      {insights?.llm_narrative && (
        <div className="rounded-lg border border-wb-sage/40 bg-wb-sage/5 p-4 mb-3">
          <p className="text-[10px] uppercase tracking-wider text-wb-sage-deep mb-2">Medical Officer Assessment</p>
          <p className="text-sm text-wb-ink/90 leading-relaxed">{insights.llm_narrative}</p>
        </div>
      )}

      {insights?.risk_flags?.length || insights?.positive_flags?.length ? (
        <div className="grid gap-3 sm:grid-cols-2 mb-3">
          {insights?.risk_flags?.length ? (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Risk Flags</p>
              <FlagChips items={insights.risk_flags} tone="crit" />
            </div>
          ) : null}
          {insights?.positive_flags?.length ? (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Positive Flags</p>
              <FlagChips items={insights.positive_flags} tone="ok" />
            </div>
          ) : null}
        </div>
      ) : null}

      {insights?.wins_this_week?.length ? (
        <div className="mb-3">
          <p className="text-[10px] uppercase tracking-wider text-wb-ink2 mb-1.5">Wins This Week</p>
          <div className="flex flex-col gap-1">
            {insights.wins_this_week.map((w, i) => (
              <div
                key={i}
                className="flex items-start gap-2 rounded-lg border border-wb-line bg-wb-bg/60 px-3 py-2 text-xs text-wb-ink/90"
              >
                <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${winsTone.dot}`} aria-hidden="true" />
                {w}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {daily && (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {daily.sleep_hours != null && (
            <div className="rounded-md border border-wb-line bg-wb-bg/60 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-wb-ink2">Sleep</p>
              <p className="text-xs text-wb-ink/90 mt-0.5 font-mono">
                {daily.sleep_hours}h
                {daily.cpap_compliant === true && (
                  <span className={stateToneClasses('ok').text}> · CPAP compliant</span>
                )}
                {daily.cpap_compliant === false && (
                  <span className={stateToneClasses('warn').text}> · CPAP not compliant</span>
                )}
              </p>
            </div>
          )}
          {daily.nervous_system_state && (
            <div className="rounded-md border border-wb-line bg-wb-bg/60 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-wb-ink2">Nervous System</p>
              <p className="text-xs text-wb-ink/90 mt-0.5 capitalize">{daily.nervous_system_state}</p>
            </div>
          )}
          {daily.energy && (
            <div className="rounded-md border border-wb-line bg-wb-bg/60 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-wb-ink2">Energy</p>
              <p className="text-xs text-wb-ink/90 mt-0.5 capitalize">{daily.energy}</p>
            </div>
          )}
          {daily.sitting_tolerance_minutes != null && (
            <div className="rounded-md border border-wb-line bg-wb-bg/60 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-wb-ink2">Sitting Tolerance</p>
              <p className="text-xs text-wb-ink/90 mt-0.5">{daily.sitting_tolerance_minutes} min</p>
            </div>
          )}
        </div>
      )}

      {(insights?.cpap_compliance_rate != null || insights?.dow_pain_pattern) && (
        <div className="grid gap-2 sm:grid-cols-2 mt-3">
          {insights?.cpap_compliance_rate != null && (
            <div className="rounded-lg border border-wb-line bg-wb-bg/60 p-3">
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">CPAP Compliance (7d)</p>
              <p className="text-lg font-semibold text-wb-navy mt-0.5">
                {Math.round(insights.cpap_compliance_rate * 100)}%
              </p>
            </div>
          )}
          {insights?.dow_pain_pattern && (
            <div className="rounded-lg border border-wb-line bg-wb-bg/60 p-3">
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Pain Pattern</p>
              <p className="text-sm text-wb-ink/90 mt-0.5">{insights.dow_pain_pattern}</p>
            </div>
          )}
        </div>
      )}
    </WorkbenchPanel>
  );
}

// ── Page ────────────────────────────────────────────────────────────────────

export default function RecoveryBriefPage() {
  const { posture: livePosture, bodyContext, isLive, isLoading } = useROSData();

  const brief = {
    stardate: mockBrief.stardate,
    posture: livePosture.posture,
    posture_message: livePosture.posture_message,
    capacity_message: livePosture.capacity_message,
    best_window: livePosture.best_window,
    sleep_summary: bodyContext.sleep_hours
      ? `${bodyContext.sleep_hours}h · ${bodyContext.sleep_quality}${bodyContext.cpap_compliant ? ' · CPAP compliant' : ''}`
      : mockBrief.sleep_summary,
    nervous_system: bodyContext.nervous_system_state,
    energy: bodyContext.energy,
  };

  const postureTone = POSTURE_STATE_TONE[brief.posture];
  const pc = stateToneClasses(postureTone);

  const [generated, setGenerated] = useState<string | null>(null);
  useEffect(() => {
    setGenerated(
      new Date().toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false }),
    );
  }, []);

  return (
    <WorkbenchShell
      title="Recovery Brief"
      eyebrow="Human Systems"
      tagline="USS TJR · Recovery Brief · Nervous system first, mission detail second"
      back={{ href: '/human-systems-workbench', label: 'Human Systems' }}
    >
      <div className="flex flex-col gap-4">
        <WorkbenchPanel
          title="Recovery Brief"
          eyebrow={`Stardate ${brief.stardate}${generated ? ` · Generated ${generated}` : ''}`}
          actions={<StateBadge label={brief.posture} tone={postureTone} />}
        >
          <p className="text-xs text-wb-ink2 mb-2">
            The Recovery Brief leads with what the nervous system needs today. Mission detail follows when
            capacity supports it.
          </p>
          <DataSourceIndicator
            live={isLive}
            loading={isLoading}
            variant="inline"
            liveLabel="Live · Supabase"
            mockLabel="Mock data — no check-in today"
            loadingLabel="Loading live data…"
          />
        </WorkbenchPanel>

        <RecoveryConfidenceSection />

        <WorkbenchPanel
          title="Recovery Posture"
          eyebrow="What does my system need today?"
          actions={<StateBadge label={brief.posture} tone={postureTone} />}
        >
          <div className={`rounded-lg border ${pc.border} ${pc.bg} p-5`}>
            <p className={`text-3xl font-bold ${pc.text}`}>{brief.posture}</p>
            <p className="mt-2 text-sm text-wb-ink/90 leading-relaxed">{brief.posture_message}</p>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-wb-line bg-wb-bg/60 p-3">
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Sleep last night</p>
              <p className="mt-1 text-sm text-wb-ink/90">{brief.sleep_summary}</p>
            </div>
            <div className="rounded-lg border border-wb-line bg-wb-bg/60 p-3">
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Nervous system</p>
              <p className="mt-1 text-sm text-wb-ink/90 capitalize">{brief.nervous_system}</p>
            </div>
            <div className="rounded-lg border border-wb-line bg-wb-bg/60 p-3">
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Energy</p>
              <p className="mt-1 text-sm text-wb-ink/90">{brief.energy}</p>
            </div>
          </div>
        </WorkbenchPanel>

        <WorkbenchPanel title="Capacity Today" eyebrow="What capacity is available?">
          <div className="rounded-lg border border-wb-navy/40 bg-wb-navy/5 p-4">
            <p className="text-sm text-wb-ink/90 leading-relaxed">{brief.capacity_message}</p>
            <div className="mt-3 flex flex-wrap gap-4">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Best window</p>
                <p className="text-lg font-semibold text-wb-navy">{brief.best_window}</p>
              </div>
            </div>
          </div>
        </WorkbenchPanel>

        <WellnessIntelligenceSection />

        <WorkbenchPanel title="Mission & Fleet" eyebrow="Context — available when needed">
          <p className="text-sm text-wb-ink/80">
            Live mission load and fleet status are maintained on the Captain&apos;s Chair.
          </p>
          <Link
            href="/captains-chair-workbench"
            className="mt-2 inline-block text-xs text-wb-sage-deep hover:opacity-70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          >
            Full mission detail and fleet status → Captain&apos;s Chair
          </Link>
        </WorkbenchPanel>

        <div className="rounded-lg border border-wb-line bg-wb-surface p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <p className="text-[10px] uppercase tracking-[0.25em] text-wb-ink2 mb-1">End of day</p>
            <p className="text-sm text-wb-ink/90">
              Complete today&apos;s Captain&apos;s Log entry to close the recovery loop.
            </p>
          </div>
          <Link
            href="/captains-log"
            className="shrink-0 rounded-lg bg-wb-sage-deep px-4 py-2 text-xs font-bold uppercase tracking-[0.2em] text-white hover:opacity-80 transition-opacity focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          >
            Log Today →
          </Link>
        </div>
      </div>
    </WorkbenchShell>
  );
}
