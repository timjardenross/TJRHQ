'use client';

// Canonical domain/tab switch for *-workbench pages. Consolidated 2026-07-18
// (WORKBENCH-REVIEW.md H9/H12): 5 workbenches forked a role="tablist" version
// of this (identical except the domain list + aria-label), comms-workbench
// had its own role="radiogroup" version with NO keyboard handler at all (a
// real WCAG regression - role="radio" requires arrow-key navigation per the
// ARIA spec, this had none), and intelligence-workbench had a THIRD, even
// less accessible pattern - plain buttons with no role/aria-selected
// attributes whatsoever.
//
// This implementation is a real WAI-ARIA APG tablist: roving tabindex (only
// the active tab is in the natural Tab order; arrow keys move focus AND
// selection between the others) plus Home/End to jump to the first/last tab.
// None of the 7 prior implementations had this - the 5 "tablist" ones only
// had the ARIA attributes, not the keyboard behaviour those attributes
// promise a screen-reader/keyboard user.
import { useRef } from 'react';

export interface DomainToggleOption<T extends string> {
  key: T;
  label: string;
  /** Optional trailing badge, e.g. a pending-count (capture-workbench's own use). */
  badge?: string | number;
}

export function DomainToggle<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
}: {
  value: T;
  onChange: (key: T) => void;
  options: DomainToggleOption<T>[];
  ariaLabel: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  function focusTabAt(index: number) {
    const buttons = containerRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    const target = buttons?.[index];
    target?.focus();
    if (target) onChange(options[index].key);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const currentIndex = options.findIndex((o) => o.key === value);
    if (currentIndex === -1) return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      focusTabAt((currentIndex + 1) % options.length);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      focusTabAt((currentIndex - 1 + options.length) % options.length);
    } else if (e.key === 'Home') {
      e.preventDefault();
      focusTabAt(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      focusTabAt(options.length - 1);
    }
  }

  return (
    <div
      ref={containerRef}
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className="flex gap-1 rounded-md border border-wb-line bg-wb-surface px-1.5 py-1"
    >
      {options.map((o) => {
        const active = value === o.key;
        return (
          <button
            key={o.key}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(o.key)}
            className={`rounded px-3 py-1.5 text-[13px] font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep ${
              active ? 'bg-wb-sage-deep text-white' : 'text-wb-ink2 hover:bg-wb-line'
            }`}
          >
            {o.label}
            {o.badge != null && o.badge !== '' && o.badge !== 0 && (
              <span className={`ml-1 text-[11px] ${active ? 'text-white/80' : 'text-wb-ink2'}`}>{o.badge}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
