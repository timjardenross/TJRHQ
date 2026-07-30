import { ReactNode } from 'react';

export type BadgeStatus = 'success' | 'warning' | 'error' | 'info' | 'neutral';

const STATUS_CLASSES: Record<BadgeStatus, string> = {
  success: 'bg-wb-ok/15 text-wb-ok-on',
  warning: 'bg-wb-warn/15 text-wb-warn-on',
  error: 'bg-wb-crit/15 text-wb-crit-on',
  info: 'bg-wb-sage/15 text-wb-sage-deep',
  neutral: 'bg-wb-line text-wb-ink2',
};

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
