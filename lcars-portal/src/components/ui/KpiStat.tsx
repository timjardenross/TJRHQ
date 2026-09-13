import { ReactNode } from 'react';

export type KpiStatTone = 'ink' | 'ok' | 'warn' | 'crit';

const TONE_TEXT: Record<KpiStatTone, string> = {
  ink: 'text-wb-ink',
  ok: 'text-wb-ok-on',
  warn: 'text-wb-warn-on',
  crit: 'text-wb-crit-on',
};

export interface KpiStatProps {
  label: string;
  value: ReactNode;
  onClick?: () => void;
  tone?: KpiStatTone;
}

/**
 * KpiStat — a single plain-number-and-label KPI cell, shared by the
 * workbench KpiDashboard strips (previously copy-pasted per-workbench as a
 * local `Stat` function). Renders as a button when `onClick` is given.
 */
export function KpiStat({ label, value, onClick, tone = 'ink' }: KpiStatProps) {
  const body = (
    <>
      <div className={`font-serif text-2xl ${TONE_TEXT[tone]}`}>{value}</div>
      <div className="text-[11px] uppercase tracking-[0.14em] text-wb-ink2">{label}</div>
    </>
  );

  if (!onClick) return <div className="text-left">{body}</div>;

  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md text-left transition hover:opacity-70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
    >
      {body}
    </button>
  );
}

export interface KpiCardProps {
  label: string;
  value: string;
  sub?: string;
  badge?: ReactNode;
}

/**
 * KpiCard — a bordered KPI tile with an optional badge in place of the raw
 * value and an optional sub-line. For richer per-tile content (badges,
 * hint text) than KpiStat's plain number+label supports.
 */
export function KpiCard({ label, value, sub, badge }: KpiCardProps) {
  return (
    <div className="rounded-lg border border-wb-line bg-wb-surface p-4">
      <div className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">{label}</div>
      <div className="mt-1.5 flex items-center gap-2">
        {badge ?? <span className="font-serif text-[20px] leading-none text-wb-ink">{value}</span>}
      </div>
      {sub && <div className="mt-1 text-[12px] text-wb-ink2">{sub}</div>}
    </div>
  );
}
