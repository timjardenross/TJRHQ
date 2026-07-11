'use client';

// EOS Phase 2 Priority 1 (docs/EOS-CANONICAL-ARCHITECTURE-DECISIONS.md §1):
// "Integrate existing... recommendations... into this experience." Reuses
// the real Recommendation Engine bridge (lib/recommendations.ts,
// api/recommendations/route.ts -> core/coordination/recommendation_engine.py)
// as-is - no ranking/scoring logic lives here. Read-only, deliberately: a
// recommendation is evidence-backed advice, not a governed action. Turning
// one into a real action (approving a mission, logging a decision) happens
// through the existing Decide flow, per Priority 4's "no independent
// reasoning or decision logic in the interface" constraint - this page
// never mutates anything.
//
// Same zero-nav, single-purpose pattern as /decide and /ask: quiet "← Home"
// link, no sidebar, reached only by deliberate navigation from Home.

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchRecommendations, type RecommendationPackage } from '@/lib/recommendations';

const URGENCY_LABEL: Record<string, string> = {
  high: 'Time-sensitive',
  medium: 'Some urgency',
  low: 'No particular urgency',
  none: 'No deadline',
};

export default function RecommendedPage() {
  const [pkg, setPkg] = useState<RecommendationPackage | null | 'loading'>('loading');

  useEffect(() => {
    fetchRecommendations().then(setPkg);
  }, []);

  return (
    <main className="min-h-screen flex justify-center bg-[#0B1017] text-[#E8EDF2]">
      <div className="w-full max-w-[620px] px-7 pt-10 pb-14 flex flex-col min-h-screen">
        <Link
          href="/home"
          className="text-sm text-[#5A6875] hover:text-[#93A1B0] mb-8 inline-flex items-center gap-1.5 w-fit"
        >
          ← Home
        </Link>

        <h1
          className="text-[28px] sm:text-[34px] mb-3 leading-[1.2]"
          style={{
            // Same fix as HomeScreen.tsx/decide/page.tsx: globals.css forces
            // uppercase sans on h1-h3 - pinned inline, not fought.
            fontFamily: '"New York", "SF Pro Display", Georgia, serif',
            fontWeight: 500,
            textTransform: 'none',
          }}
        >
          What&rsquo;s worth doing next
        </h1>

        {pkg === 'loading' && (
          <p className="text-[#5A6875] text-[15.5px]">Reading the recommendation engine…</p>
        )}

        {pkg === null && (
          <p className="text-[#93A1B0] text-[15.5px] leading-relaxed">
            Couldn&rsquo;t reach the recommendation engine just now. This isn&rsquo;t a claim that
            nothing needs attention — try again shortly.
          </p>
        )}

        {pkg && pkg !== 'loading' && pkg.recommendations.length === 0 && (
          <p className="text-[#93A1B0] text-[15.5px] leading-relaxed">
            Nothing rose to the top of {pkg.total_active_missions} active mission
            {pkg.total_active_missions === 1 ? '' : 's'} right now.
          </p>
        )}

        {pkg && pkg !== 'loading' && pkg.recommendations.length > 0 && (
          <div className="flex flex-col gap-6">
            {!pkg.health_constraints_applied && (
              <p className="text-[12.5px] text-[#5A6875] -mt-1">
                Capacity/health context wasn&rsquo;t available for this pass — ranking reflects
                priority and staleness only.
              </p>
            )}
            {pkg.recommendations.map((rec) => (
              <div
                key={rec.mission_id}
                className="py-6"
                style={{ borderTop: '1px solid rgba(147,161,176,0.14)' }}
              >
                <div className="flex items-baseline justify-between gap-3 mb-2">
                  <span className="text-[11px] uppercase tracking-[0.12em] text-[#5A6875]">
                    #{rec.priority_rank} · {rec.mission_id}
                  </span>
                  <span className="text-[11px] text-[#5A6875] tabular-nums">
                    confidence {Math.round(rec.confidence * 100)}%
                  </span>
                </div>
                <h2
                  className="text-[19px] mb-2 leading-snug"
                  style={{
                    fontFamily: '"New York", "SF Pro Display", Georgia, serif',
                    fontWeight: 500,
                  }}
                >
                  {rec.title}
                </h2>
                <p className="text-[15px] text-[#93A1B0] leading-relaxed mb-2">{rec.reason}</p>
                <p className="text-[13.5px] text-[#E8EDF2] mb-2">
                  <span className="text-[#5A6875]">Next: </span>
                  {rec.next_action}
                </p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-[#5A6875]">
                  <span>{URGENCY_LABEL[rec.deadline_urgency] ?? rec.deadline_urgency}</span>
                  {rec.due_date && <span>due {rec.due_date}</span>}
                  {rec.blockers.length > 0 && <span>blocked by {rec.blockers.join(', ')}</span>}
                </div>
                {rec.health_constraint_note && (
                  <p className="text-[12.5px] text-[#D8A65A] mt-2">{rec.health_constraint_note}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
