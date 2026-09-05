'use client';

// Extracted from captains-chair-workbench/page.tsx 2026-09-05 so the LifeOS
// Hub (/hub) can render the same situation strip without duplicating markup.

import Link from 'next/link';
import { stateToneClasses } from '@/lib/departments';
import type { StateTone } from '@/lib/types';

export function SituationBadge({
  label,
  value,
  tone,
  sublabel,
  href,
}: {
  label: string;
  value: string;
  tone: StateTone;
  sublabel?: string;
  href?: string;
}) {
  const c = stateToneClasses(tone);
  const content = (
    <>
      <p className="text-[10px] uppercase tracking-wider text-wb-ink2">{label}</p>
      <p className={`mt-0.5 text-lg font-bold ${c.text}`}>{value}</p>
      {sublabel && <p className="mt-0.5 text-xs text-wb-ink/80">{sublabel}</p>}
    </>
  );
  const className = `flex-1 rounded-lg border ${c.border} ${c.bg} px-4 py-3`;
  if (href) {
    return (
      <Link href={href} className={`${className} block transition-colors hover:border-wb-sage-deep/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep`}>
        {content}
      </Link>
    );
  }
  return <div className={className}>{content}</div>;
}
