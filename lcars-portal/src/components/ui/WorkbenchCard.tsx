import Link from 'next/link';
import type { WorkbenchEntry } from '@/lib/workbenches';

// Adaptive Themes + Home/Workbench Redesign mission (2026-09-05), §7 —
// icon-bearing, whole-card-clickable workbench tile. Wraps the plain <Card>
// pattern rather than forking it (no new border/surface/radius system).
export function WorkbenchCard({ entry }: { entry: WorkbenchEntry }) {
  const Icon = entry.icon;
  return (
    <Link
      href={entry.href}
      className="group flex h-full flex-col gap-3 rounded-lg border border-wb-line bg-wb-surface p-6 shadow-sm transition hover:-translate-y-px hover:border-wb-sage-deep hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
    >
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-wb-sage-deep/10 text-wb-sage-deep">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <span className="font-serif text-[16px] text-wb-ink">{entry.title}</span>
      <span className="text-[13px] text-wb-ink2">{entry.description}</span>
    </Link>
  );
}
