'use client';

import { useEffect, useState, type ReactNode } from 'react';

/** Progressive disclosure (VNext consolidation spec §25/§34): "collapsible
 *  detail sections below the first six items" on mobile, "avoid presenting
 *  all 30-day metrics above the fold." Defaults open on desktop (matches
 *  the doc's own desktop ASCII layout, which shows everything expanded) and
 *  closed on a mobile-width viewport at mount — a user can always toggle
 *  either way afterward. Client-only viewport check (matchMedia), not a
 *  CSS-only trick, since <details open> can't vary its default by
 *  breakpoint. */
const MOBILE_BREAKPOINT = '(max-width: 639px)';

export function CollapsibleSection({ title, children, className = '' }: { title: string; children: ReactNode; className?: string }) {
  const [open, setOpen] = useState(true);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    setOpen(!window.matchMedia(MOBILE_BREAKPOINT).matches);
  }, []);

  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      className={`rounded-lg border border-wb-line bg-wb-surface ${className}`}
    >
      <summary className="cursor-pointer list-none rounded-lg p-6 pb-3 font-serif text-lg text-wb-ink marker:content-none [&::-webkit-details-marker]:hidden focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
        <span className="flex items-center justify-between">
          {title}
          <span className="text-[11px] font-sans font-normal uppercase tracking-wide text-wb-ink2">{open ? 'Hide' : 'Show'}</span>
        </span>
      </summary>
      <div className="border-t border-wb-line px-6 pb-6 pt-3">{children}</div>
    </details>
  );
}
