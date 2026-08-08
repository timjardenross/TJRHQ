// WORKBENCHES IS NOW THE HOME PAGE (after login).
//
// Per MSN-0350/EOS redesign: after authentication, users land on this
// workbench hub instead of a static Home screen. Every experience is
// reachable from here as a direct tile, emphasizing choice and deliberate
// navigation over passive info-pushing.
//
// This page replaces the previous Home (HomeScreen) per design decision
// 2026-07-18. Root redirect now goes to /workbenches instead of /home.
'use client';

import Link from 'next/link';
import { Card, BackLink } from '@/components/ui';

interface Tile {
  href: string;
  title: string;
  description: string;
}

const TILES: Tile[] = [
  {
    href: '/captains-chair-workbench',
    title: 'Captain\'s Chair',
    description: 'Operational dashboard — recovery posture, mission overview, alerts, and intelligence at a glance.',
  },
  {
    href: '/intelligence-workbench',
    title: 'Technical OSINT Workbench',
    description: 'Cyber, infrastructure, and regulatory signal intelligence — source reliability, confidence scoring, and threat escalation.',
  },
  {
    href: '/health-osint',
    title: 'Health OSINT Workbench',
    description: 'Clinical trial and performance-research intelligence — source reliability, study confidence, and safety escalation.',
  },
  // Communications Workbench (Signals/Pipeline/Portfolio) removed from this
  // home list 2026-08 per explicit decision — Content Workbench now covers
  // capture through publish-submission end to end, superseding it as the
  // day-to-day surface. The route itself (/comms-workbench) is untouched
  // and still reachable directly — its Portfolio tab (published items) has
  // no equivalent here yet, so nothing there was deleted, just unlisted.
  //
  // Mission Workbench was delisted the same day, same reasoning — the
  // route (/mission-workbench) is untouched, just unlisted.
  {
    href: '/content-workbench',
    title: 'Content Workbench',
    description: 'Capture, research, draft, proof, and submit comms content for publish approval end-to-end - one QA-gated pipeline, Captain approval still required in Decide.',
  },
  {
    href: '/human-systems-workbench',
    title: 'Human Systems Workbench',
    description: 'Recovery posture, medical tracking, and physical readiness in one collection - live from the recovery-pulse signal.',
  },
  {
    href: '/advisory-workbench',
    title: 'Advisory Workbench',
    description: 'Consult officer advisors, convene the strategic Board, and hear distinguished perspectives - one advisory brain across surfaces.',
  },
  // Capture Workbench and Knowledge Workbench delisted 2026-08 per explicit
  // decision — routes (/capture-workbench, /knowledge-workbench) untouched,
  // still reachable directly, just unlisted here.
];

export default function Workbenches() {
  return (
    <div className="min-h-[100dvh] bg-wb-bg font-sans text-wb-ink antialiased">
      <main className="mx-auto max-w-4xl px-6 py-10">
        <h1 className="mb-1 font-serif text-2xl text-wb-ink">Welcome</h1>
        <p className="mb-8 text-[13px] text-wb-ink2">
          Choose a workbench or surface to navigate to. Every real experience is reachable from here.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          {TILES.map((t) => (
            <Link key={t.href} href={t.href} className="block focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep rounded-lg">
              <Card className="h-full transition hover:-translate-y-px hover:border-wb-sage-deep">
                <h2 className="mb-1.5 font-serif text-[16px] text-wb-ink">{t.title}</h2>
                <p className="text-[13px] text-wb-ink2">{t.description}</p>
              </Card>
            </Link>
          ))}
        </div>
      </main>
    </div>
  );
}
