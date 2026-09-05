'use client';

// Needs You (MSN-0364) — replaces the 3 CountTiles + Live Alerts list with
// a real decision queue. Priority-ordered per captainsChairSynthesis.ts's
// sortNeedsYou (urgency != severity, brief §7). Empty state is enforced
// strictly — see mission doc §10's locked decision — never padded to avoid
// looking empty.

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { stateToneClasses } from '@/lib/departments';
import type { NeedsYouItem } from '@/lib/captainsChairSynthesis';

const KIND_TONE: Record<NeedsYouItem['kind'], 'crit' | 'warn' | 'info'> = {
  safety: 'crit',
  time_critical: 'crit',
  blocker: 'warn',
  approval: 'warn',
  review: 'info',
  triage: 'info',
};

const KIND_LABEL: Record<NeedsYouItem['kind'], string> = {
  safety: 'Safety',
  time_critical: 'Time-Critical',
  blocker: 'Blocker',
  approval: 'Decide',
  review: 'Review',
  triage: 'Triage',
};

function NeedsYouRow({ item }: { item: NeedsYouItem }) {
  const c = stateToneClasses(KIND_TONE[item.kind]);
  return (
    <li className={`rounded-lg border ${c.border} ${c.bg} p-3`}>
      <p className={`text-[10px] font-semibold uppercase tracking-wider ${c.text}`}>{KIND_LABEL[item.kind]}</p>
      <p className="mt-0.5 text-sm font-semibold text-wb-ink">{item.title}</p>
      <p className="mt-0.5 text-xs text-wb-ink2">{item.detail}</p>
      <Link href={item.href} className="mt-1.5 inline-block text-[11px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
        {item.actionLabel} →
      </Link>
    </li>
  );
}

export function NeedsYou({ items, loading, errors }: { items: NeedsYouItem[]; loading: boolean; errors: string[] }) {
  const decisions = items.filter((i) => i.kind === 'approval' || i.kind === 'safety' || i.kind === 'time_critical').length;
  const reviews = items.filter((i) => i.kind === 'review' || i.kind === 'blocker').length;

  return (
    <WorkbenchPanel
      title="Needs You"
      eyebrow={items.length > 0 ? `${decisions ? `${decisions} decision${decisions === 1 ? '' : 's'}` : ''}${decisions && reviews ? ' · ' : ''}${reviews ? `${reviews} review${reviews === 1 ? '' : 's'}` : ''}` || undefined : undefined}
    >
      {loading ? (
        <p className="text-sm text-wb-ink2 animate-pulse">Checking…</p>
      ) : items.length === 0 ? (
        <p className="text-sm font-medium text-wb-ink2">✓ Nothing needs you right now.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (<NeedsYouRow key={item.id} item={item} />))}
        </ul>
      )}
      {errors.length > 0 && (
        <p className="mt-3 text-[10px] text-wb-ink2">Unavailable right now: {errors.join(', ')}.</p>
      )}
    </WorkbenchPanel>
  );
}
