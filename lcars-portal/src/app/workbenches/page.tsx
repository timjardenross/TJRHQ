// THE WORKBENCH DIRECTORY — every real destination in HQ, one tap away.
//
// Per MSN-0350/EOS redesign this used to be true literally: root '/'
// redirected here. That changed 2026-09-05 (see app/page.tsx's own header
// comment) — the front door is /hub now, this directory is one tap further
// in (the WorkbenchShell logo, visible on every workbench). Mission 7
// §16/§35: this file's own comment above kept claiming home-page status for
// two weeks after that redirect moved, exactly the stale-doc drift this
// codebase's other comments warn about (see the Content Workbench
// description example two paragraphs down) — corrected here, not just
// worked around.
//
// Still the one complete, unfiltered list of every live workbench — Hub
// deliberately doesn't try to be this (mission §6/§8's "not a workbench
// browser"), so this page remains the answer to "show me everything."
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

import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { NumberOne, QuickCapture, Sidebar, ThemeSelector, WorkbenchCard } from '@/components/ui';
import { MobileCommandBar } from '@/components/MobileCommandBar';
import { LIVE_WORKBENCHES, WORKBENCH_GROUP_META, type WorkbenchGroup } from '@/lib/workbenches';
import { useTheme, THEME_TAGLINE } from '@/lib/theme';

const GROUP_ORDER = Object.keys(WORKBENCH_GROUP_META) as WorkbenchGroup[];

export default function Workbenches() {
  const [theme] = useTheme();
  const [query, setQuery] = useState('');

  // Mission 7 §16: a flat 19-tile grid with no structure was one long
  // unlabelled scroll on mobile and gave a Captain scanning for "the health
  // one" nothing but title text to go on. Grouping + search doesn't remove
  // the complete directory (still available, still every real destination)
  // — it just makes scanning it faster. Search flattens to a single ranked
  // list; with no query, the grouped view is a lighter first read.
  const q = query.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!q) return LIVE_WORKBENCHES;
    return LIVE_WORKBENCHES.filter(
      (e) => e.title.toLowerCase().includes(q) || e.description.toLowerCase().includes(q),
    );
  }, [q]);

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
            <p className="mb-6 text-[13px] italic text-wb-sage-deep">{THEME_TAGLINE[theme]}</p>

            <div className="relative mb-8 max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-wb-ink2" aria-hidden />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search workbenches…"
                aria-label="Search workbenches"
                className="w-full rounded-md border border-wb-line bg-wb-surface py-2 pl-9 pr-3 text-[13px] text-wb-ink placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
              />
            </div>

            {q ? (
              filtered.length === 0 ? (
                <p className="text-sm text-wb-ink2">Nothing matches &ldquo;{query}&rdquo;.</p>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {filtered.map((entry) => (
                    <WorkbenchCard key={entry.href} entry={entry} />
                  ))}
                </div>
              )
            ) : (
              <div className="space-y-8">
                {GROUP_ORDER.map((group) => {
                  const entries = LIVE_WORKBENCHES.filter((e) => e.group === group);
                  if (entries.length === 0) return null;
                  const meta = WORKBENCH_GROUP_META[group];
                  return (
                    <section key={group} aria-label={meta.label}>
                      <h2 className="mb-0.5 text-[12px] font-semibold uppercase tracking-wider text-wb-ink">
                        {meta.label}
                      </h2>
                      <p className="mb-3 text-[12px] text-wb-ink2">{meta.hint}</p>
                      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                        {entries.map((entry) => (
                          <WorkbenchCard key={entry.href} entry={entry} />
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
            )}
          </main>
        </div>
      </div>
      <QuickCapture />
      <NumberOne />
      <MobileCommandBar />
    </div>
  );
}
