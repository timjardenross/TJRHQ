import Link from 'next/link';

// Retired 2026-09-19 (Mission 7 legacy-page sweep, §35). Confirmed zero
// live inbound links anywhere in the app. Unlike most of this sweep, this
// page carried clear internal evidence of already being stale rather than
// merely unlinked: its own hardcoded SCHEDULED_JOBS/DELIVERY_CHANNELS
// tables referenced things already retired elsewhere in the repo by name
// ("Slack — bot retired (MSN-0337)", three jobs marked "RETIRED (D-3C-04)"
// sitting next to ones still marked "Active") — a half-updated snapshot,
// not maintained documentation. Its ALERT_THRESHOLDS table (pain/mission-
// blocked/recovery-gap/approval-wait severity mappings) is presented as if
// describing live alerting logic with no evidence it still matches
// lib/alerts.ts's real computeAlerts() after the Mission 1-6 rebuild —
// kept nowhere else, so not ported (a stale copy of alerting rules is
// worse than none; if this needs documenting, it should be generated from
// or verified against the real computeAlerts() logic, not hand-authored
// here). "Is HQ's automation actually working" is HQ Status's real job
// now (agent-status-workbench) — interpreted platform health from live
// heartbeats, not a static table.
export default function AutomationCentrePage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-sans text-lg font-bold uppercase tracking-wider text-lcars-text">
        Automation Centre
      </h1>
      <p className="mt-3 text-[13px] leading-relaxed text-wb-ink2">
        This page moved.{' '}
        <Link href="/agent-status-workbench" className="text-wb-sage-deep underline hover:no-underline">
          Go to HQ Status →
        </Link>
      </p>
    </div>
  );
}
