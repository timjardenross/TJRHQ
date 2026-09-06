import Link from 'next/link';
import { WorkbenchShell, Card } from '@/components/ui';

// Human Systems redesign Phase 10 (2026-09-06) — Recovery Brief consolidation.
//
// This page used to be a full, real content page (RecoveryConfidenceSection
// ported from RecoveryConfidencePanel.tsx, WellnessIntelligenceSection
// ported from WellnessInsightPanel.tsx, a posture/capacity hero fed by
// useROSData()). Two things made it worth retiring rather than keeping:
//
// 1. RecoveryConfidenceSection depended on useRecoveryConfidence(), which
//    queried recovery_confidence_today — a view over the RETIRED
//    recovery_pulses table (superseded by capacity_checkins, 2026-08-22).
//    That hook is now fixed to read the live capacity_checkins_today view
//    instead (see src/lib/useRecoveryConfidence.ts), but its whole 4-slot
//    pulse/confidence-score UI model has no real equivalent under the
//    free-form check-in model any more.
// 2. Everything this page was actually FOR — "what does my system need
//    today, nervous-system-first" — is the exact framing the NOW tab on
//    the main Human Systems Workbench page was built around (Capacity
//    Today, What's Contributing, What May Help Now, Recovery Trajectory).
//    The one genuinely distinct, non-duplicate piece this page carried —
//    "Wins This Week" from health_insights — has been ported into the
//    PATTERNS tab's "System Learning" section (see
//    SystemLearningSection in _components/RecoveryView.tsx) so it isn't
//    lost by this consolidation.
//
// Kept as a real route (not deleted) rather than a hard redirect() —
// several live callers still link here (src/lib/alerts.ts's recovery-debt
// escalation, the top-level /recovery-brief legacy alias, nav/public-site
// route lists) and a silent instant redirect gives a visiting Captain no
// chance to see why the page moved. A hard redirect() is used for the
// (app)/recovery-brief and (app)/medical/pulse legacy aliases, which never
// carried unique content of their own — this page did, so it explains
// itself instead.

export default function RecoveryBriefPage() {
  return (
    <WorkbenchShell
      title="Recovery Brief"
      eyebrow="Human Systems"
      tagline="USS TJR · This page has moved into Human Systems — NOW"
      back={{ href: '/human-systems-workbench', label: 'Human Systems' }}
    >
      <Card className="max-w-2xl">
        <div className="text-[11px] uppercase tracking-[0.12em] text-wb-ink2">Recovery Brief has moved</div>
        <p className="mt-2 text-[14px] leading-relaxed text-wb-ink">
          What this page used to show — capacity today, what&rsquo;s driving it, what your system needs,
          and your recovery trajectory — now lives on the Human Systems Workbench&rsquo;s{' '}
          <span className="font-medium">NOW</span> tab, kept up to date from the same live check-in data.
          Recent wins are on the <span className="font-medium">PATTERNS</span> tab.
        </p>
        <p className="mt-2 text-[13px] text-wb-ink2">
          Nothing real was dropped — this page is kept as a pointer, not deleted, since other parts of the
          platform still link to it.
        </p>
        <Link
          href="/human-systems-workbench"
          className="mt-4 inline-block rounded-md bg-wb-sage-deep px-4 py-2 text-[12px] font-bold uppercase tracking-[0.15em] text-white transition hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
        >
          Go to Human Systems — NOW →
        </Link>
      </Card>
    </WorkbenchShell>
  );
}
