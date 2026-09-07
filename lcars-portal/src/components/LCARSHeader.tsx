// Real-Captain-walkthrough revision (2026-07-10): restyled on the real
// public-site brand (components/public/PublicShell.tsx tokens), matching
// HomeScreen.tsx's earlier redesign, so the chrome every (app) page sits
// inside stops looking like a third, unrelated design system.
//
// Also removed condition/readinessPercent/missionStatus entirely - a
// repo-wide grep confirmed zero callers anywhere ever passed real values
// for any of the three; every page under (app) has been showing the
// hardcoded prop defaults ("94%", "GREEN", "CONDITION GREEN") as if they
// were real operational data, on every single page load. No real
// "operational readiness %" or "mission status" computation exists
// anywhere in this codebase to wire this to honestly, so - matching the
// same principle applied to Human Systems' fabricated 60/Moderate
// fallback this same session - the fix is removal, not a fake number
// swapped for an equally fake "No data" badge nobody asked to see on
// every page. Stardate stays: computeStardate() is real and deterministic.
//
// Settings Page Redesign mission §23: LCARSNav (the (app) group's own left
// rail) is xl:-only, same as *-workbench's Sidebar, but the (app) group has
// no WorkbenchShell equivalent adding a mobile fallback icon — so this
// header carries the one Settings link this route group has, at every
// width, rather than leaving it URL-only below xl.
import Link from 'next/link';
import { Settings } from 'lucide-react';

export interface LCARSHeaderProps {
  ship: string;
  registry: string;
  stardate: string;
  pageTitle?: string;
}

export function LCARSHeader({ ship, registry, stardate, pageTitle }: LCARSHeaderProps) {
  return (
    <header className="overflow-hidden rounded-[24px] border border-[#d9e1f0] bg-white/92 shadow-[0_12px_40px_rgba(23,32,51,0.06)]">
      <div className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between md:gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-9 w-9 shrink-0 rounded-xl bg-[#243b7a]" />
          <div className="min-w-0">
            {pageTitle && (
              <h1 className="text-lg font-semibold tracking-[-0.01em] text-[#18223a] truncate">
                {pageTitle}
              </h1>
            )}
            <p className="text-[13px] text-[#61718c] truncate">
              {ship} · {registry}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <div className="text-right">
            <p className="text-[10px] uppercase tracking-[0.2em] text-[#61718c]">Stardate</p>
            <p className="ml-2 font-semibold tabular-nums text-[#18223a]">{stardate}</p>
          </div>
          <Link
            href="/settings"
            aria-label="Settings"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-xl text-[#61718c] hover:bg-[#eef1f8] hover:text-[#18223a] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#243b7a]"
          >
            <Settings className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </div>
    </header>
  );
}
