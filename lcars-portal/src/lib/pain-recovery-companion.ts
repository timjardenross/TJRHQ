export type CompanionState = { stage: 'morning'|'plan'|'active'|'deferred'|'evening'|'safety_hold'; actionStatus?: string|null; currentAction?: string|null; returningAfterGap?: boolean };

export type DayGuideState = { stage: CompanionState['stage']; valuedActivity?: string|null; plan?: string|null; currentAction?: string|null };

export function companionCopy(state: CompanionState) {
  if (state.stage === 'safety_hold') return { label: 'Safety boundary', title: 'Pause the Studio here.', body: 'Use your agreed safety pathway. The Studio will not coach through a safety concern.', primary: 'Open safety card' };
  if (state.returningAfterGap) return { label: 'Welcome back', title: 'Start with today, not catch-up.', body: 'Choose only what is possible now. Nothing from the gap needs to be repaid.', primary: 'Start today' };
  if (state.stage === 'evening') return { label: 'Close the day', title: 'Keep one useful thing from today.', body: 'Name what helped, what cost more, or what you want to repeat. That is enough.', primary: 'Close today' };
  if (state.actionStatus === 'deferred' || state.stage === 'deferred') return { label: 'A later route', title: 'The next step can wait.', body: 'You have not failed the plan. Choose a smaller route, return later, or stop for today.', primary: 'Choose another route' };
  if (state.currentAction) return { label: 'Your companion', title: state.currentAction, body: 'Stay with this one step. If the situation changes, change the route rather than pushing through.', primary: 'Guide me from here' };
  return { label: 'Your companion', title: 'What would make the next few hours more possible?', body: 'Choose one useful action. The Studio will help you adapt it if the day changes.', primary: 'Guide me' };
}

export function shouldOfferReentry(lastSeen: string|null, today: string) { return Boolean(lastSeen && lastSeen !== today); }

/** A compact day map: orient the person without exposing a task list. */
export function dayGuideCopy(state: DayGuideState) {
  const valued = state.valuedActivity || 'one thing that matters';
  if (state.stage === 'safety_hold') return { now: 'Use the safety pathway', next: 'Pause ordinary coaching', later: 'Return only when the safety question is settled' };
  if (state.stage === 'morning') return { now: 'Notice the room you have today', next: 'Choose one thing worth protecting', later: 'Let the Studio shape the next step' };
  if (state.stage === 'plan') return { now: `Choose the smallest version of ${valued}`, next: 'Set a stopping point before you begin', later: 'Adapt if the day changes' };
  if (state.stage === 'deferred') return { now: 'Give the next step less weight', next: 'Return when there is more room', later: 'No catch-up is required' };
  if (state.stage === 'evening') return { now: 'Keep one useful observation', next: 'Use it to shape tomorrow', later: 'The day is complete' };
  return { now: state.currentAction || state.plan || `Protect ${valued} in a small way`, next: 'Check what has changed before continuing', later: 'Close the day without measuring your worth' };
}
