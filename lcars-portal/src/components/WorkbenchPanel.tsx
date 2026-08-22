import type { ReactNode } from 'react';

/**
 * WorkbenchPanel — the wb-* system's card container. Sibling of LCARSPanel,
 * not a themed variant of it: *-workbench routes should reference zero
 * components rooted in the legacy LCARS system, so this is its own small
 * file rather than a `variant` prop on LCARSPanel (design-audit finding —
 * Captain's Chair was importing LCARSPanel/StatusBadge/etc, which meant a
 * future edit to those files' default styling could silently reintroduce
 * LCARS chrome into a wb-branded page).
 */
export interface WorkbenchPanelProps {
  title: string;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function WorkbenchPanel({
  title,
  eyebrow,
  actions,
  children,
  className = '',
}: WorkbenchPanelProps) {
  return (
    <section
      className={`overflow-hidden rounded-lg border border-wb-line bg-wb-surface shadow-sm ${className}`}
    >
      <div className="flex items-center gap-3 border-b border-wb-line px-4 py-3.5">
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
