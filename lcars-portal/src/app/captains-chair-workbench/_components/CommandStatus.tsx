'use client';

// Command Status (MSN-0364) — replaces the 5 equal-weight SituationBadge
// cards with one interpreted headline. The drill-down links each badge
// used to carry are preserved as the "Supporting Signals" row underneath,
// so nothing that was reachable before becomes unreachable now.

import Link from 'next/link';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { stateToneClasses } from '@/lib/departments';
import { POSTURE_STATE_TONE, RISK_STATE_TONE } from '@/lib/captainsChairData';
import type { CommandStatusResult } from '@/lib/captainsChairSynthesis';
import type { StateTone } from '@/lib/types';

interface SignalChip {
  label: string;
  value: string;
  tone: StateTone;
  href: string;
}

export function CommandStatus({
  status,
  loading,
  signals,
}: {
  status: CommandStatusResult;
  loading: boolean;
  signals: SignalChip[];
}) {
  const postureTone: StateTone = status.posture === 'UNKNOWN' ? 'unknown' : POSTURE_STATE_TONE[status.posture];
  const toneClasses = stateToneClasses(postureTone);

  return (
    <WorkbenchPanel title="Command Status" eyebrow="Interpreted, not raw">
      {loading ? (
        <p className="text-sm text-wb-ink2 animate-pulse">Assessing…</p>
      ) : (
        <div className="space-y-3">
          <div className="flex items-baseline gap-3">
            <span className={`text-2xl font-bold ${toneClasses.text}`}>{status.postureLine.toUpperCase()}</span>
            {status.hasUrgentException && (
              <span className={`rounded-full ${stateToneClasses('crit').bg} px-2 py-0.5 text-[11px] font-semibold ${stateToneClasses('crit').on}`}>
                Needs attention now
              </span>
            )}
          </div>
          <p className="text-sm leading-relaxed text-wb-ink">{status.interpretation}</p>

          <div className="grid grid-cols-1 gap-1.5 rounded-lg border border-wb-line/60 bg-wb-bg/50 p-3 text-[12.5px] sm:grid-cols-2">
            <p className="text-wb-ink2"><span className="font-semibold text-wb-ink">Personal:</span> {status.personalLine}</p>
            <p className="text-wb-ink2"><span className="font-semibold text-wb-ink">Environment:</span> {status.environmentLine}</p>
          </div>

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
