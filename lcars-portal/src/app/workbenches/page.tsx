// WORKBENCHES IS THE HOME PAGE (after login).
//
// Per MSN-0350/EOS redesign, then confirmed and made literally true by the
// 2026-08 UX review: root '/' redirects here (see app/page.tsx), and the
// prior /home "needs attention" triage feed is retired (see
// home/page.tsx) — this directory of direct tiles is the one canonical
// landing surface, not an alternative to something else.
//
// Tile content now comes from lib/workbenches.ts's LIVE_WORKBENCHES,
// shared with WorkbenchShell's persistent switcher, so the two lists
// can't drift the way this file's own local array once did (its Content
// Workbench description kept describing a "Captain approval in Decide"
// step for weeks after that step was removed from the actual pipeline).
'use client';

import Link from 'next/link';
import { Card, QuickCapture } from '@/components/ui';
import { LIVE_WORKBENCHES } from '@/lib/workbenches';

export default function Workbenches() {
  return (
    <div className="min-h-[100dvh] bg-wb-bg font-sans text-wb-ink antialiased">
      <main className="mx-auto max-w-4xl px-6 py-10">
        <h1 className="mb-1 font-serif text-2xl text-wb-ink">Welcome</h1>
        <p className="mb-8 text-[13px] text-wb-ink2">
          Choose a workbench or surface to navigate to. Every real experience is reachable from here.
        </p>
<<<<<<< HEAD
        <div className="grid gap-4 sm:grid-cols-2">
=======
        {/* 2026-08-09 mobile/iPad review (P3): stayed 2-col from sm all the
            way through desktop, never using iPad landscape/desktop's extra
            width. lg:grid-cols-3 only kicks in at 1024px+, so mobile/iPad
            portrait behavior (1-col below sm, 2-col sm-lg) is unchanged. */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
>>>>>>> 3f9972f3d831aafb30298d1ef6b714751063906b
          {LIVE_WORKBENCHES.map((t) => (
            <Link key={t.href} href={t.href} className="block focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep rounded-lg">
              <Card className="h-full transition hover:-translate-y-px hover:border-wb-sage-deep">
                <h2 className="mb-1.5 font-serif text-[16px] text-wb-ink">{t.title}</h2>
                <p className="text-[13px] text-wb-ink2">{t.description}</p>
              </Card>
            </Link>
          ))}
        </div>
      </main>
      <QuickCapture />
    </div>
  );
}
