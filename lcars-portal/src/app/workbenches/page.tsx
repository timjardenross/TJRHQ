// Direct-URL only, deliberately not added to nav.ts or linked from Home.
//
// docs/EOS-CANONICAL-ARCHITECTURE-DECISIONS.md §5 (Canonical Navigation &
// Experience Model) found zero of 22 real investigation journeys began by
// browsing a menu, and explicitly rejects a persistent, browsable sidebar
// for exactly that reason - a standing link is itself a checking-habit cue.
// A tile grid of every workbench is the same shape as that rejected menu,
// so this page follows the one precedent already accepted for this
// situation instead: comms-workbench/page.tsx's own header comment says
// it is "Direct-URL only (not yet in nav) per COMMS-UI-REDESIGN-SPEC.md
// rollout plan" - i.e. an unlisted URL is the sanctioned way to make a
// build-phase surface reachable without promoting it into the platform's
// real navigation model. This page is that same pattern applied to "which
// workbenches exist right now", not a new navigation surface: bookmark the
// URL, it is not meant to be discovered by browsing.
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
    href: '/intelligence-workbench',
    title: 'Intelligence Workbench',
    description: 'Operational resilience signals and health intelligence, live ORI feed.',
  },
  {
    href: '/comms-workbench',
    title: 'Communications Workbench',
    description: 'Signals to opportunities, pipeline, and portfolio for comms content.',
  },
  {
    href: '/human-systems-workbench',
    title: 'Human Systems Workbench',
    description: 'Recovery posture, medical tracking, and physical readiness in one collection — live from the recovery-pulse signal.',
  },
  {
    href: '/advisory-workbench',
    title: 'Advisory Workbench',
    description: 'Consult officer advisors, convene the strategic Board, and hear distinguished perspectives — one advisory brain across surfaces.',
  },
  {
    href: '/capture-workbench',
    title: 'Capture Workbench',
    description: 'Capture anything in one box, then triage the inbox — classify, route, and promote, review-first. Live from every capture channel.',
  },
  {
    href: '/self-improvement-findings',
    title: 'Self-Improvement Findings',
    description: 'Findings, decisions, and audit trail from the self-improvement system.',
  },
];

export default function Workbenches() {
  return (
    <div className="min-h-[100dvh] bg-wb-bg font-sans text-wb-ink antialiased">
      <main className="mx-auto max-w-4xl px-6 py-10">
        <BackLink href="/home" label="Home" />
        <h1 className="mb-1 font-serif text-2xl text-wb-ink">Workbenches</h1>
        <p className="mb-8 text-[13px] text-wb-ink2">
          Direct links to build-phase surfaces not yet in Home&rsquo;s contextual flow.
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
