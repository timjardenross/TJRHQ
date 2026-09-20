import Link from 'next/link';

// Retired 2026-09-19 (Mission 7 adversarial pass, §35). This was the
// pre-redesign, 776-line LCARS-styled Medical dashboard (Overview / Pulse /
// Check-In / Trends tabs, old LCARSPanel/StatusBadge components) — fully
// superseded by human-systems-workbench's 2026-09-06 NOW/WHAT
// HELPS/PATTERNS/TRENDS redesign, and confirmed to have zero live inbound
// links anywhere in the app (this route only ever reached by typing the
// URL directly — `lib/nav.ts`'s VALID_NAV_HREFS listed it for the
// build-time type check, not because anything actually linked here).
// /medical/check-in and /medical/log-activity already redirect to their
// human-systems-workbench equivalents; this page is the one piece of that
// cluster that was still rendering the old page in full instead of
// forwarding, so a bookmark or stray link would have shown genuinely stale
// UI rather than an honest notice.
//
// /medical/log-weight is retired too (Mission 7 deferred-register item 12,
// closed): its real 30-day weight-trend history is now ported into
// human-systems-workbench/weight, same data (`weight_logs`, manual entry
// still retired per the 2026-08-10 Recovery Pulse directive), just
// reshelled onto WorkbenchShell/wb-* tokens. No more redirect hop needed.
export default function MedicalPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-sans text-lg font-bold uppercase tracking-wider text-wb-ink">
        Medical Bay
      </h1>
      <p className="mt-3 text-[13px] leading-relaxed text-wb-ink2">
        This page moved.{' '}
        <Link href="/human-systems-workbench" className="text-wb-sage-deep underline hover:no-underline">
          Go to Human Systems →
        </Link>
      </p>
      <ul className="mt-4 space-y-2 text-[13px] text-wb-ink2">
        <li>
          Daily check-in:{' '}
          <Link href="/human-systems-workbench/medical/check-in" className="text-wb-sage-deep underline hover:no-underline">
            Human Systems → Check-In
          </Link>
        </li>
        <li>
          Pulse:{' '}
          <Link href="/human-systems-workbench/medical/pulse" className="text-wb-sage-deep underline hover:no-underline">
            Human Systems → Pulse
          </Link>
        </li>
        <li>
          Trends:{' '}
          <Link href="/human-systems-workbench/trends" className="text-wb-sage-deep underline hover:no-underline">
            Human Systems → Trends
          </Link>
        </li>
        <li>
          Weight history (30-day trend, manual entry retired):{' '}
          <Link href="/human-systems-workbench/weight" className="text-wb-sage-deep underline hover:no-underline">
            Human Systems → Weight
          </Link>
        </li>
      </ul>
    </div>
  );
}
