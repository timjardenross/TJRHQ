'use client';

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import Link from 'next/link';
import { useROSData } from '@/lib/useROSData';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import {
  stageProgressionRecord,
  stageStatus
} from '@/lib/mockData';
import { WellnessInsightPanel } from '@/components/WellnessInsightPanel';
import { toneClasses } from '@/lib/departments';
import type {
  EmotionalLoadFlag,
  LifeParticipationScore,
  PostureHistory,
  RecoveryIndex,
  RecoveryPostureBand,
  StageProgressionRecord,
  StageStatus,
  StatusTone,
  WeeklyPatternSummary
} from '@/lib/types';

// metadata must be in a server component — moved to layout or a wrapper.

// ── Tab definitions ──────────────────────────────────────────────────────────

const TABS = [
  { key: 'overview',  label: 'Overview',  glyph: '●' },
  { key: 'pulse',     label: 'Pulse',     glyph: '♥' },
  { key: 'check-in',  label: 'Check-In',  glyph: '✚' },
  { key: 'trends',    label: 'Trends',    glyph: '↗' },
  { key: 'stage',     label: 'Stage',     glyph: '◈' },
] as const;
type Tab = typeof TABS[number]['key'];

interface TrendRow {
  log_date: string;
  energy_level: string | null;
  sleep_quality: string | null;
  nervous_system_state: string | null;
  pain_level: string | null;
}

// ── Posture band helpers ─────────────────────────────────────────────────────

const POSTURE_TONE: Record<RecoveryPostureBand, StatusTone> = {
  STRONG:  'status',
  STABLE:  'command',
  FRAGILE: 'operations',
  REST:    'medical',
  UNKNOWN: 'neutral'
};

const BAND_LABEL: Record<string, string> = {
  good:     'Good',
  moderate: 'Moderate',
  limited:  'Limited',
  rest:     'Rest',
  unknown:  'No data'
};

const BAND_TONE: Record<string, StatusTone> = {
  good:     'status',
  moderate: 'command',
  limited:  'operations',
  rest:     'medical',
  unknown:  'neutral'
};

// ── Stage display ────────────────────────────────────────────────────────────

function StageDisplay({ stage }: { stage: StageStatus }) {
  const c = toneClasses(stage.tone);
  return (
    <LCARSPanel title="Recovery Stage" accent="medical" eyebrow="ROS-001 v1.1">
      <div className={`flex items-start gap-4 rounded-lcars border ${c.border} ${c.bg} p-4`}>
        <div className={`shrink-0 font-lcars text-4xl font-bold ${c.text}`}>
          {stage.stage}
        </div>
        <div>
          <p className={`font-lcars text-sm font-semibold uppercase tracking-wider ${c.text}`}>
            {stage.label}
          </p>
          <p className="mt-1 text-sm text-lcars-text/80 leading-relaxed">
            {stage.description}
          </p>
        </div>
      </div>
    </LCARSPanel>
  );
}

// ── Life Participation Score ─────────────────────────────────────────────────

function LifeParticipationHero({ lp }: { lp: LifeParticipationScore }) {
  const tone = BAND_TONE[lp.band] ?? 'neutral';
  const c = toneClasses(tone);
  const sittingPct = Math.min(
    Math.round((lp.sitting_minutes / lp.sitting_baseline_minutes) * 100),
    100
  );

  const signals: { label: string; value: string; met: boolean }[] = [
    { label: 'Movement',          value: lp.movement_done ? 'Done' : 'Not recorded',   met: lp.movement_done },
    { label: 'Pleasure / creativity', value: lp.pleasure_marker ?? 'Not recorded',     met: !!lp.pleasure_marker },
    { label: 'Social noted',      value: lp.social_noted ? 'Present' : 'Not recorded', met: lp.social_noted },
    { label: 'Sitting tolerance', value: `${lp.sitting_minutes} min (${sittingPct}% of ${lp.sitting_baseline_minutes}-min baseline)`, met: sittingPct >= 50 },
    { label: 'Workload constraint', value: lp.workload_constraint === 'none' ? 'None' : lp.workload_constraint, met: lp.workload_constraint === 'none' || lp.workload_constraint === 'light' }
  ];

  return (
    <LCARSPanel
      title="Life Participation"
      accent="medical"
      eyebrow="Primary Stage 1 outcome measure"
      actions={<StatusBadge label={BAND_LABEL[lp.band]} tone={tone} />}
    >
      <p className="mb-4 text-xs text-lcars-muted leading-relaxed">
        Measures participation in life — not productivity. Recovery follows when the conditions
        for life are present. Pain reduction is a downstream effect.
      </p>

      {/* Hero score */}
      <div className={`flex items-center gap-4 rounded-lcars border ${c.border} ${c.bg} px-5 py-4 mb-4`}>
        <span className={`font-lcars text-5xl font-bold ${c.text}`}>{lp.score}</span>
        <div>
          <p className={`font-lcars text-sm font-semibold uppercase tracking-wider ${c.text}`}>
            {BAND_LABEL[lp.band]}
          </p>
          <p className="text-xs text-lcars-muted mt-0.5">out of 100 · today</p>
        </div>
      </div>

      {/* Component signals */}
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {signals.map((s) => (
          <div
            key={s.label}
            className="rounded-lcars border border-edge bg-space/40 p-3 flex items-start gap-2"
          >
            <span className={`mt-0.5 text-xs ${s.met ? 'text-status' : 'text-lcars-muted'}`}>
              {s.met ? '●' : '○'}
            </span>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{s.label}</p>
              <p className="text-sm text-lcars-text/90 mt-0.5">{s.value}</p>
            </div>
          </div>
        ))}
      </div>
    </LCARSPanel>
  );
}

// ── Four Recovery Indexes ────────────────────────────────────────────────────

function RecoveryIndexes({ indexes }: { indexes: RecoveryIndex[] }) {
  return (
    <LCARSPanel title="Recovery Indexes" accent="medical" eyebrow="Clinical indicators">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {indexes.map((idx) => {
          const tone = BAND_TONE[idx.band] ?? 'neutral';
          const c = toneClasses(tone);
          return (
            <div key={idx.key} className={`rounded-lcars border ${c.border} ${c.bg} p-4`}>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{idx.label}</p>
              <p className={`font-lcars text-lg font-semibold mt-1 ${c.text}`}>
                {BAND_LABEL[idx.band]}
              </p>
              <p className="text-xs text-lcars-text/70 mt-1 leading-relaxed">{idx.detail}</p>
            </div>
          );
        })}
      </div>
    </LCARSPanel>
  );
}

// ── Posture Pattern Chart ────────────────────────────────────────────────────

const POSTURE_ORDER: RecoveryPostureBand[] = ['STRONG', 'STABLE', 'FRAGILE', 'REST', 'UNKNOWN'];
const POSTURE_ROWS = ['STRONG', 'STABLE', 'FRAGILE', 'REST'] as const;

const POSTURE_BAR_COLOUR: Record<RecoveryPostureBand, string> = {
  STRONG:  'bg-status',
  STABLE:  'bg-command',
  FRAGILE: 'bg-operations',
  REST:    'bg-medical',
  UNKNOWN: 'bg-edge'
};

function PosturePatternChart({ history }: { history: PostureHistory }) {
  const { days, period_label } = history;

  return (
    <LCARSPanel
      title="Posture Pattern"
      accent="medical"
      eyebrow={period_label}
      actions={<StatusBadge label="Medical Bay" tone="medical" />}
    >
      <p className="mb-4 text-xs text-lcars-muted">
        Day-by-day posture bands. UNKNOWN indicates no check-in was recorded.
      </p>

      {/* Grid chart */}
      <div className="overflow-x-auto">
        <div
          className="grid gap-x-1"
          style={{ gridTemplateColumns: `80px repeat(${days.length}, minmax(40px, 1fr))` }}
        >
          {/* Header row — dates */}
          <div />
          {days.map((d) => (
            <div key={d.date} className="text-center text-[9px] text-lcars-muted pb-1 truncate">
              {d.date.slice(5)} {/* MM-DD */}
            </div>
          ))}

          {/* Band rows */}
          {POSTURE_ROWS.map((band) => (
            <>
              <div
                key={`label-${band}`}
                className="text-[10px] text-lcars-muted flex items-center pr-2 truncate"
              >
                {band}
              </div>
              {days.map((d) => {
                const active = d.posture === band;
                return (
                  <div key={`${band}-${d.date}`} className="flex items-center justify-center py-1">
                    <div
                      className={`h-5 w-full rounded-sm ${
                        active ? POSTURE_BAR_COLOUR[band] : 'bg-edge/30'
                      }`}
                    />
                  </div>
                );
              })}
            </>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap gap-3">
        {POSTURE_ROWS.map((band) => (
          <div key={band} className="flex items-center gap-1.5">
            <div className={`h-2.5 w-2.5 rounded-sm ${POSTURE_BAR_COLOUR[band]}`} />
            <span className="text-[10px] text-lcars-muted">{band}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5">
          <div className="h-2.5 w-2.5 rounded-sm bg-edge/30" />
          <span className="text-[10px] text-lcars-muted">No data</span>
        </div>
      </div>
    </LCARSPanel>
  );
}

// ── Emotional Load Flag ──────────────────────────────────────────────────────

function EmotionalLoadFlagPanel({ flag }: { flag: EmotionalLoadFlag }) {
  const tone: StatusTone = flag.raised ? 'operations' : 'status';
  const c = toneClasses(tone);
  return (
    <LCARSPanel
      title="Emotional Load Flag"
      accent="medical"
      eyebrow="Nervous system activation pattern"
      actions={<StatusBadge label={flag.raised ? 'Raised' : 'Clear'} tone={tone} />}
    >
      <div className={`flex items-start gap-3 rounded-lcars border ${c.border} ${c.bg} p-4`}>
        <span className={`text-xl ${c.text}`}>{flag.raised ? '⚑' : '●'}</span>
        <div>
          <p className="text-sm text-lcars-text/90 leading-relaxed">{flag.message}</p>
          <p className="mt-2 text-xs text-lcars-muted">
            {flag.period} — Activated: {flag.activated_days} day{flag.activated_days !== 1 ? 's' : ''} ·{' '}
            Dysregulated: {flag.dysregulated_days} day{flag.dysregulated_days !== 1 ? 's' : ''}
          </p>
          <p className="mt-1 text-[10px] text-lcars-muted italic">
            Flag raises when activated or dysregulated on 3+ of any 7 days.
          </p>
        </div>
      </div>
    </LCARSPanel>
  );
}

// ── Weekly Pattern Summary ───────────────────────────────────────────────────

function WeeklyPatternSummaryPanel({ summary }: { summary: WeeklyPatternSummary }) {
  const { period_7d, period_30d, direction_label } = summary;
  const recorded7d = period_7d.strong + period_7d.stable + period_7d.fragile + period_7d.rest;

  const bands: { label: string; count: number; tone: StatusTone }[] = [
    { label: 'Strong',  count: period_7d.strong,  tone: 'status' },
    { label: 'Stable',  count: period_7d.stable,  tone: 'command' },
    { label: 'Fragile', count: period_7d.fragile, tone: 'operations' },
    { label: 'Rest',    count: period_7d.rest,    tone: 'medical' }
  ];

  return (
    <LCARSPanel title="Pattern Summary" accent="medical" eyebrow="7-day and 30-day">
      <div className="grid gap-3 sm:grid-cols-2">
        {/* 7-day breakdown */}
        <div className="rounded-lcars border border-edge bg-space/40 p-4">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-3">Last 7 days</p>
          <div className="flex flex-col gap-1.5">
            {bands.map((b) => {
              const c = toneClasses(b.tone);
              return (
                <div key={b.label} className="flex items-center gap-2">
                  <span className={`w-14 shrink-0 text-[10px] uppercase tracking-wide ${c.text}`}>
                    {b.label}
                  </span>
                  <div className="flex-1 h-2 rounded-full bg-edge/40 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${c.dot}`}
                      style={{ width: `${(b.count / 7) * 100}%` }}
                    />
                  </div>
                  <span className={`w-4 text-right font-mono text-xs font-bold ${c.text}`}>
                    {b.count}
                  </span>
                </div>
              );
            })}
            {period_7d.unknown > 0 && (
              <p className="text-[10px] text-lcars-muted mt-1">
                {period_7d.unknown} day{period_7d.unknown !== 1 ? 's' : ''} without check-in
              </p>
            )}
          </div>
        </div>

        {/* 30-day and direction */}
        <div className="flex flex-col gap-3">
          <div className="rounded-lcars border border-edge bg-space/40 p-4">
            <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-1">Last 30 days</p>
            <p className="font-lcars text-lg font-semibold text-command">
              {period_30d.stable_or_strong} / {period_30d.total_recorded}
            </p>
            <p className="text-xs text-lcars-muted">days stable or strong (of recorded)</p>
            <p className="text-[10px] text-lcars-muted/70 mt-1 italic">
              Stage 2 signal: 14 of any 21 consecutive days stable or strong
            </p>
          </div>
          <div className="rounded-lcars border border-edge bg-space/40 p-4">
            <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-1">Direction</p>
            <p className="text-sm text-lcars-text/90 leading-relaxed">{direction_label}</p>
          </div>
        </div>
      </div>
    </LCARSPanel>
  );
}

// ── Capacity Restoration Progress (live) ─────────────────────────────────────

interface ReadinessTrendRow {
  assessment_date: string;
  readiness_score: number | null;
  sleep_hours: number | null;
  energy: string | null;
  readiness_status: string | null;
}

const STATUS_DOT: Record<string, string> = {
  green: 'bg-status',
  amber: 'bg-command',
  red:   'bg-operations',
};

function CapacityRestorationPanel({ rows }: { rows: ReadinessTrendRow[] }) {
  if (!rows.length) return null;
  const latest = rows[0];
  const older  = rows.slice(1);

  const avgScore = rows.reduce((s, r) => s + (r.readiness_score ?? 0), 0) / rows.filter(r => r.readiness_score != null).length;

  return (
    <LCARSPanel
      title="Capacity Restoration Progress"
      accent="medical"
      eyebrow={`D-055 · ${rows.length} readiness assessments · trend`}
      actions={<StatusBadge label="Live" tone="medical" />}
    >
      <p className="mb-4 text-xs text-lcars-muted leading-relaxed">
        Tracks movement from Stabilisation toward Capacity Restoration. Rising readiness over time
        signals the nervous system is settling — the primary D-055 objective.
      </p>

      {/* Latest + average */}
      <div className="grid gap-3 sm:grid-cols-3 mb-4">
        <div className="rounded-lcars border border-medical/40 bg-medical/5 p-3 text-center">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Latest score</p>
          <p className="font-lcars text-3xl font-bold text-medical mt-0.5">
            {latest.readiness_score ?? '—'}
          </p>
          {latest.readiness_status && (
            <div className="flex items-center justify-center gap-1.5 mt-1">
              <div className={`h-2 w-2 rounded-full ${STATUS_DOT[latest.readiness_status.toLowerCase()] ?? 'bg-edge'}`} />
              <span className="text-[10px] text-lcars-muted capitalize">{latest.readiness_status}</span>
            </div>
          )}
        </div>
        <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Avg ({rows.length})</p>
          <p className="font-lcars text-3xl font-bold text-command mt-0.5">
            {isNaN(avgScore) ? '—' : Math.round(avgScore)}
          </p>
        </div>
        <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Sleep latest</p>
          <p className="font-lcars text-3xl font-bold text-science mt-0.5">
            {latest.sleep_hours != null ? `${latest.sleep_hours}h` : '—'}
          </p>
        </div>
      </div>

      {/* Mini trend — most recent 7 */}
      {older.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-2">Recent history</p>
          <div className="flex flex-col gap-1.5">
            {rows.slice(0, 7).map((r) => {
              const pct = r.readiness_score != null ? Math.min(r.readiness_score, 100) : 0;
              const dot = r.readiness_status ? (STATUS_DOT[r.readiness_status.toLowerCase()] ?? 'bg-edge') : 'bg-edge';
              return (
                <div key={r.assessment_date} className="flex items-center gap-3">
                  <span className="w-16 shrink-0 text-[10px] text-lcars-muted font-mono">
                    {r.assessment_date.slice(5)}
                  </span>
                  <div className="flex-1 h-2.5 rounded-full bg-edge/30 overflow-hidden">
                    <div className={`h-full rounded-full ${dot} transition-all`} style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-8 text-right font-mono text-[10px] text-lcars-muted">
                    {r.readiness_score ?? '—'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </LCARSPanel>
  );
}

// ── Body Signals (pain as context — no numeric display) ──────────────────────

function BodySignalsContextLive({ ctx }: { ctx: import('@/lib/types').BodyContext }) {
  const ns = ctx.nervous_system_state;
  const NS_LABEL: Record<string, string> = {
    calm: 'Calm',
    activated: 'Activated',
    dysregulated: 'Dysregulated'
  };
  const NS_DETAIL: Record<string, string> = {
    calm: 'Settled baseline. Optimal window for engagement.',
    activated: 'Elevated activation. Protect capacity.',
    dysregulated: 'Dysregulated. Rest is the priority.'
  };

  const signals = [
    { label: 'Body Signals',    value: ctx.body_signals,   note: 'Contextual — not a recovery target' },
    { label: 'Nervous System',  value: NS_LABEL[ns],       note: NS_DETAIL[ns] },
    { label: 'Energy',          value: ctx.energy,         note: 'Subjective daily report' },
    { label: 'Sitting window',  value: `${ctx.sitting_window_minutes} min`, note: "Today's tolerance" }
  ];

  return (
    <LCARSPanel title="Body Context" accent="medical" eyebrow="For Medical Officer interpretation">
      <p className="mb-3 text-xs text-lcars-muted leading-relaxed">
        Body signals are recorded as context for Medical Officer review. They are not formula
        inputs and are not displayed as performance metrics. Pain and activation are lagging
        indicators — conditions, not targets.
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        {signals.map((s) => (
          <div key={s.label} className="rounded-lcars border border-edge bg-space/40 p-3">
            <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{s.label}</p>
            <p className="text-sm text-lcars-text/90 mt-0.5">{s.value}</p>
            <p className="text-[10px] text-lcars-muted/70 mt-0.5 italic">{s.note}</p>
          </div>
        ))}
      </div>
    </LCARSPanel>
  );
}

// ── Medical Officer Guidance ─────────────────────────────────────────────────

function MedicalGuidance({ guidance }: { guidance: string[] }) {
  return (
    <LCARSPanel
      title="Medical Officer Guidance"
      accent="medical"
      eyebrow="Standing orders — today"
      actions={<StatusBadge label="Active" tone="medical" />}
    >
      <ol className="flex flex-col gap-2">
        {guidance.map((item, i) => (
          <li key={i} className="flex gap-3 rounded-lcars border border-edge bg-space/40 p-3 text-sm text-lcars-text/90 leading-relaxed">
            <span className="font-lcars text-medical shrink-0">{i + 1}.</span>
            {item}
          </li>
        ))}
      </ol>
    </LCARSPanel>
  );
}

// ── Stage Progression card (compact — full record on /stage-progression) ─────

function StageProgressionCard({ record }: { record: StageProgressionRecord }) {
  const metCount = record.stage2_criteria.filter((c) => c.met === true).length;
  const total = record.stage2_criteria.length;
  const { stable_or_strong, total_recorded, threshold } = record.stability_signal;

  return (
    <LCARSPanel
      title="Stage Progression"
      accent="medical"
      eyebrow="Knowledge Officer record"
      actions={
        <Link
          href="/stage-progression"
          className="text-[10px] uppercase tracking-[0.15em] text-medical hover:text-medical/70"
        >
          Full Record →
        </Link>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="rounded-lcars border border-medical/40 bg-medical/5 p-3">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Current stage</p>
          <p className="font-lcars text-lg font-semibold text-medical mt-0.5">
            {record.current_stage_label}
          </p>
          <p className="text-xs text-lcars-muted mt-1">
            Transitions are recognised, not achieved. Consistent behaviour creates the conditions.
          </p>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <div className="rounded-lcars border border-edge bg-space/40 p-3">
            <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Stage 2 criteria</p>
            <p className="font-lcars text-lg font-semibold text-command mt-0.5">
              {metCount} / {total}
            </p>
            <p className="text-xs text-lcars-muted">criteria met or partial</p>
          </div>
          <div className="rounded-lcars border border-edge bg-space/40 p-3">
            <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Stability signal</p>
            <p className="font-lcars text-lg font-semibold text-command mt-0.5">
              {stable_or_strong} / {threshold}
            </p>
            <p className="text-xs text-lcars-muted">of {threshold} days needed ({total_recorded} recorded)</p>
          </div>
        </div>
      </div>
    </LCARSPanel>
  );
}

// ── Recovery Posture summary (compact — full detail on Captain's Chair) ──────

function PostureSummary({ posture }: { posture: import('@/lib/types').RecoveryPosture }) {
  const tone = POSTURE_TONE[posture.posture];
  const c = toneClasses(tone);
  return (
    <LCARSPanel title="Today's Posture" accent="medical" eyebrow="From Captain's Chair">
      <div className={`flex items-start gap-3 rounded-lcars border ${c.border} ${c.bg} p-4`}>
        <div>
          <p className={`font-lcars text-sm font-semibold uppercase tracking-wider ${c.text}`}>
            {posture.posture}
          </p>
          <p className="text-sm text-lcars-text/80 mt-1 leading-relaxed">
            {posture.posture_message}
          </p>
        </div>
      </div>
      <p className="mt-2 text-xs text-lcars-muted">
        Full posture detail and mission load guidance is on the Captain&apos;s Chair.
      </p>
    </LCARSPanel>
  );
}

// ── NS state colour helper ────────────────────────────────────────────────────

function nsColour(state: string | null): string {
  if (!state) return 'text-lcars-muted';
  const s = state.toLowerCase();
  if (s === 'calm') return 'text-status';
  if (s === 'activated') return 'text-command';
  if (s === 'dysregulated') return 'text-operations';
  return 'text-lcars-muted';
}

function energyColour(val: string | null): string {
  if (!val) return 'text-lcars-muted';
  const v = val.toLowerCase();
  if (v === 'good' || v === 'high') return 'text-status';
  if (v === 'moderate') return 'text-command';
  if (v === 'poor' || v === 'low') return 'text-operations';
  return 'text-lcars-muted';
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function MedicalPage() {
  const {
    posture,
    lifeParticipation,
    recoveryIndexes,
    postureHistory,
    weeklySummary,
    emotionalLoadFlag,
    bodyContext,
    isLive,
    isLoading
  } = useROSData();

  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [readinessTrend, setReadinessTrend] = useState<ReadinessTrendRow[]>([]);
  const [trendRows, setTrendRows] = useState<TrendRow[]>([]);

  useEffect(() => {
    async function load() {
      try {
        const supabase = createSupabaseBrowserClient();
        const { data } = await supabase
          .from('captain_readiness_history')
          .select('assessment_date, readiness_score, sleep_hours, energy, readiness_status')
          .order('assessment_date', { ascending: false })
          .limit(14);
        if (data?.length) setReadinessTrend(data as ReadinessTrendRow[]);
      } catch { /* fall through */ }
    }
    load();
  }, []);

  useEffect(() => {
    if (activeTab !== 'trends') return;
    async function loadTrends() {
      try {
        const supabase = createSupabaseBrowserClient();
        const { data } = await supabase
          .from('health_daily_logs')
          .select('log_date, energy_level, sleep_quality, nervous_system_state, pain_level')
          .order('log_date', { ascending: false })
          .limit(30);
        if (data?.length) setTrendRows(data as TrendRow[]);
      } catch { /* fall through */ }
    }
    loadTrends();
  }, [activeTab]);

  return (
    <div className="flex flex-col gap-4">

      {/* Tab bar */}
      <div className="flex border-b border-edge mb-4 overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-xs uppercase tracking-[0.15em] whitespace-nowrap transition-colors ${
              activeTab === tab.key
                ? 'border-b-2 border-medical text-medical font-semibold'
                : 'text-lcars-muted hover:text-lcars-text'
            }`}
          >
            {tab.glyph} {tab.label}
          </button>
        ))}
      </div>

      {/* Overview tab — all existing content */}
      {activeTab === 'overview' && (
        <>
          {/* Live data indicator */}
          <div className="flex justify-end text-[10px] uppercase tracking-wider text-lcars-muted">
            {isLoading ? (
              <span className="animate-pulse">Loading live data…</span>
            ) : (
              <span>{isLive ? '● Live · Supabase' : '○ Mock data — no check-in today'}</span>
            )}
          </div>

          {/* Stage — no countdown, no progress bar */}
          <StageDisplay stage={stageStatus} />

          {/* D-055 Capacity Restoration Progress — live trend */}
          <CapacityRestorationPanel rows={readinessTrend} />

          {/* Life Participation — primary Stage 1 outcome measure */}
          <LifeParticipationHero lp={lifeParticipation} />

          {/* Four recovery indexes */}
          <RecoveryIndexes indexes={recoveryIndexes} />

          {/* Posture pattern — Medical Bay only */}
          <PosturePatternChart history={postureHistory} />

          {/* Two-column: pattern summary + emotional load flag */}
          <div className="grid gap-4 xl:grid-cols-2">
            <WeeklyPatternSummaryPanel summary={weeklySummary} />
            <EmotionalLoadFlagPanel flag={emotionalLoadFlag} />
          </div>

          {/* Wellness Intelligence — live from health_insights + health_daily_logs */}
          <WellnessInsightPanel />

          {/* Body context */}
          <BodySignalsContextLive ctx={bodyContext} />

          {/* Quick log actions */}
          <div className="grid gap-3 sm:grid-cols-3">
            <Link
              href="/medical/check-in"
              className="rounded-lcars border border-medical/40 bg-medical/5 px-4 py-3 text-center hover:bg-medical/10 transition-colors"
            >
              <p className="font-lcars text-xs font-bold uppercase tracking-wider text-medical">Daily Check-In</p>
              <p className="text-[10px] text-lcars-muted mt-0.5">Sleep · NS · Energy · Mood</p>
            </Link>
            <Link
              href="/medical/log-activity"
              className="rounded-lcars border border-status/40 bg-status/5 px-4 py-3 text-center hover:bg-status/10 transition-colors"
            >
              <p className="font-lcars text-xs font-bold uppercase tracking-wider text-status">Log Activity</p>
              <p className="text-[10px] text-lcars-muted mt-0.5">Walk · Physio · Stretch · more</p>
            </Link>
            <Link
              href="/medical/log-weight"
              className="rounded-lcars border border-command/40 bg-command/5 px-4 py-3 text-center hover:bg-command/10 transition-colors"
            >
              <p className="font-lcars text-xs font-bold uppercase tracking-wider text-command">Log Weight</p>
              <p className="text-[10px] text-lcars-muted mt-0.5">Daily weigh-in · 30-day trend</p>
            </Link>
          </div>

          {/* Stage Progression card — full record on /stage-progression */}
          <StageProgressionCard record={stageProgressionRecord} />

          {/* Today's posture summary — links back to Captain's Chair for detail */}
          <PostureSummary posture={posture} />
        </>
      )}

      {/* Pulse tab */}
      {activeTab === 'pulse' && (
        <div className="flex flex-col gap-4">
          <div className="rounded-lcars border border-medical/40 bg-medical/5 p-6 text-center">
            <p className="font-lcars text-2xl font-bold text-medical mb-2">Daily Pulse Log</p>
            <p className="text-sm text-lcars-muted mb-4">Record energy, pain, mood and nervous system state up to 4 times daily.</p>
            <Link href="/medical/pulse" className="inline-block rounded-lcars border border-medical bg-medical/20 px-6 py-3 font-lcars text-sm font-bold uppercase tracking-wider text-medical hover:bg-medical/30 transition-colors">
              Open Pulse Log →
            </Link>
          </div>
          <p className="text-xs text-lcars-muted text-center">Pulse logs are recorded throughout the day and feed the recovery indexes above.</p>
        </div>
      )}

      {/* Check-In tab */}
      {activeTab === 'check-in' && (
        <div className="rounded-lcars border border-command/40 bg-command/5 p-6 text-center">
          <p className="font-lcars text-2xl font-bold text-command mb-2">Daily Check-In</p>
          <p className="text-sm text-lcars-muted mb-4">Sleep quality, nervous system baseline, energy, mood, pain, and intentions for today.</p>
          <Link href="/medical/check-in" className="inline-block rounded-lcars border border-command bg-command/20 px-6 py-3 font-lcars text-sm font-bold uppercase tracking-wider text-command hover:bg-command/30 transition-colors">
            Open Daily Check-In →
          </Link>
        </div>
      )}

      {/* Trends tab */}
      {activeTab === 'trends' && (
        <LCARSPanel title="30-Day Health Trends" accent="medical" eyebrow="health_daily_logs · last 30 entries">
          {trendRows.length === 0 ? (
            <p className="text-sm text-lcars-muted text-center py-8">No trend data available yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-edge">
                    <th className="text-left py-2 pr-4 text-[10px] uppercase tracking-wider text-lcars-muted font-normal">Date</th>
                    <th className="text-left py-2 pr-4 text-[10px] uppercase tracking-wider text-lcars-muted font-normal">Energy</th>
                    <th className="text-left py-2 pr-4 text-[10px] uppercase tracking-wider text-lcars-muted font-normal">Sleep</th>
                    <th className="text-left py-2 pr-4 text-[10px] uppercase tracking-wider text-lcars-muted font-normal">NS State</th>
                    <th className="text-left py-2 text-[10px] uppercase tracking-wider text-lcars-muted font-normal">Pain</th>
                  </tr>
                </thead>
                <tbody>
                  {trendRows.map((row) => (
                    <tr key={row.log_date} className="border-b border-edge/40 hover:bg-space/30">
                      <td className="py-2 pr-4 font-mono text-lcars-muted">{row.log_date}</td>
                      <td className={`py-2 pr-4 ${energyColour(row.energy_level)}`}>{row.energy_level ?? '—'}</td>
                      <td className={`py-2 pr-4 ${energyColour(row.sleep_quality)}`}>{row.sleep_quality ?? '—'}</td>
                      <td className={`py-2 pr-4 ${nsColour(row.nervous_system_state)}`}>{row.nervous_system_state ?? '—'}</td>
                      <td className="py-2 text-lcars-text/80">{row.pain_level ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </LCARSPanel>
      )}

      {/* Stage tab */}
      {activeTab === 'stage' && (
        <div className="flex flex-col gap-4">
          <StageProgressionCard record={stageProgressionRecord} />
          <div className="rounded-lcars border border-edge bg-space/40 p-4">
            <p className="text-sm text-lcars-muted leading-relaxed mb-3">
              Stage tracking observes patterns over time. Transitions are recognised, not achieved.
            </p>
            <Link href="/human-systems" className="text-xs uppercase tracking-[0.15em] text-medical hover:text-medical/70 transition-colors">
              Human Systems Framework →
            </Link>
          </div>
        </div>
      )}

    </div>
  );
}
