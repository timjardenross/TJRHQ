'use client';

import { Button } from '@/components/ui';
import type { PersonalTask } from '@/lib/personalTasks';

/** Mission 4: shared "pick up where you left off" card, extracted from
 * TodayStream so Unstick Me can surface the same paused/restart-cued tasks
 * — a posture-driven default can route the Captain straight into Unstick
 * Me, and a resumable task should never go invisible just because of which
 * domain they landed on (interruption-recovery gap, Stream E).
 *
 * Mission 6B §8.6: was previously read-only, telling the Captain to
 * "Switch to Do to continue" — a manual-navigation dead end, and the
 * reason discovery flagged this as not participating in interruption
 * recovery at all. Now clickable: `onResume` reuses the exact `?task=<id>`
 * deep link Ready Room's page/TodayStream already handle (Mission 6B
 * §8.4), landing directly in ActiveTaskView instead of a second click.
 * Deliberately still no evidence write here — resuming isn't an outcome
 * (helpful/not_helpful/not_now all describe a completed support
 * interaction); whatever happens once the Captain is back in
 * ActiveTaskView already carries its own evidence hookup
 * (recordSupportCompletion on Done) when that task has one. Manufacturing
 * a "helpful" event at click-time here would misrepresent evidence no
 * outcome has actually happened yet (spec §22 "evidence amplification"). */
export function PickUpBanner({ tasks, onResume }: { tasks: PersonalTask[]; onResume: (task: PersonalTask) => void }) {
  if (tasks.length === 0) return null;
  return (
    <div className="flex flex-col gap-2 rounded-md border border-wb-sage/40 bg-wb-sage/10 p-3">
      <p className="text-[11px] uppercase tracking-wide text-wb-sage-deep">Pick up where you left off</p>
      {tasks.map((t) => (
        <div key={t.id} className="flex items-center justify-between gap-2">
          <div>
            <p className="text-[13px] font-medium text-wb-ink">{t.title}</p>
            {t.restart_cue && <p className="text-[12px] text-wb-ink2">{t.restart_cue}</p>}
          </div>
          <Button size="sm" onClick={() => onResume(t)}>Continue</Button>
        </div>
      ))}
    </div>
  );
}
