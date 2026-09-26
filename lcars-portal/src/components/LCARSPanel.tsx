import type { ReactNode } from 'react';
import type { DepartmentKey } from '@/lib/types';

/**
 * LCARSPanel — the base content container. Every section sits in one of these.
 *
 * Real-Captain-walkthrough revision (2026-07-10): restyled on the real
 * public-site brand tokens (components/public/PublicShell.tsx), matching
 * HomeScreen.tsx's earlier redesign. `accent` is kept in the type signature
 * only - every call site across Advisory Council/Comms/Missions/etc. still
 * passes it, and this component being the single shared wrapper for all of
 * them is exactly why redesigning it here cascades everywhere at once
 * rather than needing dozens of call-site edits. It no longer drives any
 * colour: the new brand has one accent, not five decorative department
 * colours per panel.
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
  eyebrow,
  actions,
  children,
  className = ''
}: LCARSPanelProps) {
  return (
    <section
      className={`overflow-hidden rounded-xl border border-wb-line bg-wb-surface shadow-sm ${className}`}
    >
      <div className="flex items-center gap-3 border-b border-lcars-chrome-border-soft px-4 py-3.5">
        <div className="flex flex-1 flex-col">
          {eyebrow && (
            <span className="text-[11px] uppercase tracking-[0.2em] text-wb-ink2">
              {eyebrow}
            </span>
          )}
          <h2 className="text-base font-semibold text-wb-ink">{title}</h2>
        </div>
        {actions}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}
