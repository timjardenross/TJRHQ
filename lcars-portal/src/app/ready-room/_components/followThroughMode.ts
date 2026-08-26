import { FOLLOW_THROUGH_MODES, type FollowThroughMode } from '@/lib/personalTasks';

export { FOLLOW_THROUGH_MODES };

/** When a due date is picked, nudge the follow-through mode to 'deadline' —
 * but only if the user hasn't already deliberately changed the mode away
 * from its default. Mirrors the existing urgency-bump-on-due-date logic in
 * QuickAdd/DecomposeView: an explicit user choice always wins. */
export function autoSwitchModeOnDueDate(
  dueDate: string,
  currentMode: FollowThroughMode,
  modeTouched: boolean,
): FollowThroughMode {
  if (dueDate && !modeTouched) return 'deadline';
  return currentMode;
}
