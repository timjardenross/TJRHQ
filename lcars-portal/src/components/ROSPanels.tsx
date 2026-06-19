'use client';

/**
 * ROSPanels — client component that fetches live ROS data and renders
 * the recovery-first panels on the Captain's Chair.
 *
 * Imported by the Captain's Chair server page so the fleet sections
 * remain static while recovery data is live.
 */

import { useROSData } from '@/lib/useROSData';
import { toneClasses } from '@/lib/departments';
import { StatusBadge } from './StatusBadge';
import { LCARSPanel } from './LCARSPanel';
import type {
  BodyContext,
  MissionLoadGuidanceData,
  RecoveryPosture,
  RecoveryPostureBand,
  StatusTone
} from '@/lib/types';
import { missionLoadGuidance as mockMLG } from '@/lib/mockData';

// ── Tone maps ──────────────────────────────────────────────────────────────

const POSTURE_TONE: Record<RecoveryPostureBand, StatusTone> = {
  STRONG:  'status',
  STABLE:  'command',
  FRAGILE: 'operations',
  REST:    'medical',
  UNKNOWN: 'neutral'
};

const NS_TONE: Record<string, StatusTone> = {
  calm:         'status',
  activated:    'command',
  dysregulated: 'operations'
};
const NS_LABEL: Record<string, string> = {
  calm:         'Calm',
  activated:    'Activated',
  dysregulated: 'Dysregulated'
};
const ENERGY_TONE: Record<string, StatusTone> = {
  High: 'status', Moderate: 'command', Low: 'operations'
};
const SIGNAL_TONE: Record<string, StatusTone> = {
  Low: 'status', Moderate: 'command', High: 'operations'
};

// ── RecoveryPostureBlock ─────────────────────────────────────────────────────

function RecoveryPostureBlock({ posture }: { posture: RecoveryPosture }) {
  const tone = POSTURE_TONE[posture.posture];
  const c    = toneClasses(tone);
  return (
    <LCARSPanel
      title="Recovery Posture"
      accent="medical"
      eyebrow="What does my system need today?"
      actions={<StatusBadge label={posture.posture} tone={tone} />}
    >
      <div className="grid gap-3 xl:grid-cols-2">
        <div className={`rounded-lcars border ${c.border} ${c.bg} p-4`}>
          <p className={`font-lcars text-2xl font-bold ${c.text}`}>{posture.posture}</p>
          <p className="mt-2 text-sm text-lcars-text/90 leading-relaxed">{posture.posture_message}</p>
        </div>
        <div className="rounded-lcars border border-edge bg-space/40 p-4 flex flex-col gap-1">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{posture.capacity_band}</p>
          <p className="text-sm text-lcars-text/90 leading-relaxed">{posture.capacity_message}</p>
          {posture.best_window && (
            <p className="text-xs text-lcars-muted mt-1">Best window: <span className="text-lcars-text">{posture.best_window}</span></p>
          )}
        </div>
      </div>
    </LCARSPanel>
  );
}

// ── BodyContextBlock ─────────────────────────────────────────────────────────

function BodyContextBlock({ ctx }: { ctx: BodyContext }) {
  const nsTone   = NS_TONE[ctx.nervous_system_state]   ?? 'neutral';
  const enTone   = ENERGY_TONE[ctx.energy]             ?? 'neutral';
  const sigTone  = SIGNAL_TONE[ctx.body_signals]       ?? 'neutral';

  const signals: { label: string; value: string; tone: StatusTone }[] = [
    { label: 'Sleep',          value: `${ctx.sleep_hours}h · ${ctx.sleep_quality}`, tone: ctx.sleep_quality === 'Good' ? 'status' : ctx.sleep_quality === 'Fair' ? 'command' : 'operations' },
    { label: 'Nervous System', value: NS_LABEL[ctx.nervous_system_state] ?? ctx.nervous_system_state, tone: nsTone },
    { label: 'Energy',         value: ctx.energy, tone: enTone },
    { label: 'CPAP',           value: ctx.cpap_compliant ? 'Compliant' : 'Not recorded', tone: ctx.cpap_compliant ? 'status' : 'neutral' },
    { label: 'Sitting window', value: `${ctx.sitting_window_minutes} min`, tone: 'neutral' },
    { label: 'Body signals',   value: ctx.body_signals, tone: sigTone }
  ];

  return (
    <LCARSPanel title="Body Context" accent="medical" eyebrow="What is the body signalling today?">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {signals.map((s) => {
          const c = toneClasses(s.tone);
          return (
            <div key={s.label} className={`rounded-lcars border ${c.border} ${c.bg} p-3`}>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{s.label}</p>
              <p className={`mt-1 text-sm font-semibold ${c.text}`}>{s.value}</p>
            </div>
          );
        })}
      </div>
    </LCARSPanel>
  );
}

// ── RecoveryGuidanceBlock ────────────────────────────────────────────────────

function RecoveryGuidanceBlock({ guidance }: { guidance: string[] }) {
  return (
    <LCARSPanel
      title="Recovery Guidance"
      accent="medical"
      eyebrow="Medical Officer — standing orders"
      actions={<StatusBadge label="Always present" tone="medical" />}
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

// ── MissionLoadGuidance ──────────────────────────────────────────────────────

function MissionLoadGuidance({ posture, mlg }: { posture: RecoveryPostureBand; mlg: MissionLoadGuidanceData }) {
  const tone = POSTURE_TONE[posture];
  const c    = toneClasses(tone);
  return (
    <LCARSPanel title="Today's Sustainable Load" accent="medical" eyebrow="What is safe and sustainable today?">
      <div className="flex flex-col gap-2">
        <div className={`rounded-lcars border ${c.border} ${c.bg} px-4 py-3`}>
          <p className={`text-sm font-semibold ${c.text}`}>Posture: {posture}</p>
        </div>
        <div className="rounded-lcars border border-edge bg-space/40 px-4 py-3 text-sm text-lcars-text/90">
          <span className="text-lcars-muted">Active mission · </span>
          {mlg.active_mission_id} — {mlg.active_mission_safe ? 'safe to continue' : 'review recommended'}
        </div>
        <div className="rounded-lcars border border-edge bg-space/40 px-4 py-3 text-sm text-lcars-text/90">
          <span className="text-lcars-muted">New starts · </span>
          {mlg.new_starts_recommended ? 'Appropriate today' : 'Not recommended today — hold for a STRONG day'}
        </div>
        {mlg.decisions_pending > 0 && (
          <div className="rounded-lcars border border-edge bg-space/40 px-4 py-3 text-sm text-lcars-text/90">
            <span className="text-lcars-muted">Decisions · </span>
            {mlg.decisions_pending} pending — {mlg.defer_decisions ? 'defer to tomorrow if capacity allows' : 'within capacity to address'}
          </div>
        )}
      </div>
    </LCARSPanel>
  );
}

// ── Live data indicator ───────────────────────────────────────────────────────

function DataSourceBadge({ isLive, isLoading }: { isLive: boolean; isLoading: boolean }) {
  if (isLoading) return (
    <div className="text-[10px] uppercase tracking-wider text-lcars-muted animate-pulse">
      Loading live data…
    </div>
  );
  return (
    <div className="text-[10px] uppercase tracking-wider text-lcars-muted">
      {isLive ? '● Live · Supabase' : '○ Mock data — no check-in today'}
    </div>
  );
}

// ── Exported composite ───────────────────────────────────────────────────────

export function ROSPanels() {
  const { posture, bodyContext, guidance, isLive, isLoading } = useROSData();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <DataSourceBadge isLive={isLive} isLoading={isLoading} />
      </div>
      <RecoveryPostureBlock posture={posture} />
      <BodyContextBlock ctx={bodyContext} />
      <div className="grid gap-4 xl:grid-cols-2">
        <RecoveryGuidanceBlock guidance={guidance} />
        <MissionLoadGuidance posture={posture.posture} mlg={mockMLG} />
      </div>
    </div>
  );
}
