import type { ReactNode } from 'react';
import type { DepartmentKey } from '@/lib/types';
import { DEPARTMENTS } from '@/lib/departments';

/**
 * LCARSPanel — the base content container. Every section sits in one of these.
 * `accent` colour-codes the title rail by department.
 */
export interface LCARSPanelProps {
  title: string;
  accent?: DepartmentKey;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function LCARSPanel({
  title,
  accent = 'command',
  eyebrow,
  actions,
  children,
  className = ''
}: LCARSPanelProps) {
  const dept = DEPARTMENTS[accent];
  return (
    <section
      className={`overflow-hidden rounded-lcars border border-edge bg-panel/60 ${className}`}
    >
      <div className="flex items-center gap-3 border-b border-edge px-4 py-3">
        <span className={`h-6 w-2 rounded-full ${dept.bg}`} aria-hidden />
        <div className="flex flex-1 flex-col">
          {eyebrow && (
            <span className="text-[11px] uppercase tracking-[0.25em] text-lcars-muted">
              {eyebrow}
            </span>
          )}
          <h2 className={`text-base font-bold ${dept.text}`}>{title}</h2>
        </div>
        {actions}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}
