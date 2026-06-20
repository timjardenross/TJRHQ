'use client';

import Link from 'next/link';
import { useRecoveryConfidence } from '@/lib/useRecoveryConfidence';
import { StatusBadge } from './StatusBadge';
import type { StatusTone } from '@/lib/types';

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

// ── Confidence tone ───────────────────────────────────────────────────────────

function confidenceTone(score: number): StatusTone {
  if (score === 100) return 'status';
  if (score >= 75)   return 'command';
  if (score >= 50)   return 'operations';
  return 'neutral';
}

function confidenceBarColour(score: number): string {
  if (score === 100) return 'bg-status';
  if (score >= 75)   return 'bg-command';
  if (score >= 50)   return 'bg-operations';
  return 'bg-lcars-muted';
}

// ── Escalation border / banner classes ───────────────────────────────────────

function escalationBorder(level: 0 | 1 | 2 | 3): string {
  if (level === 3) return 'border-medical';
  if (level === 2) return 'border-operations';
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

// ── Escalation alert banner ───────────────────────────────────────────────────

function EscalationBanner({ level }: { level: 2 | 3 }) {
  if (level === 3) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-medical bg-medical/10 px-3 py-2">
        <span className="animate-pulse text-medical text-xs font-bold uppercase tracking-widest">⚠ Critical</span>
        <span className="text-xs text-lcars-text/80">No telemetry today — log a pulse to restore baseline.</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 rounded-md border border-operations bg-operations/10 px-3 py-2">
      <span className="text-operations text-xs font-bold uppercase tracking-widest">Low</span>
      <span className="text-xs text-lcars-text/80">Recovery confidence below threshold — pulses needed.</span>
    </div>
  );
}

// ── Panel ─────────────────────────────────────────────────────────────────────

export function RecoveryConfidencePanel({ compact = false }: { compact?: boolean }) {
  const { confidence, isLoading } = useRecoveryConfidence();

  if (isLoading) return null;

  const level  = escalationLevel(confidence.recovery_confidence, confidence.pulses_completed);
  const tone   = confidenceTone(confidence.recovery_confidence);
  const barCls = confidenceBarColour(confidence.recovery_confidence);
  const border = escalationBorder(level);

  if (compact) {
    return (
      <div className={`rounded-lcars border ${border} bg-panel/40 px-4 py-3 flex items-center gap-4`}>
        <div className="flex-1">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-1">Recovery confidence</p>
          <div className="flex items-center gap-3">
            <div className="flex-1 h-2 rounded-full bg-edge/30 overflow-hidden">
              <div className={`h-full rounded-full ${barCls} transition-all`} style={{ width: `${confidence.recovery_confidence}%` }} />
            </div>
            <span className={`font-lcars text-sm font-bold shrink-0 ${tone === 'status' ? 'text-status' : tone === 'command' ? 'text-command' : tone === 'operations' ? 'text-operations' : 'text-lcars-muted'}`}>
              {confidence.recovery_confidence}%
            </span>
          </div>
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
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted mb-0.5">Recovery Confidence</p>
          <p className="text-xs text-lcars-muted/80">{confidence.confidence_label}</p>
        </div>
        <StatusBadge label={`${confidence.recovery_confidence}%`} tone={tone} />
      </div>

      {/* Escalation alert — L2/L3 only */}
      {level >= 2 && <EscalationBanner level={level as 2 | 3} />}

      {/* Progress bar */}
      <div className="h-3 rounded-full bg-edge/30 overflow-hidden">
        <div className={`h-full rounded-full ${barCls} transition-all`} style={{ width: `${confidence.recovery_confidence}%` }} />
      </div>

      {/* Pulse dots */}
      <div className="flex justify-between">
        <PulseDot done={confidence.morning_done}    label="Morning" />
        <PulseDot done={confidence.midday_done}     label="Midday" />
        <PulseDot done={confidence.end_of_day_done} label="End of day" />
        <PulseDot done={confidence.evening_done}    label="Evening" />
      </div>

      {/* Latest signals */}
      {confidence.pulses_completed > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {confidence.latest_energy && (
            <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Energy</p>
              <p className="text-xs text-lcars-text/90 mt-0.5 capitalize">{confidence.latest_energy}</p>
            </div>
          )}
          {confidence.latest_mood && (
            <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Mood</p>
              <p className="text-xs text-lcars-text/90 mt-0.5 capitalize">{confidence.latest_mood}</p>
            </div>
          )}
          {confidence.latest_stress && (
            <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
              <p className="text-[9px] uppercase tracking-wider text-lcars-muted">Stress</p>
              <p className="text-xs text-lcars-text/90 mt-0.5 capitalize">{confidence.latest_stress}</p>
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
