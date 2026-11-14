export type CompanionState = { stage: 'morning'|'plan'|'active'|'deferred'|'evening'|'safety_hold'; actionStatus?: string|null; currentAction?: string|null; returningAfterGap?: boolean };

export type PrimaryJourney = 'start_my_day' | 'help_me_now' | 'something_changed';

export type JourneyContext = CompanionState & {
  journey?: PrimaryJourney;
  chosenColour?: 'Green'|'Amber'|'Red'|string|null;
  hasPlan?: boolean;
  hasCurrentAction?: boolean;
};

export type JourneyGuide = {
  journey: PrimaryJourney;
  label: string;
  title: string;
  body: string;
  primary: string;
  secondary: string;
  nextStep: string;
  showSafety: boolean;
};

/**
 * Resolve the three user-facing entry points without exposing the product's
 * internal stages. Explicit intent wins; otherwise the current day state is
 * used so a returning user is not sent back through morning setup.
 */
export function resolvePrimaryJourney(state: JourneyContext): PrimaryJourney {
  if (state.journey) return state.journey;
  if (state.stage === 'safety_hold' || state.actionStatus === 'deferred' || state.stage === 'deferred') return 'something_changed';
  if (state.stage === 'morning' || state.returningAfterGap) return 'start_my_day';
  return 'help_me_now';
}

/**
 * The journey is deliberately action-first: one clear next step, one
 * fallback, and a persistent safety exit. It is deterministic and works
 * without AI, so a model or network outage never blocks the user.
 */
export function primaryJourneyCopy(state: JourneyContext): JourneyGuide {
  const journey = resolvePrimaryJourney(state);
  const safety = state.stage === 'safety_hold' || state.chosenColour === 'Red';

  if (state.stage === 'safety_hold') {
    return {
      journey: 'something_changed',
      label: 'Safety boundary',
      title: 'Pause ordinary coaching.',
      body: 'Use the agreed safety pathway first. The Studio will not interpret the symptom or coach you through it.',
      primary: 'Open the safety card',
      secondary: 'I need a different kind of help',
      nextStep: 'Use the safety card, then return only when the safety question is settled.',
      showSafety: true,
    };
  }

  if (journey === 'start_my_day') {
    return {
      journey,
      label: 'Start my day',
      title: state.returningAfterGap ? 'Start with today, not catch-up.' : 'How much room is there today?',
      body: 'Choose only the signals that help. The Studio will turn them into one manageable direction, not a list of tasks.',
      primary: state.stage === 'morning' ? 'Check in with today' : 'Choose what matters',
      secondary: 'I need help right now',
      nextStep: state.stage === 'morning' ? 'Notice capacity, then choose one thing worth protecting.' : 'Choose the smallest meaningful version of your plan.',
      showSafety: true,
    };
  }

  if (journey === 'something_changed') {
    return {
      journey,
      label: safety ? 'A lower-demand route' : 'Something changed',
      title: safety ? 'Make the next step smaller.' : 'Pause. We can adjust without starting over.',
      body: safety
        ? 'Keep essentials only, use your agreed plan, and choose one low-demand option. This does not change Peter’s exercise plan.'
        : 'You do not need to push through or redo the check-in. We can adjust without starting over: tell the Studio what changed and choose a smaller, later or different route.',
      primary: safety ? 'Open the Red-day plan' : 'Tell the Studio what changed',
      secondary: 'Move this to later',
      nextStep: safety ? 'Reduce one non-essential demand, then reassess.' : 'Name the change in a few words, then choose the least demanding useful option.',
      showSafety: true,
    };
  }

  return {
    journey: 'help_me_now',
    label: 'Help me now',
    title: state.currentAction || 'Choose one useful next step.',
    body: 'The Studio will offer one practical option. You can make it smaller, choose a different route or stop without failure.',
    primary: state.currentAction ? 'Help me do this' : 'Give me one next step',
    secondary: 'Something changed',
    nextStep: state.hasCurrentAction || state.currentAction ? 'Do only this part, then check whether the day has changed.' : 'Choose one low-effort action that supports what matters today.',
    showSafety: true,
  };
}

export type DayGuideState = { stage: CompanionState['stage']; valuedActivity?: string|null; plan?: string|null; currentAction?: string|null; actionStatus?: string|null; hasReminder?: boolean; learningNote?: string|null };

export function companionCopy(state: CompanionState) {
  if (state.stage === 'safety_hold') return { label: 'Safety boundary', title: 'Pause the Studio here.', body: 'Use your agreed safety pathway. The Studio will not coach through a safety concern.', primary: 'Open safety card' };
  if (state.returningAfterGap) return { label: 'Welcome back', title: 'Start with today, not catch-up.', body: 'Choose only what is possible now. Nothing from the gap needs to be repaid.', primary: 'Start today' };
  if (state.stage === 'evening') return { label: 'Close the day', title: 'Keep one useful thing from today.', body: 'Name what helped, what cost more, or what you want to repeat. That is enough.', primary: 'Close today' };
  if (state.actionStatus === 'deferred' || state.stage === 'deferred') return { label: 'A later route', title: 'The next step can wait.', body: 'You have not failed the plan. Choose a smaller route, return later, or stop for today.', primary: 'Choose another route' };
  if (state.currentAction) return { label: 'Next step', title: state.currentAction, body: 'Do only this part. If it is too much or the day changes, choose a different route instead of pushing through.', primary: 'Help me do this' };
  return { label: 'Next step', title: 'What would help right now?', body: 'Choose one small action. The Studio will stay with you and adapt the route if the day changes.', primary: 'Choose one step' };
}

export function shouldOfferReentry(lastSeen: string|null, today: string) { return Boolean(lastSeen && lastSeen !== today); }

/** A compact day map: orient the person without exposing a task list. */
export function dayGuideCopy(state: DayGuideState) {
  const valued = state.valuedActivity || 'one thing that matters';
  if (state.stage === 'safety_hold') return { now: 'Use the safety pathway', next: 'Pause ordinary coaching', later: 'Return only when the safety question is settled', primary: 'Open safety card' };
  if (state.stage === 'morning') return { now: 'Notice the room you have today', next: 'Choose one thing worth protecting', later: 'Let the Studio shape the next step', primary: 'Begin the morning check-in' };
  if (state.stage === 'plan') return { now: `Choose the smallest version of ${valued}`, next: 'Set a stopping point before you begin', later: 'Adapt if the day changes', primary: 'Choose what matters' };
  if (state.stage === 'deferred') return { now: 'Give the next step less weight', next: state.hasReminder ? 'Return when your check-in is ready' : 'Return when there is more room', later: 'No catch-up is required', primary: 'Choose another route' };
  if (state.stage === 'evening') return { now: 'Keep one useful observation', next: 'Use it to shape tomorrow', later: 'The day is complete', primary: 'Close the day' };
  if (state.actionStatus === 'completed') return { now: 'Notice what changed after the action', next: 'Close the day when ready', later: 'Tomorrow starts without catch-up', primary: 'Close the day' };
  return { now: state.currentAction || state.plan || `Protect ${valued} in a small way`, next: state.hasReminder ? 'Check in: what has changed?' : 'Check what has changed before continuing', later: state.learningNote ? 'Carry yesterday’s learning lightly' : 'Close the day without measuring your worth', primary: 'Guide me from here' };
}
