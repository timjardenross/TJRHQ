'use client';

// KPI strip for the Captain's Brief Workbench — the wb- home for the
// document's headline counts, mirroring the KpiDashboard pattern in the Capture
// / Human Systems Workbenches. Confidence gets a meter; warnings / priorities /
// next-actions are stat tiles. A tile click jumps to the relevant view/section.

import { Card } from './Shell';
import { ConfidenceMeter } from './cards';
import type { CaptainBriefDocument } from './types';

function Stat({
  value,
  label,
  onClick,
  emphasise,
}: {
  value: number;
  label: string;
  onClick?: () => void;
  emphasise?: boolean;
}) {
  const body = (
    <>
      <div className={`font-serif text-2xl ${emphasise && value > 0 ? 'text-wb-crit-on' : 'text-wb-ink'}`}>
        {value}
      </div>
      <div className="text-[11px] uppercase tracking-[0.14em] text-wb-ink2">{label}</div>
    </>
  );
  if (!onClick) return <div className="text-left">{body}</div>;
  return (
    <button
      onClick={onClick}
      className="rounded-md text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
    >
      {body}
    </button>
  );
}

function formatGeneratedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function KpiDashboard({
  doc,
  onJump,
}: {
  doc: CaptainBriefDocument;
  onJump?: (target: 'warnings' | 'priorities' | 'next_actions') => void;
}) {
  return (
    <Card className="mb-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="sm:w-56">
          <ConfidenceMeter score={doc.confidence} label="Document confidence" />
        </div>
        <div className="grid flex-1 grid-cols-3 gap-4">
          <Stat value={doc.warnings.length} label="Warnings" emphasise onClick={onJump && (() => onJump('warnings'))} />
          <Stat value={doc.priorities.length} label="Priorities" onClick={onJump && (() => onJump('priorities'))} />
          <Stat value={doc.next_actions.length} label="Next actions" onClick={onJump && (() => onJump('next_actions'))} />
        </div>
      </div>
      <p className="mt-3 border-t border-wb-line pt-2 text-[11px] text-wb-ink2">
        v{doc.version} · assembled {formatGeneratedAt(doc.generated_at)}
      </p>
    </Card>
  );
}
