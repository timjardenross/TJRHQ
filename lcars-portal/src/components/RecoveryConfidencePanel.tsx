'use client';

import Link from 'next/link';
import { useRecoveryConfidence } from '@/lib/useRecoveryConfidence';
import { ConfidenceIndicator } from './ConfidenceIndicator';
import { EscalationBanner } from './EscalationBanner';
import { stateToneClasses } from '@/lib/departments';

// ── Escalation level (mirrors Telegram dispatcher logic) ──────────────────────

function escalationLevel(confidence: number, pulses: number): 0 | 1 | 2 | 3 {
  const hour = new Date().getHours();
  if (confidence === 0 && pulses === 0) {
    if (hour >= 14) return 3;
    if (hour >= 9)  return 2;
    return 1;
  }
  if (confidence <= 25) return 2;
  if (confidence <= 50) return 1;
  return 0;
}

// ── Escalation border classes ─────────────────────────────────────────────────
// Monotonic with EscalationBanner's tone mapping (level 3 = crit, 1/2 = warn) —
// previously level 3 used the `medical` (blue) border and level 2 used
// `operations` (red), so the more severe level read calmer than the less
// severe one. Fixed here as part of the same consolidation.

function escalationBorder(level: 0 | 1 | 2 | 3): string {
  if (level === 3) return stateToneClasses('crit').border;
  if (level === 2) return stateToneClasses('warn').border;
  return 'border-edge';
}

// ── Pulse dot ─────────────────────────────────────────────────────────────────

function PulseDot({ done, label }: { done: boolean; label: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className={`h-2.5 w-2.5 rounded-full ${done ? 'bg-medical' : 'bg-edge/40'}`} />
      <span className="text-[9px] uppercase tracking-wide text-lcars-muted">{label}</span>
    </div>
  );
}

// ── Panel ─────────────────────────────────────────────────────────────────────

export function RecoveryConfidencePanel({ compact = false }: { compact?: boolean }) {
  const { confidence, isLoading } = useRecoveryConfidence();

  if (isLoading) return null;

  const level  = escalationLevel(confidence.recovery_confidence, confidence.pulses_completed);
  const border = escalationBorder(level);

  if (compact) {
    return (
      <div className={`rounded-lcars border ${border} bg-panel/40 px-4 py-3 flex items-center gap-4`}>
        <div className="flex-1">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-1">Recovery confidence</p>
          <ConfidenceIndicator score={confidence.recovery_confidence} compact />
        </div>
        <div className="flex gap-3 shrink-0">
          <PulseDot done={confidence.morning_done}    label="AM" />
          <PulseDot done={confidence.midday_done}     label="Mid" />
          <PulseDot done={confidence.end_of_day_done} label="EOD" />
          <PulseDot done={confidence.evening_done}    label="PM" />
        </div>
        <Link
          href="/medical/pulse"
          className="shrink-0 rounded-lcars bg-medical px-3 py-1.5 font-lcars text-[11px] font-bold uppercase tracking-[0.15em] text-space hover:opacity-80 transition-opacity"
        >
          + Pulse
        </Link>
      </div>
    );
  }

  return (
    <div className={`rounded-lcars border ${border} bg-panel/40 p-4 flex flex-col gap-4`}>
      <div>
        <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted mb-0.5">Recovery Confidence</p>
        <p className="text-xs text-lcars-muted/80">{confidence.confidence_label}</p>
      </div>

      {/* Escalation alert — L2/L3 only */}
      {level >= 2 && (
        <EscalationBanner
          level={level as 2 | 3}
          message={
            level === 3
              ? 'No telemetry today — log a pulse to restore baseline.'
              : 'Recovery confidence below threshold — pulses needed.'
          }
        />
      )}

      <ConfidenceIndicator score={confidence.recovery_confidence} />

      {/* Pulse dots */}
      <div className="flex justify-between">
        <PulseDot done={confidence.morning_done}    label="Morning" />
        <PulseDot done={confidence.midday_done}     label="Midday" />
        <PulseDot done={confidence.end_of_day_done} label="End of day" />
        <PulseDot done={confidence.evening_done}    label="Evening" />
      </div>

      {/* Latest signals — energy/nervous_system/body_signals are the canonical
          Telegram-bot fields (Captain directive, 2026-08-10); mood/stress
          removed here since recovery_confidence_today stopped exposing them
          (migration 0115). */}
      {confidence.pulses_completed > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {confidence.latest_energy && (
            <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Energy</p>
              <p className="text-xs text-lcars-text/90 mt-0.5 capitalize">{confidence.latest_energy}</p>
            </div>
          )}
          {confidence.latest_nervous_system && (
            <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Nervous system</p>
              <p className="text-xs text-lcars-text/90 mt-0.5 capitalize">{confidence.latest_nervous_system}</p>
            </div>
          )}
          {confidence.latest_body_signals && (
            <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Body signals</p>
              <p className="text-xs text-lcars-text/90 mt-0.5 capitalize">{confidence.latest_body_signals}</p>
            </div>
          )}
          {confidence.latest_readiness && (
            <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Readiness</p>
              <p className="text-xs text-lcars-text/90 mt-0.5 capitalize">{confidence.latest_readiness}</p>
            </div>
          )}
        </div>
      )}

      <Link
        href="/medical/pulse"
        className="text-center rounded-lcars bg-medical px-4 py-2 font-lcars text-xs font-bold uppercase tracking-[0.2em] text-space hover:opacity-80 transition-opacity"
      >
        {confidence.pulses_completed === 0 ? 'Log First Pulse →' : `Log Next Pulse (${confidence.pulses_missing} remaining) →`}
      </Link>
    </div>
  );
}
