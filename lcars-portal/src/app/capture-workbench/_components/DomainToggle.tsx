'use client';

import type { Domain } from './types';

const DOMAINS: { key: Domain; label: string }[] = [
  { key: 'capture', label: 'Capture' },
  { key: 'inbox', label: 'Inbox' },
];

/** Two-way domain switch. Mirrors the Human Systems / Advisory Workbench
 *  toggle; keyboard navigable with role=tablist semantics for WCAG 2.1 AA. */
export function DomainToggle({
  domain,
  onChange,
  pendingCount,
}: {
  domain: Domain;
  onChange: (d: Domain) => void;
  pendingCount?: number;
}) {
  return (
    <div role="tablist" aria-label="Capture domain" className="flex gap-1 rounded-md border border-wb-line bg-wb-surface px-1.5 py-1">
      {DOMAINS.map((d) => {
        const active = domain === d.key;
        const badge = d.key === 'inbox' && pendingCount && pendingCount > 0 ? ` ${pendingCount}` : '';
        return (
          <button
            key={d.key}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(d.key)}
            className={`rounded px-3 py-1.5 text-[13px] font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep ${
              active ? 'bg-wb-sage-deep text-white' : 'text-wb-ink2 hover:bg-wb-line'
            }`}
          >
            {d.label}
            {badge && <span className={`ml-1 text-[11px] ${active ? 'text-white/80' : 'text-wb-ink2'}`}>{badge}</span>}
          </button>
        );
      })}
    </div>
  );
}
