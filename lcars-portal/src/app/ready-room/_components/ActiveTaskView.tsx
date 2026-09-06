'use client';

import { useEffect, useState } from 'react';
import { Button, Textarea } from '@/components/ui';
import { updateTaskState, type PersonalTask } from '@/lib/personalTasks';

/** The "YOU'RE DOING" experience (spec §12) — starting a task should feel
 * like an immediate action, not another admin screen. No timers, streaks,
 * or scores (spec §32) — just the one next physical action. */
export function ActiveTaskView({
  task,
  onDone,
  onPaused,
  onBack,
}: {
  task: PersonalTask;
  onDone: () => void;
  onPaused: () => void;
  onBack: () => void;
}) {
  const [stopping, setStopping] = useState(false);
  const [note, setNote] = useState(task.restart_cue ?? '');
  const [busy, setBusy] = useState(false);

  const startHere = task.micro_action?.trim() || task.title;

  async function markStarted() {
    if (task.work_state === 'in_progress' || task.work_state === 'paused') return;
    await updateTaskState(task.id, 'in_progress');
  }

  async function complete() {
    setBusy(true);
    await updateTaskState(task.id, 'completed');
    setBusy(false);
    onDone();
  }

  async function saveAndStop() {
    setBusy(true);
    await updateTaskState(task.id, 'paused', {
      restart_cue: note.trim() || null,
      stop_point: note.trim() || null,
    });
    setBusy(false);
    onPaused();
  }

  // Enter in_progress the first time this view opens for a not-yet-started
  // task, without blocking the UI on the round trip.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (task.work_state === 'captured') void markStarted(); }, [task.id]);

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 rounded-md border border-wb-line bg-wb-surface p-6">
      <div>
        <p className="text-[11px] uppercase tracking-wide text-wb-ink2">You&apos;re doing</p>
        <h2 className="font-serif text-[18px] text-wb-ink">{task.title}</h2>
      </div>

      {!stopping && (
        <>
          <div className="rounded-md bg-wb-sage/10 p-3">
            <p className="text-[11px] uppercase tracking-wide text-wb-sage-deep">Start here</p>
            <p className="mt-1 text-[14px] text-wb-ink">{startHere}</p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={complete}>Done</Button>
            <Button variant="secondary" disabled={busy} onClick={() => setStopping(true)}>
              I&apos;m stopping here
            </Button>
            <Button variant="ghost" disabled={busy} onClick={onBack}>Back</Button>
          </div>
        </>
      )}

      {stopping && (
        <div className="flex flex-col gap-3 border-t border-wb-line pt-3">
          <p className="text-[13px] text-wb-ink">Leave future-you a clue. Where did you get to?</p>
          <Textarea
            rows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Rubbish is gone. Next sweep the floor."
          />
          <div className="flex gap-2">
            <Button disabled={busy} onClick={saveAndStop}>Save &amp; stop</Button>
            <Button variant="ghost" disabled={busy} onClick={() => setStopping(false)}>Back</Button>
          </div>
        </div>
      )}
    </div>
  );
}
