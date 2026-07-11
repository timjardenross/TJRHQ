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

        <div className="flex items-center shrink-0 text-right">
          <p className="text-[10px] uppercase tracking-[0.2em] text-[#61718c]">Stardate</p>
          <p className="ml-2 font-semibold tabular-nums text-[#18223a]">{stardate}</p>
        </div>
      </div>
    </header>
  );
}
