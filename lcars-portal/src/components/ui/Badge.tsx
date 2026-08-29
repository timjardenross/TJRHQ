import { ReactNode } from 'react';
import { stateToneClasses } from '@/lib/departments';
import type { StateTone } from '@/lib/types';

// BadgeStatus is Badge's public prop contract (10+ call sites across the
// app) and stays as-is — only the internal color source changed, 2026-08-29
// (docs/Severity-Vocab-Canonicalization-Plan-2026-08-29.md): this used to
// carry its own bg-wb-*/text-wb-*-on table, now it's a thin adapter onto
// the canonical stateToneClasses/StateTone system, so Badge no longer
// competes with it as a second severity vocabulary.
export type BadgeStatus = 'success' | 'warning' | 'error' | 'info' | 'neutral';

const BADGE_STATUS_TONE: Record<BadgeStatus, StateTone> = {
  success: 'ok',
  warning: 'warn',
  error: 'crit',
  info: 'info',
  neutral: 'unknown',
};

export const STATUS_CLASSES: Record<BadgeStatus, string> = Object.fromEntries(
  (Object.keys(BADGE_STATUS_TONE) as BadgeStatus[]).map((status) => {
    const t = stateToneClasses(BADGE_STATUS_TONE[status]);
    return [status, `${t.bg} ${t.on}`];
  }),
) as Record<BadgeStatus, string>;

const TONE_BADGE_STATUS: Record<StateTone, BadgeStatus> = {
  ok: 'success',
  warn: 'warning',
  crit: 'error',
  info: 'info',
  unknown: 'neutral',
};

/** Reverse of BADGE_STATUS_TONE — lets a page compute a canonical StateTone
 *  via one of departments.ts's severity adapters, then still render it
 *  through <Badge>. */
export function toneToStatus(tone: StateTone): BadgeStatus {
  return TONE_BADGE_STATUS[tone];
}

/** Maps RED/AMBER/GREEN/HIGH/MEDIUM/LOW risk values (workbench convention) to a status. */
export function riskToStatus(risk: string | null | undefined): BadgeStatus {
  const v = (risk ?? '').toUpperCase();
  if (v === 'RED' || v === 'HIGH') return 'error';
  if (v === 'AMBER' || v === 'MEDIUM') return 'warning';
  if (v === 'GREEN' || v === 'LOW') return 'success';
  return 'neutral';
}

export interface BadgeProps {
  status?: BadgeStatus;
  children: ReactNode;
  className?: string;
}

/** TJR Design System — generalized from intelligence-workbench's RiskPill/riskClass. */
export function Badge({ status = 'neutral', children, className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${STATUS_CLASSES[status]} ${className}`}
    >
      {children}
    </span>
  );
}
