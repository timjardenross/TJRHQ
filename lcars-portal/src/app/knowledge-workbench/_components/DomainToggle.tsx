'use client';

import type { Domain } from './types';

const DOMAINS: { key: Domain; label: string }[] = [
  { key: 'memory', label: 'Memory' },
  { key: 'library', label: 'Library' },
];

/** Two-way domain switch for Memory | Library. Mirrors the Intelligence Workbench
 *  toggle; keyboard navigable with role=tablist semantics for WCAG 2.1 AA. */
export function DomainToggle({ domain, onChange }: { domain: Domain; onChange: (d: Domain) => void }) {
  return (
    <div role="tablist" aria-label="Knowledge domain" className="flex gap-1 rounded-md border border-wb-line bg-wb-surface px-1.5 py-1">
      {DOMAINS.map((d) => {
        const active = domain === d.key;
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
          </button>
        );
      })}
    </div>
  );
}
