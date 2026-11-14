export type CompanionState = { stage: 'morning'|'plan'|'active'|'deferred'|'evening'|'safety_hold'; actionStatus?: string|null; currentAction?: string|null; returningAfterGap?: boolean };

export function companionCopy(state: CompanionState) {
  if (state.stage === 'safety_hold') return { label: 'Safety boundary', title: 'Pause the Studio here.', body: 'Use your agreed safety pathway. The Studio will not coach through a safety concern.', primary: 'Open safety card' };
  if (state.returningAfterGap) return { label: 'Welcome back', title: 'Start with today, not catch-up.', body: 'Choose only what is possible now. Nothing from the gap needs to be repaid.', primary: 'Start today' };
  if (state.stage === 'evening') return { label: 'Close the day', title: 'Keep one useful thing from today.', body: 'Name what helped, what cost more, or what you want to repeat. That is enough.', primary: 'Close today' };
  if (state.actionStatus === 'deferred' || state.stage === 'deferred') return { label: 'A later route', title: 'The next step can wait.', body: 'You have not failed the plan. Choose a smaller route, return later, or stop for today.', primary: 'Choose another route' };
  if (state.currentAction) return { label: 'Your companion', title: state.currentAction, body: 'Stay with this one step. If the situation changes, change the route rather than pushing through.', primary: 'Guide me from here' };
  return { label: 'Your companion', title: 'What would make the next few hours more possible?', body: 'Choose one useful action. The Studio will help you adapt it if the day changes.', primary: 'Guide me' };
}

export function shouldOfferReentry(lastSeen: string|null, today: string) { return Boolean(lastSeen && lastSeen !== today); }
