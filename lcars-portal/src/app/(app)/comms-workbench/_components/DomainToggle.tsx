'use client';

import type { Domain } from './shared';

const OPTIONS: { key: Domain; label: string }[] = [
  { key: 'both', label: 'Both' },
  { key: 'health', label: 'Health' },
  { key: 'operational', label: 'Operational' },
];

export function DomainToggle({ domain, onChange }: { domain: Domain; onChange: (d: Domain) => void }) {
  return (
    <div role="radiogroup" aria-label="Filter by domain" className="flex gap-1 rounded-lcars border border-[#d9e1f0] bg-white/20 p-1">
      {OPTIONS.map(opt => (
        <button
          key={opt.key}
          type="button"
          role="radio"
          aria-checked={domain === opt.key}
          onClick={() => onChange(opt.key)}
          className={`text-xs px-3 py-1 rounded transition-colors ${
            domain === opt.key
              ? 'bg-[#243b7a] text-white'
              : 'text-[#61718c] hover:text-[#18223a]'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
