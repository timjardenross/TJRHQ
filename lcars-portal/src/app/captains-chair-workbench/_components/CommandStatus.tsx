'use client';

// TODAY (Command-Experience vNext, Phase 2) — answers "what kind of day is
// this?" with one command-level posture (commandState.ts's
// deriveCommandPosture()), not Human Systems' own posture. Human Systems
// contributes to this; it does not become it (mission §6). The personal/
// environment breakdown Human Systems' CommandStatusResult already computes
// is preserved as a restrained "Why?" expansion — explanation, never raw
// plumbing (mission §9.1).
//
// Supersedes the previous MSN-0364 version, which used Human Systems'
// posture band directly as the headline (STABLE/PROTECT/etc) — that
// conflated "what kind of day" with "what's my capacity," the exact
// conflation mission §6 calls out as wrong.

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { stateToneClasses } from '@/lib/departments';
import type { CommandStatusResult } from '@/lib/captainsChairSynthesis';
import type { CommandPostureResult } from '@/lib/commandState';
import type { StateTone } from '@/lib/types';

const POSTURE_TONE: Record<CommandPostureResult['posture'], StateTone> = {
  RESPOND: 'crit',
  RECOVER: 'crit',
  PROTECT: 'warn',
  FOCUS: 'ok',
  STEADY: 'ok',
  UNKNOWN: 'unknown',
};

interface SignalChip {
  label: string;
  value: string;
  tone: StateTone;
  href: string;
}

export function CommandStatus({
  posture,
  status,
  loading,
  signals,
}: {
  posture: CommandPostureResult;
  status: CommandStatusResult;
  loading: boolean;
  signals: SignalChip[];
}) {
  const toneClasses = stateToneClasses(POSTURE_TONE[posture.posture]);

  return (
    <WorkbenchPanel title="Today" eyebrow="What kind of day is this?">
      {loading ? (
        <p className="text-sm text-wb-ink2 animate-pulse">Assessing…</p>
      ) : (
        <div className="space-y-3">
          <div className="flex items-baseline gap-3">
            <span className={`text-2xl font-bold ${toneClasses.text}`}>{posture.headline}</span>
            {status.hasUrgentException && (
              <span className={`rounded-full ${stateToneClasses('crit').bg} px-2 py-0.5 text-[11px] font-semibold ${stateToneClasses('crit').on}`}>
                Needs attention now
              </span>
            )}
          </div>
          <p className="text-sm leading-relaxed text-wb-ink">{posture.explanation}</p>

          <details className="group">
            <summary className="cursor-pointer text-[12.5px] font-medium text-wb-sage-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep">
              Why?
            </summary>
            <div className="mt-2 grid grid-cols-1 gap-1.5 rounded-lg border border-wb-line/60 bg-wb-bg/50 p-3 text-[12.5px] sm:grid-cols-2">
              <p className="text-wb-ink2"><span className="font-semibold text-wb-ink">Human Systems:</span> {status.personalLine}</p>
              <p className="text-wb-ink2"><span className="font-semibold text-wb-ink">Environment:</span> {status.environmentLine}</p>
            </div>
          </details>

          <div className="flex flex-wrap gap-2 pt-1">
            {signals.map((s) => {
              const c = stateToneClasses(s.tone);
              return (
                <Link
                  key={s.label}
                  href={s.href}
                  className={`rounded-full border ${c.border} ${c.bg} px-2.5 py-1 text-[11px] font-medium ${c.text} transition-colors hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep`}
                >
                  {s.label}: {s.value}
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </WorkbenchPanel>
  );
}
