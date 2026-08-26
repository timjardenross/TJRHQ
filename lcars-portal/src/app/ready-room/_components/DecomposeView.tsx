'use client';

import { useState } from 'react';
import { Button, Textarea, Input, Select } from '@/components/ui';
import { createTask, decomposeTask, updateTaskState, type FollowThroughMode } from '@/lib/personalTasks';
import { FOLLOW_THROUGH_MODES, autoSwitchModeOnDueDate } from './followThroughMode';

type Stage = 'input' | 'thinking' | 'result' | 'started';

const EXAMPLES = ['Organize the closet', 'Fix the tax situation', 'Update the project status'];

/** Turns a vague task into: the goal (as typed), a tiny first action (from
 * decompose_task via /api/ready-room/decompose), an editable "good enough"
 * version, and a stop point / restart cue captured up front so re-entering
 * after an interruption never starts from a blank page. */
export function DecomposeView({ onSaved }: { onSaved: () => void }) {
  const [stage, setStage] = useState<Stage>('input');
  const [goal, setGoal] = useState('');
  const [microAction, setMicroAction] = useState('');
  const [mvpNote, setMvpNote] = useState('');
  const [restartCue, setRestartCue] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [followThroughMode, setFollowThroughMode] = useState<FollowThroughMode>('normal');
  const [modeTouched, setModeTouched] = useState(false);
  const [decomposeError, setDecomposeError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function handleDueDateChange(value: string) {
    setDueDate(value);
    setFollowThroughMode((prev) => autoSwitchModeOnDueDate(value, prev, modeTouched));
  }

  function handleModeChange(value: FollowThroughMode) {
    setModeTouched(true);
    setFollowThroughMode(value);
  }

  async function breakItDown() {
    if (!goal.trim() || busy) return;
    setStage('thinking');
    setDecomposeError(null);
    setBusy(true);
    const { action, error } = await decomposeTask(goal);
    setBusy(false);
    if (action) {
      setMicroAction(action);
    } else {
      setDecomposeError(error ?? "Couldn't generate a step automatically — write your own below.");
      setMicroAction('');
    }
    setStage('result');
  }

  async function saveAndStart() {
    setBusy(true);
    const result = await createTask({
      title: goal,
      category: 'task',
      due_date: dueDate || null,
      micro_action: microAction.trim() || null,
      mvp_note: mvpNote.trim() || null,
      follow_through_mode: followThroughMode,
    });
    if (result.ok && result.id) {
      await updateTaskState(result.id, 'in_progress', { restart_cue: restartCue.trim() || null });
      setTaskId(result.id);
      setStage('started');
      onSaved();
    }
    setBusy(false);
  }

  function reset() {
    setStage('input');
    setGoal('');
    setMicroAction('');
    setMvpNote('');
    setRestartCue('');
    setDueDate('');
    setFollowThroughMode('normal');
    setModeTouched(false);
    setDecomposeError(null);
    setTaskId(null);
  }

  if (stage === 'started') {
    return (
      <div className="rounded-md border border-wb-line bg-wb-surface p-6 text-center">
        <p className="text-[14px] text-wb-ink">Started. It&apos;s in your Now column.</p>
        <Button className="mt-4" variant="secondary" onClick={reset}>Break down another task</Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Textarea
          label="What's the vague, overwhelming thing?"
          placeholder={EXAMPLES[0]}
          rows={2}
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          disabled={stage === 'thinking'}
        />
        {stage === 'input' && (
          <p className="mt-1 text-[11px] text-wb-ink2">
            e.g. {EXAMPLES.join(' · ')}
          </p>
        )}
      </div>

      {stage === 'input' && (
        <Button disabled={!goal.trim()} onClick={breakItDown}>Break it down</Button>
      )}

      {stage === 'thinking' && (
        <p className="text-[13px] text-wb-ink2">Finding a tiny first step…</p>
      )}

      {stage === 'result' && (
        <div className="flex flex-col gap-4 rounded-md border border-wb-line bg-wb-surface p-4">
          {decomposeError && (
            <p className="text-[12px] text-wb-warn-on">{decomposeError}</p>
          )}
          <Textarea
            label="First action — do this now, 5–15 minutes"
            rows={2}
            value={microAction}
            onChange={(e) => setMicroAction(e.target.value)}
          />
          <Textarea
            label="Good enough version (optional)"
            hint="What counts as &quot;done enough&quot;, if you never get further than this?"
            rows={2}
            value={mvpNote}
            onChange={(e) => setMvpNote(e.target.value)}
          />
          <Textarea
            label="Restart cue (optional)"
            hint="If you get pulled away, what should future-you read to jump back in?"
            rows={1}
            value={restartCue}
            onChange={(e) => setRestartCue(e.target.value)}
          />
          <Input type="date" label="Due date (optional)" value={dueDate} onChange={(e) => handleDueDateChange(e.target.value)} />
          <Select
            label="Follow-through"
            value={followThroughMode}
            onChange={(e) => handleModeChange(e.target.value as FollowThroughMode)}
          >
            {FOLLOW_THROUGH_MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </Select>
          <div className="flex gap-2">
            <Button disabled={!microAction.trim() || busy} onClick={saveAndStart}>Start</Button>
            <Button variant="secondary" onClick={reset}>Discard</Button>
          </div>
        </div>
      )}
    </div>
  );
}
