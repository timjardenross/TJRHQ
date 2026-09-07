// WORKBENCHES IS THE HOME PAGE (after login).
//
// Per MSN-0350/EOS redesign, then confirmed and made literally true by the
// 2026-08 UX review: root '/' redirects here (see app/page.tsx), and the
// prior /home "needs attention" triage feed is retired (see
// home/page.tsx) — this directory of direct tiles is the one canonical
// landing surface, not an alternative to something else.
//
// Tile content comes from lib/workbenches.ts's LIVE_WORKBENCHES, shared with
// WorkbenchShell's persistent switcher, so the two lists can't drift the
// way this file's own local array once did (its Content Workbench
// description kept describing a "Captain approval in Decide" step for
// weeks after that step was removed from the actual pipeline).
//
// Redesigned 2026-09-05 (Adaptive Themes + Home/Workbench Redesign
// mission, §7-9) — welcome header + theme-specific tagline, icon-bearing
// WorkbenchCard grid, global Sidebar (this page doesn't use WorkbenchShell
// itself — it's the one page that predates it — so it renders Sidebar
// directly, matching the Captain's "global sidebar everywhere" call rather
// than being the one page left out of it). Every existing route/position
// unchanged; this only touches how they're presented.
'use client';

import { QuickCapture, Sidebar, ThemeSelector, WorkbenchCard } from '@/components/ui';
import { MobileCommandBar } from '@/components/MobileCommandBar';
import { LIVE_WORKBENCHES } from '@/lib/workbenches';
import { useTheme, THEME_TAGLINE } from '@/lib/theme';

export default function Workbenches() {
  const [theme] = useTheme();

  return (
    <div className="min-h-[100dvh] bg-wb-bg font-sans text-wb-ink antialiased">
      <div className="flex">
        <Sidebar />
        <div className="min-w-0 flex-1">
          <header className="border-b border-wb-line bg-wb-bg/80 px-6 py-4 backdrop-blur">
            <div className="mx-auto flex max-w-6xl items-center justify-end">
              <ThemeSelector />
            </div>
          </header>
          <main className="mx-auto max-w-6xl px-6 py-10">
            <h1 className="mb-1 font-serif text-2xl text-wb-ink">Welcome, TJR</h1>
            <p className="mb-1 text-[13px] text-wb-ink2">
              Choose a workbench or surface to navigate to. Every real experience is reachable from here.
            </p>
            <p className="mb-8 text-[13px] italic text-wb-sage-deep">{THEME_TAGLINE[theme]}</p>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {LIVE_WORKBENCHES.map((entry) => (
                <WorkbenchCard key={entry.href} entry={entry} />
              ))}
            </div>
          </main>
        </div>
      </div>
      <QuickCapture />
      <MobileCommandBar />
    </div>
  );
}
