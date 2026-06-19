'use client';

import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import Link from 'next/link';
import { useROSData } from '@/lib/useROSData';
import {
  recoveryGuidance as mockGuidance,
  stageProgressionRecord,
  stageStatus
} from '@/lib/mockData';
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
      <Link
        href="/captains-chair"
        className="mt-2 block text-xs text-command hover:opacity-70"
      >
        Full posture detail and mission load guidance → Captain&apos;s Chair
      </Link>
    </LCARSPanel>
  );
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

  const guidance = mockGuidance; // Phase 2+: replace with health_insights fetch

  return (
    <div className="flex flex-col gap-4">

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

      {/* Two-column: body context + guidance */}
      <div className="grid gap-4 xl:grid-cols-2">
        <BodySignalsContextLive ctx={bodyContext} />
        <MedicalGuidance guidance={guidance} />
      </div>

      {/* Stage Progression card — full record on /stage-progression */}
      <StageProgressionCard record={stageProgressionRecord} />

      {/* Today's posture summary — links back to Captain's Chair for detail */}
      <PostureSummary posture={posture} />

    </div>
  );
}
