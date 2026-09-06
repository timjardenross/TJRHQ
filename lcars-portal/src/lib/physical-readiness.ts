/**
 * Physical Readiness — shared types/labels for the exercise library and
 * workout history views.
 *
 * The deterministic session-generation engine this file used to contain
 * (chooseSessionType/generateSession/swapExercise/makeEasier/makeShorter,
 * plus their ReadinessInput/PlanExercise/GeneratedSession/TEMPLATES/
 * COACHING_CUES support) had zero callers anywhere in the app — the
 * readiness check-in and session-completion flows that would have called
 * it were retired (Captain directive, 2026-08-10/11; see
 * physical-readiness/start/page.tsx and session/[id]/page.tsx, both now
 * static "moved" notices). Removed as orphaned dead code in the workbench
 * integration audit rather than left to bit-rot silently; Recovery Pulse
 * (Telegram XO bot) is the single source for capacity/stats now. Schema:
 * migration 0068/0069 (physical_readiness_*, physical_exercises,
 * physical_workout_*).
 */

export type SessionType =
  | 'recovery'
  | 'low_energy_strength'
  | 'balanced_strength'
  | 'upper_body_strength'
  | 'lower_body_gentle_strength'
  | 'cardio_mobility'
  | 'minimum_viable';

/** Row shape matches physical_exercises columns directly (migration 0068). */
export interface ExerciseRow {
  id: string;
  name: string;
  equipment: string;
  movement_pattern: string;
  primary_muscles_json: string[];
  difficulty: string;
  default_sets: number;
  default_reps: number;
  default_duration_minutes: number | null;
  pain_cautions_json: Record<string, number>;
  regression: string | null;
  progression: string | null;
  video_search_query: string;
  preferred_video_url: string | null;
  status: 'active' | 'avoid' | 'needs_review';
}

export const SESSION_TYPE_LABELS: Record<SessionType, string> = {
  recovery: 'Recovery Session',
  low_energy_strength: 'Low Energy Strength',
  balanced_strength: 'Balanced Strength',
  upper_body_strength: 'Upper Body Strength',
  lower_body_gentle_strength: 'Lower Body Gentle Strength',
  cardio_mobility: 'Cardio + Mobility',
  minimum_viable: 'Minimum Viable Session',
};

export function youtubeSearchUrl(query: string): string {
  return `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
}
