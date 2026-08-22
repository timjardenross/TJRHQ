import Link from 'next/link';

// Retired 2026-08-11 (Chief Engineer workbench-drift review + Captain
// direction: "captains-chair-workbench wins"). Before retiring, ported the
// 4 real capability gaps a parity check found onto captains-chair-workbench
// (Since Last Session, Captain's Timeline, Captain's Notebook, Department
// Row) and fixed a live confidence-percentage bug there (was rendering
// 8700% instead of 87%). Operational Picture and Operational Hygiene were
// NOT ported back — both were deliberately removed from the workbench page
// by an earlier "Captain's call" (commits a5ab2cc2, 64a2bdaf), and that
// decision stands.
//
// All 5 live surfaces that pointed at this route (lib/alerts.ts's
// capacity-critical wellness alert, HomeScreen.tsx, lib/nav.ts's
// VALID_NAV_HREFS, lib/preferences.ts's default favourites, and
// lib/public-site.ts's robots disallow list) were repointed to
// /captains-chair-workbench in the same pass.
//
// Kept as an honest "this page moved" notice rather than deleted outright,
// matching the /home, /captains-brief, and /comms retirement precedent.
export default function CaptainsChairPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-sans text-lg font-bold uppercase tracking-wider text-lcars-text">
        Captain&apos;s Chair
      </h1>
      <p className="mt-3 text-[13px] leading-relaxed text-wb-ink2">
        This page moved.{' '}
        <Link href="/captains-chair-workbench" className="text-wb-sage-deep underline hover:no-underline">
          Go to Captain&apos;s Chair →
        </Link>
      </p>
    </div>
  );
}
