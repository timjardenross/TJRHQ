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
  const contextualHref = `${item.href}${item.href.includes('?') ? '&' : '?'}from=captains-chair&item=${encodeURIComponent(item.id)}`;
  const contextualHelpHref = item.helpMeStartHref
    ? `${item.helpMeStartHref}${item.helpMeStartHref.includes('?') ? '&' : '?'}from=captains-chair&item=${encodeURIComponent(item.id)}`
    : null;
  return (
    <li className={`rounded-lg border ${c.border} ${c.bg} p-3`}>
      <p className={`text-[10px] font-semibold uppercase tracking-wider ${c.text}`}>{KIND_LABEL[item.kind]}</p>
      <p className="mt-0.5 text-sm font-semibold text-wb-ink">{item.title}</p>
      <p className="mt-0.5 text-xs text-wb-ink2">{item.detail}</p>
      {/* Mission 7 §22/§30: matches Hub's own Needs You action treatment
          (same items, same actionLabel field — the two surfaces must not
          just agree on content, but read consistently) — a visible button,
          not an easy-to-miss trailing text link. */}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Link
          href={contextualHref}
          className="inline-block rounded-md bg-wb-sage-deep px-2.5 py-1 text-[11px] font-semibold text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        >
          {item.actionLabel}
        </Link>
        {/* Mission 7 item 2: straight into Unstick Me for this same task —
            Captain's choice alongside the plain Do view, not a second
            engine deciding which tasks need it. */}
        {contextualHelpHref && (
          <Link
            href={contextualHelpHref}
            className="inline-block rounded-md border border-wb-line px-2.5 py-1 text-[11px] font-semibold text-wb-ink2 hover:border-wb-sage-deep hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          >
            Help me start
          </Link>
        )}
      </div>
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
