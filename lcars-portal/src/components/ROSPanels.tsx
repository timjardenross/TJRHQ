'use client';

/**
 * ROSPanels — client component that fetches live ROS data and renders
 * the recovery-first panels on the Captain's Chair.
 *
 * Imported by the Captain's Chair server page so the fleet sections
 * remain static while recovery data is live.
 */

import { useROSData } from '@/lib/useROSData';
import { stateToneClasses } from '@/lib/departments';
import { WorkbenchBadge } from './WorkbenchBadge';
import { WorkbenchPanel } from './WorkbenchPanel';
import { DataSourceIndicator } from './DataSourceIndicator';
import type {
  BodyContext,
  MissionLoadGuidanceData,
  RecoveryPosture,
  RecoveryPostureBand,
  StateTone
} from '@/lib/types';
import { missionLoadGuidance as mockMLG } from '@/lib/mockData';

// ── Tone maps ──────────────────────────────────────────────────────────────
//
// 2026-08-10: posture/body-signal severity was mapped through toneClasses()
// (department-identity colours: command/operations/medical/status), which a
// deliberate 2026-07-10 revision collapsed to one uniform navy accent for
// every non-neutral department (departments.ts's own toneClasses() comment:
// "Genuinely semantic status... is a completely separate system —
// stateToneClasses()... and is deliberately untouched"). Recovery posture
// is a STATE, not a department, so it belongs on stateToneClasses()
// (ok/warn/crit/unknown) — using toneClasses() here meant REST rendered
// identical navy to STRONG, not remotely alarming. StateBadge below mirrors
// StatusBadge's markup but on the state-tone system.

const POSTURE_STATE_TONE: Record<RecoveryPostureBand, StateTone> = {
  STRONG:  'ok',
  STABLE:  'ok',
  FRAGILE: 'warn',
  REST:    'crit',
  UNKNOWN: 'unknown'
};

const NS_STATE_TONE: Record<string, StateTone> = {
  calm:         'ok',
  activated:    'warn',
  dysregulated: 'warn'
};
const NS_LABEL: Record<string, string> = {
  calm:         'Calm',
  activated:    'Activated',
  dysregulated: 'Dysregulated'
};
const ENERGY_STATE_TONE: Record<string, StateTone> = {
  High: 'ok', Moderate: 'warn', Low: 'warn'
};
const SIGNAL_STATE_TONE: Record<string, StateTone> = {
  Low: 'ok', Moderate: 'warn', High: 'warn'
};

function StateBadge({ label, tone }: { label: string; tone: StateTone }) {
  const c = stateToneClasses(tone);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${c.text} ${c.border} ${c.bg}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
      {label}
    </span>
  );
}

// ── RecoveryPostureBlock ─────────────────────────────────────────────────────

function RecoveryPostureBlock({ posture }: { posture: RecoveryPosture }) {
  const tone = POSTURE_STATE_TONE[posture.posture];
  const c    = stateToneClasses(tone);
  return (
    <WorkbenchPanel
      title="Recovery Posture"
      eyebrow="What does my system need today?"
      actions={<StateBadge label={posture.posture} tone={tone} />}
    >
      <div className="grid gap-3 xl:grid-cols-2">
        <div className={`rounded-lg border ${c.border} ${c.bg} p-4`}>
          <p className={`text-2xl font-bold ${c.text}`}>{posture.posture}</p>
          <p className="mt-2 text-sm text-wb-ink/90 leading-relaxed">{posture.posture_message}</p>
        </div>
        <div className="rounded-lg border border-wb-border bg-wb-bg/60 p-4 flex flex-col gap-1">
          <p className="text-[10px] uppercase tracking-wider text-wb-ink2">{posture.capacity_band}</p>
          <p className="text-sm text-wb-ink/90 leading-relaxed">{posture.capacity_message}</p>
          {posture.best_window && (
            <p className="text-xs text-wb-ink2 mt-1">Best window: <span className="text-wb-ink">{posture.best_window}</span></p>
          )}
        </div>
      </div>
    </WorkbenchPanel>
  );
}

// ── BodyContextBlock ─────────────────────────────────────────────────────────

function BodyContextBlock({ ctx }: { ctx: BodyContext }) {
  const nsTone   = NS_STATE_TONE[ctx.nervous_system_state]   ?? 'unknown';
  const enTone   = ENERGY_STATE_TONE[ctx.energy]             ?? 'unknown';
  const sigTone  = SIGNAL_STATE_TONE[ctx.body_signals]       ?? 'unknown';

  const signals: { label: string; value: string; tone: StateTone }[] = [
    { label: 'Sleep',          value: `${ctx.sleep_hours}h · ${ctx.sleep_quality}`, tone: ctx.sleep_quality === 'Good' ? 'ok' : ctx.sleep_quality === 'Fair' ? 'warn' : 'warn' },
    { label: 'Nervous System', value: NS_LABEL[ctx.nervous_system_state] ?? ctx.nervous_system_state, tone: nsTone },
    { label: 'Energy',         value: ctx.energy, tone: enTone },
    { label: 'CPAP',           value: ctx.cpap_compliant ? 'Compliant' : 'Not recorded', tone: ctx.cpap_compliant ? 'ok' : 'unknown' },
    { label: 'Sitting window', value: `${ctx.sitting_window_minutes} min`, tone: 'unknown' },
    { label: 'Body signals',   value: ctx.body_signals, tone: sigTone }
  ];

  return (
    <WorkbenchPanel title="Body Context" eyebrow="What is the body signalling today?">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {signals.map((s) => {
          const c = stateToneClasses(s.tone);
          return (
            <div key={s.label} className={`rounded-lg border ${c.border} ${c.bg} p-3`}>
              <p className="text-[10px] uppercase tracking-wider text-wb-ink2">{s.label}</p>
              <p className={`mt-1 text-sm font-semibold ${c.text}`}>{s.value}</p>
            </div>
          );
        })}
      </div>
    </WorkbenchPanel>
  );
}

// ── RecoveryGuidanceBlock ────────────────────────────────────────────────────

function RecoveryGuidanceBlock({ guidance }: { guidance: string[] }) {
  return (
    <WorkbenchPanel
      title="Recovery Guidance"
      eyebrow="Medical Officer — standing orders"
      actions={<WorkbenchBadge label="Always present" tone="medical" />}
    >
      <ol className="flex flex-col gap-2">
        {guidance.map((item, i) => (
          <li key={i} className="flex gap-3 rounded-lg border border-wb-border bg-wb-bg/60 p-3 text-sm text-wb-ink/90 leading-relaxed">
            <span className="text-medical shrink-0">{i + 1}.</span>
            {item}
          </li>
        ))}
      </ol>
    </WorkbenchPanel>
  );
}

// ── MissionLoadGuidance ──────────────────────────────────────────────────────

function MissionLoadGuidance({ posture, mlg }: { posture: RecoveryPostureBand; mlg: MissionLoadGuidanceData }) {
  const tone = POSTURE_STATE_TONE[posture];
  const c    = stateToneClasses(tone);
  return (
    <WorkbenchPanel
      title="Today's Sustainable Load"
      eyebrow="What is safe and sustainable today?"
      actions={<DataSourceIndicator live={false} variant="inline" mockLabel="Mock data — not yet wired" />}
    >
      <div className="flex flex-col gap-2">
        <div className={`rounded-lg border ${c.border} ${c.bg} px-4 py-3`}>
          <p className={`text-sm font-semibold ${c.text}`}>Posture: {posture}</p>
        </div>
        <div className="rounded-lg border border-wb-border bg-wb-bg/60 px-4 py-3 text-sm text-wb-ink/90">
          <span className="text-wb-ink2">Active mission · </span>
          {mlg.active_mission_id} — {mlg.active_mission_safe ? 'safe to continue' : 'review recommended'}
        </div>
        <div className="rounded-lg border border-wb-border bg-wb-bg/60 px-4 py-3 text-sm text-wb-ink/90">
          <span className="text-wb-ink2">New starts · </span>
          {mlg.new_starts_recommended ? 'Appropriate today' : 'Not recommended today — hold for a STRONG day'}
        </div>
        {mlg.decisions_pending > 0 && (
          <div className="rounded-lg border border-wb-border bg-wb-bg/60 px-4 py-3 text-sm text-wb-ink/90">
            <span className="text-wb-ink2">Decisions · </span>
            {mlg.decisions_pending} pending — {mlg.defer_decisions ? 'defer to tomorrow if capacity allows' : 'within capacity to address'}
          </div>
        )}
      </div>
    </WorkbenchPanel>
  );
}

// ── Exported composite ───────────────────────────────────────────────────────

export function ROSPanels() {
  const { posture, bodyContext, guidance, isLive, isLoading } = useROSData();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <DataSourceIndicator
          live={isLive}
          loading={isLoading}
          variant="inline"
          liveLabel="Live · Supabase"
          mockLabel="Mock data — no check-in today"
          loadingLabel="Loading live data…"
        />
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
