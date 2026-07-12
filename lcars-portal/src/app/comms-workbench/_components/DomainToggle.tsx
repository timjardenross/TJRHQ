'use client';

import type { Domain } from './shared';

const OPTIONS: { key: Domain; label: string }[] = [
  { key: 'both', label: 'Both' },
  { key: 'health', label: 'Health' },
  { key: 'operational', label: 'Operational' },
];

export function DomainToggle({ domain, onChange }: { domain: Domain; onChange: (d: Domain) => void }) {
  return (
    <div role="radiogroup" aria-label="Filter by domain" className="flex gap-1 rounded-md border border-wb-line bg-wb-surface p-1">
      {OPTIONS.map(opt => (
        <button
          key={opt.key}
          type="button"
          role="radio"
          aria-checked={domain === opt.key}
          onClick={() => onChange(opt.key)}
          className={`rounded px-3 py-1 text-[12px] transition-colors focus-visible:outline
            focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${
            domain === opt.key
              ? 'bg-wb-sage-deep text-white'
              : 'text-wb-ink2 hover:text-wb-ink'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
