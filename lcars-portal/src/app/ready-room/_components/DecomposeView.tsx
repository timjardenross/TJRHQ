'use client';

import { useEffect, useState } from 'react';
import { Button, Textarea, Input, Select } from '@/components/ui';
import {
  createTask, decomposeTask, fetchTasks, getReadyRoomContext, getTask, pickUpItems, promoteToMission,
  updateTaskState, type FollowThroughMode, type PersonalTask, type ReadyRoomContext,
} from '@/lib/personalTasks';
import { FOLLOW_THROUGH_MODES, autoSwitchModeOnDueDate } from './followThroughMode';
import { ActiveTaskView } from './ActiveTaskView';
import { PickUpBanner } from './PickUpBanner';
import { useAbortEffect } from '@/hooks/useAbortEffect';

type Stage = 'input' | 'thinking' | 'result' | 'started';

const EXAMPLES = ['Sort out the tax stuff', 'Organize the closet', 'Update the project status'];

const REGULATE_PREFIX = 'REGULATE:';
const CLARIFY_PREFIX = 'CLARIFY:';

/** UNSTICK ME (spec §15-20) — one smallest useful first action, not a plan.
 * "Make it smaller" / "Try another" iterate on that ONE action without
 * creating extra tasks or a long visible history.
 *
 * Mission 4 delta: the decompose call now receives Human Systems' posture
 * (never re-derived here — read via getReadyRoomContext, same as
 * TodayStream) so the model can (a) ask one clarifying question instead of
 * inventing an action for a vague goal, and (b) under PROTECT/RECOVER,
 * offer regulation/pause as a legitimate answer instead of always forcing
 * an executable step. Both are plain-string protocol prefixes on the same
 * single-string response the endpoint already returns — no new response
 * shape, no new persistence. */
export function DecomposeView({
  onSaved,
  onExecutingChange,
}: {
  onSaved: () => void;
  /** Mission 4: reports whether ActiveTaskView is showing, so the page shell
   * can drop into minimal/nav-free mode. */
  onExecutingChange?: (executing: boolean) => void;
}) {
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
  const [context, setContext] = useState<ReadyRoomContext>({
    posture: 'UNKNOWN', capacityLimit: 3, hasCheckinToday: false, freshnessStatus: 'none',
  });
  const [clarifyQuestion, setClarifyQuestion] = useState<string | null>(null);
  const [regulateSuggestion, setRegulateSuggestion] = useState<string | null>(null);
  const [pickUp, setPickUp] = useState<PersonalTask[]>([]);
  // Kept separate from `goal` — `goal` becomes the saved task/mission title
  // verbatim (startHere/turnIntoMission below), so a clarifying Q&A must
  // never be folded into it. Only used to build the text sent to the
  // decompose endpoint.
  const [clarification, setClarification] = useState<string | null>(null);

  useEffect(() => { onExecutingChange?.(stage === 'started'); }, [stage, onExecutingChange]);
  useAbortEffect((_signal, alive) => {
    getReadyRoomContext().then((c) => { if (alive()) setContext(c); });
    // Interruption-recovery gap (Mission 4 Stream E): a posture-driven
    // default can land the Captain on Unstick Me without ever seeing
    // TodayStream's "pick up where you left off" — surface it here too so
    // a paused, restart-cued task is never invisible just because low
    // capacity routed them to this domain instead of Do.
    fetchTasks({ includeCompleted: false }).then((tasks) => { if (alive()) setPickUp(pickUpItems(tasks)); });
  }, []);

  function handleDueDateChange(value: string) {
    setDueDate(value);
    setFollowThroughMode((prev) => autoSwitchModeOnDueDate(value, prev, modeTouched));
  }

  /** Splits a REGULATE:/CLARIFY:-prefixed response into its own state
   * instead of the micro-action field. Plain-string protocol, matching the
   * single-string contract /api/ready-room/decompose already has — no new
   * response shape. */
  function applyDecomposeResult(action: string | null, error: string | undefined, opts: { countsAsSmaller: boolean }) {
    setClarifyQuestion(null);
    setRegulateSuggestion(null);
    if (opts.countsAsSmaller) setSmallerCount((n) => n + 1);
    if (action?.startsWith(REGULATE_PREFIX)) {
      setRegulateSuggestion(action.slice(REGULATE_PREFIX.length).trim());
      setDecomposeError(null);
      return;
    }
    if (action?.startsWith(CLARIFY_PREFIX)) {
      setClarifyQuestion(action.slice(CLARIFY_PREFIX.length).trim());
      setDecomposeError(null);
      return;
    }
    if (action) {
      setMicroAction(action);
      setDecomposeError(null);
    } else {
      setDecomposeError(error ?? "Couldn't generate a step automatically — write your own below.");
    }
  }

  async function helpMeStart() {
    if (!goal.trim() || busy) return;
    setStage('thinking');
    setDecomposeError(null);
    setBusy(true);
    const { action, error } = await decomposeTask(goal, { posture: context.posture });
    setBusy(false);
    applyDecomposeResult(action, error, { countsAsSmaller: false });
    setStage('result');
  }

  function decomposeQuery(): string {
    return clarification ? `${goal}\n\nClarification: ${clarification}` : goal;
  }

  async function tryVariant(mode: 'smaller' | 'another') {
    if (busy) return;
    setBusy(true);
    const { action, error } = await decomposeTask(decomposeQuery(), { mode, previousAction: microAction, posture: context.posture });
    setBusy(false);
    applyDecomposeResult(action, error, { countsAsSmaller: mode === 'smaller' });
  }

  /** Captain answers the model's clarifying question — used only to build
   * the text sent back to decompose (decomposeQuery), never written into
   * `goal` itself (that stays the clean, saveable task title/description). */
  async function answerClarify(answer: string) {
    if (!answer.trim() || busy) return;
    setClarification(answer.trim());
    setStage('thinking');
    setBusy(true);
    const { action, error } = await decomposeTask(`${goal}\n\nClarification: ${answer.trim()}`, { posture: context.posture });
    setBusy(false);
    applyDecomposeResult(action, error, { countsAsSmaller: false });
    setStage('result');
  }

  /** The model asked to clarify but the Captain would rather just get
   * something to try — retries decomposition on the plain goal (no
   * clarification, no artificial restriction) rather than leaving an
   * empty box behind a button that promised "something to try". */
  async function skipClarify() {
    if (busy) return;
    setClarifyQuestion(null);
    setStage('thinking');
    setBusy(true);
    const { action, error } = await decomposeTask(goal, { mode: 'another', posture: context.posture });
    setBusy(false);
    applyDecomposeResult(action, error, { countsAsSmaller: false });
    setStage('result');
  }

  /** Captain explicitly overrode a REGULATE suggestion ("I'd still like to
   * try something small") — per Captain Override (mission §22: no repeated
   * challenge), this omits `posture` so the model cannot offer REGULATE
   * again on the same request; one override is final, not a starting point
   * for a loop. */
  async function tryAnywaySmallAction() {
    if (busy) return;
    setRegulateSuggestion(null);
    setStage('thinking');
    setBusy(true);
    const { action, error } = await decomposeTask(decomposeQuery());
    setBusy(false);
    applyDecomposeResult(action, error, { countsAsSmaller: false });
    setStage('result');
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
    setClarifyQuestion(null);
    setRegulateSuggestion(null);
    setClarification(null);
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
      {stage === 'input' && pickUp.length > 0 && (
        <PickUpBanner tasks={pickUp} />
      )}
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

      {stage === 'result' && regulateSuggestion && (
        <div className="flex flex-col gap-3 rounded-md border border-wb-sage/40 bg-wb-sage/10 p-4">
          <p className="text-[13px] text-wb-ink">{regulateSuggestion}</p>
          <div className="flex flex-wrap gap-2">
            <a
              href="/human-systems-workbench?domain=recovery"
              className="inline-flex items-center rounded-md border border-wb-line bg-wb-surface px-3 py-1.5 text-[13px] text-wb-ink hover:bg-wb-surface-raised"
            >
              Take a break instead
            </a>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={tryAnywaySmallAction}
            >
              I&apos;d still like to try something small
            </Button>
            <Button variant="ghost" onClick={reset}>Not now</Button>
          </div>
        </div>
      )}

      {stage === 'result' && clarifyQuestion && (
        <ClarifyPrompt question={clarifyQuestion} busy={busy} onAnswer={answerClarify} onSkip={skipClarify} />
      )}

      {stage === 'result' && !regulateSuggestion && !clarifyQuestion && (
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

/** Mission 4: the model asked a clarifying question rather than inventing
 * an action for a vague goal (spec §9/§32 "ambiguous task" scenario) —
 * one question, one answer, feeds straight back into decomposition. */
function ClarifyPrompt({
  question, busy, onAnswer, onSkip,
}: {
  question: string;
  busy: boolean;
  onAnswer: (answer: string) => void;
  onSkip: () => void;
}) {
  const [answer, setAnswer] = useState('');
  return (
    <div className="flex flex-col gap-3 rounded-md border border-wb-line bg-wb-surface p-4">
      <p className="text-[13px] text-wb-ink">{question}</p>
      <Textarea rows={2} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="One or two words is fine" />
      <div className="flex flex-wrap gap-2">
        <Button disabled={!answer.trim() || busy} onClick={() => onAnswer(answer)}>Continue</Button>
        <Button variant="ghost" disabled={busy} onClick={onSkip}>Skip — just give me something to try</Button>
      </div>
    </div>
  );
}
