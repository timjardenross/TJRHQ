import type { Department } from '@/lib/types';
import { DEPARTMENTS } from '@/lib/departments';
import { StatusBadge } from './StatusBadge';

/**
 * DepartmentCard — at-a-glance department readout used on the Captain's Chair
 * grid and the Engineering page.
 */
export interface DepartmentCardProps {
  department: Department;
}

export function DepartmentCard({ department }: DepartmentCardProps) {
  const theme = DEPARTMENTS[department.key];
  return (
    <article className="flex flex-col gap-3 rounded-xl border border-wb-line bg-wb-surface p-4">
      <div className="flex items-center gap-2">
        <span className={`h-8 w-8 rounded-lg ${theme.bg}`} aria-hidden />
        <div className="flex flex-1 flex-col">
          <h3 className={`text-sm font-bold ${theme.text}`}>{department.name}</h3>
          <span className="text-[11px] text-wb-ink2">{department.lead}</span>
        </div>
        <StatusBadge label={department.status} tone={department.tone} />
      </div>
      <p className="text-xs leading-relaxed text-wb-ink2">
        {department.summary}
      </p>
      <dl className="mt-auto grid grid-cols-2 gap-2">
        {department.metrics.map((m) => (
          <div
            key={m.label}
            className="rounded-md border border-wb-line bg-wb-bg px-2 py-1.5"
          >
            <dt className="text-[10px] uppercase tracking-wider text-wb-ink2">
              {m.label}
            </dt>
            <dd className={`lcars-readout ${theme.text}`}>{m.value}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}
