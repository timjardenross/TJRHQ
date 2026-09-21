import Link from 'next/link';
import { DataAvailabilityNotice } from '@/components/DataAvailabilityNotice';

export interface WhatNeedsMeItem {
  id: string;
  title: string;
  detail?: string | null;
  href: string;
  actionLabel: string;
}

export function WhatNeedsMeNow({
  items,
  loading = false,
  errors = [],
  emptyLabel = 'Nothing needs action now.',
}: {
  items: WhatNeedsMeItem[];
  loading?: boolean;
  errors?: string[];
  emptyLabel?: string;
}) {
  const first = items[0];
  return (
    <section aria-labelledby="what-needs-me-now" className="rounded-lg border-2 border-wb-sage-deep/50 bg-wb-sage/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="what-needs-me-now" className="text-[11px] font-bold uppercase tracking-[0.18em] text-wb-sage-deep">What needs me now</h2>
          <p className="mt-1 text-sm font-semibold text-wb-ink">
            {loading ? 'Checking what needs you…' : items.length ? `${items.length} item${items.length === 1 ? '' : 's'} need a decision or next action.` : emptyLabel}
          </p>
        </div>
        {!loading && first && <Link href={first.href} className="inline-flex min-h-10 items-center rounded-md bg-wb-sage-deep px-3 py-2 text-xs font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">{first.actionLabel} →</Link>}
      </div>
      {!loading && first && <p className="mt-2 text-xs text-wb-ink2"><strong className="text-wb-ink">Next:</strong> {first.title}{first.detail ? ` — ${first.detail}` : ''}</p>}
      {errors.length > 0 && <DataAvailabilityNotice state="unavailable" sources={errors} className="mt-3" />}
    </section>
  );
}
