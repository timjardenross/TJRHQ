'use client';

import { Card, Button } from '@/components/ui';
import type { NextWeekPosture as NextWeekPostureData } from '@/lib/weeklyReview';

/** Capacity-aware recommended posture (brief §16) — reuses Human Systems'
 * own StrategicPosture engine (see route.ts's fetchStrategicPosture), not a
 * competing taxonomy. Acceptance is recorded locally into the Close Week
 * record only (brief §17: don't tightly couple to every downstream
 * surface) — TJR confirms before it's treated as decided (brief §30). */
export function NextWeekPosture({
  data, accepted, onAccept,
}: {
  data: NextWeekPostureData; accepted: boolean; onAccept: () => void;
}) {
  return (
    <Card>
      <h2 className="mb-1 font-serif text-[15px] uppercase tracking-[0.1em] text-wb-ink">Next Week</h2>
      <p className="mb-1 text-[11px] uppercase tracking-[0.1em] text-wb-ink2">Recommended posture</p>
      <p className="mb-3 font-serif text-[20px] text-wb-ink">{data.posture}</p>
      <p className="mb-3 text-[13px] text-wb-ink2">{data.message}</p>
      {data.priorities.length > 0 && (
        <div className="mb-3">
          <p className="mb-1 text-[11px] uppercase tracking-[0.08em] text-wb-ink2">Priority</p>
          <ol className="flex flex-col gap-1 text-[13px] text-wb-ink">
            {data.priorities.map((p, i) => <li key={i}>{i + 1}. {p}</li>)}
          </ol>
        </div>
      )}
      {data.avoid && (
        <p className="mb-3 text-[12px] text-wb-ink2"><span className="font-medium text-wb-ink">Avoid:</span> {data.avoid}</p>
      )}
      <Button variant={accepted ? 'secondary' : 'primary'} disabled={accepted} onClick={onAccept}>
        {accepted ? 'Posture accepted ✓' : 'Accept Next-Week Posture →'}
      </Button>
    </Card>
  );
}
