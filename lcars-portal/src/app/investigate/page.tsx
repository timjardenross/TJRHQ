'use client';

// EOS Phase 2 Priority 2 (docs/EOS-CANONICAL-ARCHITECTURE-DECISIONS.md,
// Executive Intelligence): the one page that runs an Investigation Engine
// type and shows its real result. Reuses lib/investigationEngine.ts's
// openInvestigation() as-is via api/investigations/route.ts - no
// evidence-assembly or decision logic lives here.
//
// Deliberately requires ?type=&reason= in the URL - there is no type
// picker, no menu of investigations to browse. Per MSN-0353's own finding
// (zero of 22 real journeys began by browsing a menu) and the Canonical
// Architecture Decisions' §5 navigation model (no persistent sidebar
// anywhere, entry is contextual): this page is reached only from a
// specific link Home or Recommended already decided was relevant - never
// browsed to cold. Same zero-nav pattern as /decide, /ask, /recommended.
//
// Read-only: shows evidence and decision options for the Captain to read.
// Turning an option into a real action goes through the existing governed
// Decide flow (Priority 4's "no independent reasoning or decision logic in
// the interface") - this page has no approve/execute button of its own.

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { fetchInvestigation, type InvestigationRunResult } from '@/lib/investigate';

function InvestigatePageInner() {
  const params = useSearchParams();
  const type = params.get('type');
  const reason = params.get('reason');
  const originRef = params.get('originRef') ?? undefined;

  const [result, setResult] = useState<InvestigationRunResult | null | 'loading' | 'missing-params'>('loading');

  useEffect(() => {
    if (!type || !reason) {
      setResult('missing-params');
      return;
    }
    fetchInvestigation(type, reason, originRef).then(setResult);
  }, [type, reason, originRef]);

  return (
    <main className="min-h-screen flex justify-center bg-[#0B1017] text-[#E8EDF2]">
      <div className="w-full max-w-[620px] px-7 pt-10 pb-14 flex flex-col min-h-screen">
        <Link
          href="/workbenches"
          className="text-sm text-[#5A6875] hover:text-[#93A1B0] mb-8 inline-flex items-center gap-1.5 w-fit"
        >
          ← Workbenches
        </Link>

        {result === 'loading' && (
          <p className="text-[#5A6875] text-[15.5px]">Running the investigation…</p>
        )}

        {result === 'missing-params' && (
          <p className="text-[#93A1B0] text-[15.5px] leading-relaxed">
            This page needs a specific starting point — there&rsquo;s nothing to browse here.
            Reach it from a link on Home or Recommended.
          </p>
        )}

        {result === null && (
          <p className="text-[#93A1B0] text-[15.5px] leading-relaxed">
            Couldn&rsquo;t run this investigation just now. Try again from where you linked in.
          </p>
        )}

        {result && result !== 'loading' && result !== 'missing-params' && (
          <div className="flex flex-col gap-6">
            <div>
              <span className="inline-block text-[11px] uppercase tracking-[0.14em] text-[#5A6875] border border-[rgba(147,161,176,0.25)] rounded-full px-2.5 py-1 mb-4">
                {result.label} · {result.owner}
              </span>
              <p className="text-[15px] text-[#93A1B0] leading-relaxed">{result.triggerDescription}</p>
            </div>

            {!result.validation?.ok && (
              <div
                className="py-5"
                style={{ borderTop: '1px solid rgba(147,161,176,0.14)' }}
              >
                <p className="text-[13px] uppercase tracking-[0.12em] text-[#5A6875] mb-2">
                  Blocked before any decision was offered
                </p>
                <p className="text-[15.5px] text-[#E8EDF2] leading-relaxed">
                  {result.validation?.problems.join(' ') ?? 'Evidence could not be validated.'}
                </p>
              </div>
            )}

            {result.validation?.ok && result.decisionOptions.length > 0 && (
              <div className="py-5" style={{ borderTop: '1px solid rgba(147,161,176,0.14)' }}>
                <p className="text-[13px] uppercase tracking-[0.12em] text-[#5A6875] mb-3">
                  What the evidence shows
                </p>
                <ul className="flex flex-col gap-4">
                  {result.decisionOptions.map((opt) => (
                    <li key={opt.id} className="text-[15.5px] text-[#E8EDF2] leading-relaxed">
                      {opt.label}
                      {!opt.isReversible && (
                        <span className="block text-[12px] text-[#D8A65A] mt-1">Not reversible</span>
                      )}
                    </li>
                  ))}
                </ul>
                <p className="text-[12.5px] text-[#5A6875] mt-4">
                  This is evidence, not an action — nothing here changes anything. A decision with
                  real effect goes through Decide.
                </p>
                {/* EOS Phase 2 Priority 4: hands this investigation's real
                    evidence straight to the Advisory Workbench's Ask domain
                    (internal key 'board') as ambient context, rather than
                    making the Captain restate it - see
                    advisory-workbench/_components/AskView.tsx's EvidencePanel. */}
                <Link
                  href={`/advisory-workbench?domain=board&investigationType=${encodeURIComponent(type ?? '')}&investigationReason=${encodeURIComponent(result.triggerDescription)}`}
                  className="inline-block mt-3 text-[12.5px] text-[#5A6875] hover:text-[#93A1B0] underline underline-offset-2"
                >
                  Ask the Advisory Board about this
                </Link>
              </div>
            )}

            <details className="text-[12.5px] text-[#5A6875]">
              <summary className="cursor-pointer hover:text-[#93A1B0]">Audit trail</summary>
              <ul className="mt-3 flex flex-col gap-2">
                {result.audit.map((entry, i) => (
                  <li key={i}>
                    <span className="text-[#93A1B0]">{entry.stage}</span>: {entry.summary}
                  </li>
                ))}
              </ul>
            </details>
          </div>
        )}
      </div>
    </main>
  );
}

export default function InvestigatePage() {
  return (
    <Suspense fallback={null}>
      <InvestigatePageInner />
    </Suspense>
  );
}
