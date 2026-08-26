'use client';

import { useState } from 'react';
import { Button, Textarea } from '@/components/ui';
import { completeWeeklyReview, type SystemSummary } from '@/lib/weeklyReview';

/** The "Reset" step — leave the system cleaner than you found it. One
 * button, optional reflection notes, done. Doesn't re-litigate every item —
 * that already happened per-signal via the "→ Ready Room" action above. */
export function CompletePanel({ summary }: { summary: SystemSummary }) {
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function complete() {
    setBusy(true);
    setError(null);
    const result = await completeWeeklyReview(notes, summary);
    setBusy(false);
    if (result.ok) setDone(true);
    else setError(result.error ?? 'Failed to mark complete.');
  }

  if (done) {
    return (
      <div className="rounded-md border border-wb-line bg-wb-surface p-6 text-center">
        <p className="text-[14px] text-wb-ink">Review complete. See you next week.</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-wb-line bg-wb-surface p-4">
      <Textarea
        label="Anything worth remembering about this week? (optional)"
        rows={2}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      {error && <p className="mt-2 text-[12px] text-wb-crit-on">{error}</p>}
      <Button className="mt-3" disabled={busy} onClick={complete}>Mark review complete</Button>
    </div>
  );
}
