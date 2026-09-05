'use client';

import { useState } from 'react';
import { Button, Textarea } from '@/components/ui';
import { completeWeeklyReview, type SystemSummary } from '@/lib/weeklyReview';

function Check({ done, label }: { done: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 text-[13px] text-wb-ink">
      <span aria-hidden className={done ? 'text-wb-ok-on' : 'text-wb-ink2'}>{done ? '✓' : '○'}</span>
      {label}
    </li>
  );
}

/** Close the Week (brief §19) — replaces the old bare "Mark review complete"
 * button with a checklist that represents what actually happened this
 * review, not just a button state. Reflection is optional by design (brief
 * §18); everything else always shows as done because reaching this panel
 * means the synthesis/carry-forward/watch sections above already rendered. */
export function CompletePanel({
  summary, signalCounts, nextWeekAccepted,
}: {
  summary: SystemSummary; signalCounts: Record<string, number>; nextWeekAccepted: boolean;
}) {
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function complete() {
    setBusy(true);
    setError(null);
    const result = await completeWeeklyReview(notes, summary, signalCounts, nextWeekAccepted);
    setBusy(false);
    if (result.ok) setDone(true);
    else setError(result.error ?? 'Failed to mark complete.');
  }

  if (done) {
    return (
      <div className="rounded-md border border-wb-line bg-wb-surface p-6 text-center">
        <p className="text-[14px] text-wb-ink">Week closed. See you next week.</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-wb-line bg-wb-surface p-4">
      <h2 className="mb-3 font-serif text-[15px] uppercase tracking-[0.1em] text-wb-ink">Close the Week</h2>
      <ul className="mb-4 flex flex-col gap-1.5">
        <Check done label="Week synthesised" />
        <Check done label="Carry-forward decisions reviewed" />
        <Check done={nextWeekAccepted} label="Next-week posture set" />
        <Check done label="Known Unknowns carried forward" />
        <Check done={notes.trim().length > 0} label="Personal reflection — optional" />
      </ul>
      <Textarea
        label="Your Reflection — anything HQ couldn't know from the data? (optional)"
        rows={2}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      {error && <p className="mt-2 text-[12px] text-wb-crit-on">{error}</p>}
      <Button className="mt-3" disabled={busy} onClick={complete}>Close Week →</Button>
    </div>
  );
}
