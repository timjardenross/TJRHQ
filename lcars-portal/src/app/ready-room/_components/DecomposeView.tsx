'use client';

import { useState } from 'react';
import { Button, Textarea, Input, Select } from '@/components/ui';
import { createTask, decomposeTask, getTask, promoteToMission, updateTaskState, type FollowThroughMode } from '@/lib/personalTasks';
import { FOLLOW_THROUGH_MODES, autoSwitchModeOnDueDate } from './followThroughMode';
import { ActiveTaskView } from './ActiveTaskView';
import type { PersonalTask } from '@/lib/personalTasks';

type Stage = 'input' | 'thinking' | 'result' | 'started';

const EXAMPLES = ['Sort out the tax stuff', 'Organize the closet', 'Update the project status'];

/** UNSTICK ME (spec §15-20) — one smallest useful first action, not a plan.
 * "Make it smaller" / "Try another" iterate on that ONE action without
 * creating extra tasks or a long visible history. */
export function DecomposeView({ onSaved }: { onSaved: () => void }) {
  const [stage, setStage] = useState<Stage>('input');
  const [goal, setGoal] = useState('');
  const [microAction, setMicroAction] = useState('');
  const [goodEnough, setGoodEnough] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [followThroughMode, setFollowThroughMode] = useState<FollowThroughMode>('normal');
  const [modeTouched, setModeTouched] = useState(false);
  const [decomposeError, setDecomposeError] = useState<string | null>(null);
  const [smallerCount, setSmallerCount] = useState(0);
  const [startedTask, setStartedTask] = useState<PersonalTask | null>(null);
  const [showMissionPrompt, setShowMissionPrompt] = useState(false);
  const [busy, setBusy] = useState(false);

  function handleDueDateChange(value: string) {
    setDueDate(value);
    setFollowThroughMode((prev) => autoSwitchModeOnDueDate(value, prev, modeTouched));
  }

  async function helpMeStart() {
    if (!goal.trim() || busy) return;
    setStage('thinking');
    setDecomposeError(null);
    setBusy(true);
    const { action, error } = await decomposeTask(goal);
    setBusy(false);
    if (action) setMicroAction(action);
    else {
      setDecomposeError(error ?? "Couldn't generate a step automatically — write your own below.");
      setMicroAction('');
    }
    setStage('result');
  }

  async function tryVariant(mode: 'smaller' | 'another') {
    if (busy) return;
    setBusy(true);
    const { action, error } = await decomposeTask(goal, { mode, previousAction: microAction });
    setBusy(false);
    if (mode === 'smaller') setSmallerCount((n) => n + 1);
    if (action) {
      setMicroAction(action);
      setDecomposeError(null);
    } else {
      setDecomposeError(error ?? "Couldn't generate that automatically — edit the step yourself below.");
    }
  }

  async function startHere() {
    setBusy(true);
    const result = await createTask({
      title: goal,
      category: 'task',
      due_date: dueDate || null,
      micro_action: microAction.trim() || null,
      mvp_note: goodEnough.trim() || null,
      follow_through_mode: followThroughMode,
    });
    if (result.ok && result.id) {
      await updateTaskState(result.id, 'in_progress');
      const fresh = await getTask(result.id);
      if (fresh) {
        setStartedTask(fresh);
        setStage('started');
        onSaved();
      }
    }
    setBusy(false);
  }

  async function turnIntoMission() {
    setBusy(true);
    await promoteToMission({ title: goal, context: null });
    setBusy(false);
    reset();
    onSaved();
  }

  function reset() {
    setStage('input');
    setGoal('');
    setMicroAction('');
    setGoodEnough('');
    setDueDate('');
    setFollowThroughMode('normal');
    setModeTouched(false);
    setDecomposeError(null);
    setSmallerCount(0);
    setStartedTask(null);
    setShowMissionPrompt(false);
  }

  if (stage === 'started' && startedTask) {
    return (
      <ActiveTaskView
        task={startedTask}
        onDone={() => { reset(); onSaved(); }}
        onPaused={() => { reset(); onSaved(); }}
        onBack={reset}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Textarea
          label="What's feeling hard to start?"
          hint="It doesn't need to be well explained."
          placeholder={EXAMPLES[0]}
          rows={2}
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          disabled={stage === 'thinking'}
        />
        {stage === 'input' && (
          <p className="mt-1 text-[11px] text-wb-ink2">e.g. {EXAMPLES.join(' · ')}</p>
        )}
      </div>

      {stage === 'input' && (
        <Button disabled={!goal.trim()} onClick={helpMeStart}>Help me start</Button>
      )}

      {stage === 'thinking' && (
        <p className="text-[13px] text-wb-ink2">Finding a tiny first step…</p>
      )}

      {stage === 'result' && (
        <div className="flex flex-col gap-4 rounded-md border border-wb-line bg-wb-surface p-4">
          {decomposeError && <p className="text-[12px] text-wb-warn-on">{decomposeError}</p>}

          <div>
            <p className="text-[11px] uppercase tracking-wide text-wb-sage-deep">Start here</p>
            <Textarea rows={2} value={microAction} onChange={(e) => setMicroAction(e.target.value)} />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button disabled={!microAction.trim() || busy} onClick={startHere}>Start here</Button>
            <Button variant="secondary" disabled={busy} onClick={() => tryVariant('smaller')}>Make it smaller</Button>
            <Button variant="secondary" disabled={busy} onClick={() => tryVariant('another')}>Try another</Button>
          </div>

          <Textarea
            label="What would be good enough?"
            hint="You don't have to solve the whole thing today."
            rows={2}
            value={goodEnough}
            onChange={(e) => setGoodEnough(e.target.value)}
          />
          <Input type="date" label="Due date (optional)" value={dueDate} onChange={(e) => handleDueDateChange(e.target.value)} />
          <Select
            label="Remind me"
            value={followThroughMode}
            onChange={(e) => { setModeTouched(true); setFollowThroughMode(e.target.value as FollowThroughMode); }}
          >
            {FOLLOW_THROUGH_MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </Select>

          {smallerCount >= 2 && !showMissionPrompt && (
            <button
              type="button"
              className="self-start text-[12px] text-wb-ink2 underline-offset-2 hover:underline"
              onClick={() => setShowMissionPrompt(true)}
            >
              This looks bigger than a task
            </button>
          )}
          {showMissionPrompt && (
            <div className="rounded-md border border-wb-line bg-wb-bg p-3">
              <p className="text-[13px] text-wb-ink">This looks bigger than a task.</p>
              <div className="mt-2 flex gap-2">
                <Button size="sm" onClick={turnIntoMission} disabled={busy}>Turn into a Mission</Button>
                <Button size="sm" variant="ghost" onClick={() => setShowMissionPrompt(false)}>Keep it simple</Button>
              </div>
            </div>
          )}

          <Button variant="ghost" onClick={reset}>Discard</Button>
        </div>
      )}
    </div>
  );
}
