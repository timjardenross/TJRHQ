'use client';

// CAPACITY (Command-Experience vNext, Phase 2, mission §9.5) — the
// dedicated Human Systems section, replacing the old Situation panel's
// "Personal" domain fold. Reads only the canonical assessed context
// (assessed-context.ts via useHumanSystemsContext()) — no useROSData mock
// posture, ever, as command truth.

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { stateToneClasses } from '@/lib/departments';
import { CAPACITY_STATE_LABEL, SYSTEM_POSTURE_STATE_TONE } from '@/lib/captainsChairData';
import type { AssessedContext } from '@/app/api/human-systems/assessed-context';

export function Capacity({
  context,
  loading,
  unavailable,
}: {
  context: AssessedContext | null;
  loading: boolean;
  unavailable: boolean;
}) {
  if (loading) {
    return (
      <WorkbenchPanel title="Capacity">
        <p className="text-sm text-wb-ink2 animate-pulse">Loading…</p>
      </WorkbenchPanel>
    );
  }

  if (unavailable) {
    return (
      <WorkbenchPanel title="Capacity" eyebrow="Human Systems assessed context">
        <p className={`text-sm font-semibold ${stateToneClasses('unknown').text}`}>UNKNOWN — Human Systems unavailable</p>
        <Link href="/human-systems-workbench" className="mt-2 inline-block text-[11px] text-wb-sage-deep hover:underline">Open Human Systems →</Link>
      </WorkbenchPanel>
    );
  }

  const hasCheckinToday = context?.has_checkin_today ?? false;
  const posture = context?.posture ?? 'UNKNOWN';
  const tone = stateToneClasses(SYSTEM_POSTURE_STATE_TONE[posture]);

  return (
    <WorkbenchPanel title="Capacity" eyebrow="Human Systems assessed context">
      {!hasCheckinToday ? (
        <>
          <p className={`text-sm font-semibold ${tone.text}`}>UNKNOWN — no check-in today</p>
          <p className="mt-1 text-sm text-wb-ink/80">
            {context?.posture_message ?? 'No capacity check-in recorded for today yet.'}
          </p>
        </>
      ) : (
        <>
          <p className={`text-sm font-semibold ${tone.text}`}>{posture}</p>
          <ul className="mt-1 space-y-0.5 text-sm text-wb-ink/80">
            <li>Capacity {context ? (CAPACITY_STATE_LABEL[context.available_capacity] ?? context.available_capacity) : 'unknown'}</li>
            {context?.stimulation_context && <li>Stimulation {context.stimulation_context}</li>}
            <li>Recovery trajectory {context?.strain_or_recovery_context.trajectory.replaceAll('_', ' ') ?? 'unknown'}</li>
          </ul>
          <p className="mt-2 text-sm text-wb-ink">{context?.posture_message}</p>
        </>
      )}
      <Link href="/human-systems-workbench" className="mt-2 inline-block text-[11px] text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
        Open Human Systems →
      </Link>
    </WorkbenchPanel>
  );
}
