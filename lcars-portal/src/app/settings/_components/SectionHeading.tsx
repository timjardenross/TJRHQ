import type { ReactNode } from 'react';

/** Mission §22 mockup: "Clear section heading / Short explanation" at the
 * top of every section's right-hand pane. */
export function SectionHeading({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return (
    <div className="mb-6">
      <h1 className="font-serif text-2xl text-wb-ink">{title}</h1>
      <p className="mt-1 text-[13px] text-wb-ink2">{description}</p>
      {children}
    </div>
  );
}

/** A single setting row: label + control + optional hint, laid out so a
 * long label never crowds the control (mission §26: usable at 200% zoom —
 * this wraps to a stacked layout on narrow widths via flex-wrap). */
export function SettingRow({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-wb-line py-4 last:border-b-0">
      <div className="min-w-0 flex-1 pr-4">
        <p className="text-[13px] font-medium text-wb-ink">{label}</p>
        {hint && <p className="mt-0.5 text-[12px] text-wb-ink2">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
