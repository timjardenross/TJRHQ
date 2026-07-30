/**
 * Physical Readiness — deterministic workout generation.
 *
 * Rule-based, no LLM in the decision path (LLM is optional/future for prose
 * only). Every function here is pure so the 3 validation scenarios in the
 * mission brief can be asserted directly. Schema: migration 0068/0069
 * (physical_readiness_*, physical_exercises, physical_workout_*).
 */

export type EnergyState = 'green' | 'yellow' | 'orange' | 'red';
export type SessionIntent = 'move_gently' | 'build_strength' | 'reduce_stress' | 'improve_energy' | 'maintain_habit';
export type TimeAvailableMinutes = 15 | 25 | 35 | 45;
export type SessionType =
  | 'recovery'
  | 'low_energy_strength'
  | 'balanced_strength'
  | 'upper_body_strength'
  | 'lower_body_gentle_strength'
  | 'cardio_mobility'
  | 'minimum_viable';

export interface ReadinessInput {
  energyState: EnergyState;
  backPain: number;
  kneePain: number;
  anklePain: number;
  neckShoulderPain: number;
  generalPain: number;
  timeAvailableMinutes: TimeAvailableMinutes;
  sessionIntent: SessionIntent;
  notes?: string;
}

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

export interface PlanExercise {
  exercise: ExerciseRow;
  sets: number;
  reps: number;
  durationMinutes: number;
  why: string;
  setupCues: string[];
  formCues: string[];
  commonMistakes: string[];
  painCaution: string | null;
  beginnerTarget: string;
}

export interface GeneratedSession {
  sessionType: SessionType;
  reason: string;
  estimatedDurationMinutes: number;
  warmup: PlanExercise | null;
  cooldown: PlanExercise | null;
  exercises: PlanExercise[];
  isRedState: boolean;
  isMinimumViable: boolean;
  leaveGymPermission: boolean;
}

const PAIN_FIELD_TO_KEY: Record<string, keyof ReadinessInput> = {
  back_pain: 'backPain',
  knee_pain: 'kneePain',
  ankle_pain: 'anklePain',
  neck_shoulder_pain: 'neckShoulderPain',
  general_pain: 'generalPain',
};

/** Equipment tier — lower sorts first. "Prefer machines before free weights for safety and confidence." */
function equipmentTier(equipment: string): number {
  const e = equipment.toLowerCase();
  if (e.includes('machine') && !e.includes('smith')) return 0; // chest/shoulder/leg press, lat pulldown
  if (e.includes('cable') || e.includes('functional trainer')) return 1;
  if (e.includes('smith')) return 2;
  if (e.includes('treadmill') || e.includes('bike') || e.includes('elliptical')) return 1;
  if (e.includes('dumbbell')) return 3;
  if (e.includes('kettlebell')) return 4;
  return 5; // bodyweight / mat
}

/** An exercise is safe for this check-in if active and no pain caution threshold is met or exceeded. */
export function isExerciseSafe(exercise: ExerciseRow, input: ReadinessInput): boolean {
  if (exercise.status !== 'active') return false;
  for (const [field, threshold] of Object.entries(exercise.pain_cautions_json ?? {})) {
    const inputKey = PAIN_FIELD_TO_KEY[field];
    if (!inputKey) continue;
    const painValue = input[inputKey] as number;
    if (painValue >= threshold) return false;
  }
  return true;
}

export function filterSafeExercises(exercises: ExerciseRow[], input: ReadinessInput): ExerciseRow[] {
  return exercises.filter((ex) => isExerciseSafe(ex, input));
}

/**
 * Session-type decision tree. Order is the priority order: safety (energy
 * red, elevated pain) always outranks stated intent.
 */
export function chooseSessionType(input: ReadinessInput): SessionType {
  if (input.energyState === 'red') return 'recovery';
  if (input.timeAvailableMinutes <= 15) return 'minimum_viable';
  if (input.energyState === 'orange') return 'low_energy_strength';
  if (input.sessionIntent === 'reduce_stress') return 'cardio_mobility';
  if (input.sessionIntent === 'move_gently') return 'cardio_mobility';
  if (input.kneePain >= 6 || input.anklePain >= 6) return 'upper_body_strength';
  if (input.backPain >= 6) return 'upper_body_strength';
  if (input.neckShoulderPain >= 6) return 'lower_body_gentle_strength';
  if (input.sessionIntent === 'improve_energy') return 'cardio_mobility';
  return 'balanced_strength'; // build_strength, maintain_habit
}

interface SlotQuery {
  patterns: string[];
  label: string;
}

interface SessionTemplate {
  warmup: SlotQuery | null;
  cooldown: SlotQuery | null;
  slots: SlotQuery[];
}

const TEMPLATES: Record<SessionType, SessionTemplate> = {
  recovery: {
    warmup: null,
    // No separate cooldown slot — breathing + walk + mobility below already
    // closes the session, and the red-state rule caps this at ~10-15 min.
    cooldown: null,
    slots: [
      { patterns: ['breathing'], label: 'Breathing reset' },
      { patterns: ['cardio'], label: 'Gentle walk' },
      { patterns: ['mobility'], label: 'Light mobility' },
    ],
  },
  minimum_viable: {
    warmup: { patterns: ['cardio'], label: 'Short warm-up' },
    cooldown: { patterns: ['mobility', 'breathing'], label: 'Cooldown' },
    slots: [
      { patterns: ['push', 'pull'], label: 'One upper-body exercise' },
      { patterns: ['squat'], label: 'One lower-body exercise' },
    ],
  },
  low_energy_strength: {
    warmup: { patterns: ['cardio'], label: 'Easy warm-up' },
    cooldown: { patterns: ['mobility', 'breathing'], label: 'Cooldown' },
    slots: [
      { patterns: ['push'], label: 'Push' },
      { patterns: ['pull'], label: 'Pull' },
      { patterns: ['squat'], label: 'Legs' },
    ],
  },
  balanced_strength: {
    warmup: { patterns: ['cardio'], label: 'Warm-up' },
    cooldown: { patterns: ['cardio', 'mobility'], label: 'Cooldown walk / mobility' },
    slots: [
      { patterns: ['push'], label: 'Push' },
      { patterns: ['pull'], label: 'Pull' },
      { patterns: ['squat'], label: 'Legs' },
      { patterns: ['pull', 'push'], label: 'Accessory' },
    ],
  },
  upper_body_strength: {
    warmup: { patterns: ['cardio'], label: 'Warm-up (bike preferred)' },
    cooldown: { patterns: ['mobility'], label: 'Upper-body mobility' },
    slots: [
      { patterns: ['push'], label: 'Push' },
      { patterns: ['pull'], label: 'Pull' },
      { patterns: ['push'], label: 'Push accessory' },
      { patterns: ['pull'], label: 'Pull accessory' },
    ],
  },
  lower_body_gentle_strength: {
    warmup: { patterns: ['cardio'], label: 'Warm-up' },
    cooldown: { patterns: ['mobility'], label: 'Hip / calf mobility' },
    slots: [
      { patterns: ['squat'], label: 'Legs' },
      { patterns: ['calf'], label: 'Calves' },
      { patterns: ['carry'], label: 'Carry' },
    ],
  },
  cardio_mobility: {
    warmup: null,
    cooldown: { patterns: ['breathing'], label: 'Breathing close' },
    slots: [
      { patterns: ['cardio'], label: 'Cardio' },
      { patterns: ['mobility'], label: 'Mobility' },
      { patterns: ['mobility'], label: 'Mobility' },
    ],
  },
};

const COACHING_CUES: Record<string, { setup: string[]; form: string[]; mistakes: string[] }> = {
  cardio: {
    setup: ['Set an easy, conversational pace before increasing effort.'],
    form: ['Relaxed shoulders', 'Steady breathing'],
    mistakes: ['Starting too fast', 'Holding the rails/handles too tightly'],
  },
  push: {
    setup: ['Set the seat/handle height so the movement starts at chest level.'],
    form: ['Brace core lightly', 'Controlled tempo down and up', 'Exhale on the push'],
    mistakes: ['Locking elbows hard at the top', 'Rushing the return'],
  },
  pull: {
    setup: ['Set the seat/pad so your torso stays upright through the pull.'],
    form: ['Lead with the elbows', 'Squeeze shoulder blades together', 'Controlled release'],
    mistakes: ['Using momentum/jerking the weight', 'Shrugging shoulders up toward ears'],
  },
  squat: {
    setup: ['Feet hip-width, weight through the whole foot.'],
    form: ['Sit back, not just down', 'Knees track over toes', 'Stop at a comfortable depth'],
    mistakes: ['Knees caving inward', 'Going deeper than is comfortable for the knee/back'],
  },
  hinge: {
    setup: ['Soft knees, flat back, weight close to the body.'],
    form: ['Push hips back first', 'Keep spine neutral', 'Short, controlled range'],
    mistakes: ['Rounding the lower back', 'Rushing the descent'],
  },
  rotation: {
    setup: ['Feet planted, rotate from the hips and torso together.'],
    form: ['Slow, controlled rotation', 'Stop short of end-range if any pull is felt'],
    mistakes: ['Twisting through the lower back alone', 'Moving too fast'],
  },
  carry: {
    setup: ['Stand tall before taking the first step.'],
    form: ['Shoulders back and down', 'Short, steady steps', 'Brace core'],
    mistakes: ['Leaning to one side', 'Rushing the walk'],
  },
  calf: {
    setup: ['Hold something stable for balance if needed.'],
    form: ['Full but comfortable range', 'Slow lower on the way down'],
    mistakes: ['Bouncing at the bottom', 'Rushing the reps'],
  },
  mobility: {
    setup: ['Move into position slowly; stop well short of any pain.'],
    form: ['Slow, controlled movement', 'Breathe through the stretch'],
    mistakes: ['Forcing range of motion', 'Holding the breath'],
  },
  breathing: {
    setup: ['Find a seated or lying position where the body can fully relax.'],
    form: ['Slow inhale through the nose', 'Slower exhale out'],
    mistakes: ['Shallow chest-only breathing', 'Rushing to finish'],
  },
};

function paintPainCaution(exercise: ExerciseRow): string | null {
  const entries = Object.entries(exercise.pain_cautions_json ?? {});
  if (entries.length === 0) return null;
  const labels: Record<string, string> = {
    back_pain: 'back pain',
    knee_pain: 'knee pain',
    ankle_pain: 'ankle pain',
    neck_shoulder_pain: 'neck/shoulder pain',
    general_pain: 'general pain',
  };
  return entries
    .map(([field, threshold]) => `Avoid if ${labels[field] ?? field} is ${threshold}/10 or higher.`)
    .join(' ');
}

function estimateExerciseMinutes(exercise: ExerciseRow, sets: number): number {
  if (exercise.default_duration_minutes) return exercise.default_duration_minutes;
  return Math.max(2, sets * 2); // ~2 min per set including rest, for machine/cable/free-weight work
}

function toPlanExercise(exercise: ExerciseRow, why: string): PlanExercise {
  const cues = COACHING_CUES[exercise.movement_pattern] ?? COACHING_CUES.mobility;
  return {
    exercise,
    sets: exercise.default_sets,
    reps: exercise.default_reps,
    durationMinutes: estimateExerciseMinutes(exercise, exercise.default_sets),
    why,
    setupCues: cues.setup,
    formCues: cues.form,
    commonMistakes: cues.mistakes,
    painCaution: paintPainCaution(exercise),
    beginnerTarget: `${exercise.default_sets} x ${exercise.default_reps || '—'}${exercise.default_reps ? ' reps' : ''}${exercise.default_duration_minutes ? ` (~${exercise.default_duration_minutes} min)` : ''}, light/moderate effort`,
  };
}

function pickForSlot(
  slot: SlotQuery,
  candidates: ExerciseRow[],
  used: Set<string>,
): ExerciseRow | null {
  const matches = candidates
    .filter((ex) => slot.patterns.includes(ex.movement_pattern) && !used.has(ex.id))
    .sort((a, b) => equipmentTier(a.equipment) - equipmentTier(b.equipment));
  return matches[0] ?? null;
}

function buildReason(input: ReadinessInput, sessionType: SessionType): string {
  const parts: string[] = [];
  if (input.energyState === 'red') {
    parts.push('Energy is Red, so today is recovery only — no normal training.');
  } else if (input.energyState === 'orange') {
    parts.push('Energy is Orange, so this session is kept short and light.');
  } else {
    parts.push(`Energy is ${input.energyState === 'green' ? 'Green' : 'Yellow'}.`);
  }
  if (input.kneePain >= 6) parts.push(`Knee pain is ${input.kneePain}/10, so heavy leg press, squats and high-impact cardio are excluded.`);
  if (input.anklePain >= 6) parts.push(`Ankle pain is ${input.anklePain}/10, so running/incline and jumping-style work are excluded.`);
  if (input.backPain >= 6) parts.push(`Back pain is ${input.backPain}/10, so loaded hinges, twisting and unsupported free-weight rows are excluded.`);
  if (input.neckShoulderPain >= 6) parts.push(`Neck/shoulder pain is ${input.neckShoulderPain}/10, so overhead pressing is excluded.`);
  if (input.timeAvailableMinutes <= 15) parts.push('Only 15 minutes available, so this is a minimum viable session.');
  else parts.push(`${input.timeAvailableMinutes} minutes available.`);
  const intentLabel: Record<SessionIntent, string> = {
    move_gently: 'move gently',
    build_strength: 'build strength',
    reduce_stress: 'reduce stress',
    improve_energy: 'improve energy',
    maintain_habit: 'maintain the habit',
  };
  parts.push(`Stated intent: ${intentLabel[input.sessionIntent]}.`);
  parts.push(`Session type chosen: ${SESSION_TYPE_LABELS[sessionType]}.`);
  return parts.join(' ');
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

export function generateSession(input: ReadinessInput, allExercises: ExerciseRow[]): GeneratedSession {
  const sessionType = chooseSessionType(input);
  const safe = filterSafeExercises(allExercises, input);
  const template = TEMPLATES[sessionType];
  const used = new Set<string>();

  let warmup: PlanExercise | null = null;
  if (template.warmup) {
    const ex = pickForSlot(template.warmup, safe, used);
    if (ex) {
      used.add(ex.id);
      warmup = toPlanExercise(ex, 'Warm-up — raises heart rate gently before working sets.');
    }
  }

  const maxSlots = input.energyState === 'orange' ? Math.min(3, template.slots.length) : template.slots.length;
  const exercises: PlanExercise[] = [];
  for (const slot of template.slots.slice(0, maxSlots)) {
    const ex = pickForSlot(slot, safe, used);
    if (!ex) continue;
    used.add(ex.id);
    exercises.push(toPlanExercise(ex, `${slot.label} — selected as the safest available option given today's readiness.`));
  }

  let cooldown: PlanExercise | null = null;
  if (template.cooldown) {
    const cooldownEx = pickForSlot(template.cooldown, safe, used);
    if (cooldownEx) {
      used.add(cooldownEx.id);
      cooldown = toPlanExercise(cooldownEx, 'Cooldown — brings the nervous system back down before finishing.');
    }
  }

  const estimatedDurationMinutes =
    (warmup?.durationMinutes ?? 0) +
    exercises.reduce((sum, e) => sum + e.durationMinutes, 0) +
    (cooldown?.durationMinutes ?? 0);

  return {
    sessionType,
    reason: buildReason(input, sessionType),
    estimatedDurationMinutes,
    warmup,
    cooldown,
    exercises,
    isRedState: input.energyState === 'red',
    isMinimumViable: sessionType === 'minimum_viable' || sessionType === 'recovery',
    leaveGymPermission: input.energyState === 'red',
  };
}

/** "Swap exercise" — next safest alternate with the same movement pattern, not already in the plan. */
export function swapExercise(
  current: PlanExercise,
  plan: GeneratedSession,
  allExercises: ExerciseRow[],
  input: ReadinessInput,
): PlanExercise | null {
  const safe = filterSafeExercises(allExercises, input);
  const usedIds = new Set(
    [plan.warmup, ...plan.exercises, plan.cooldown].filter(Boolean).map((e) => (e as PlanExercise).exercise.id),
  );
  const alt = safe
    .filter((ex) => ex.movement_pattern === current.exercise.movement_pattern && !usedIds.has(ex.id))
    .sort((a, b) => equipmentTier(a.equipment) - equipmentTier(b.equipment))[0];
  if (!alt) return null;
  return toPlanExercise(alt, 'Swapped in as an alternate for the same movement pattern.');
}

/** "Make easier" — apply this exercise's own regression note and reduce target volume. */
export function makeEasier(planExercise: PlanExercise): PlanExercise {
  return {
    ...planExercise,
    sets: Math.max(1, planExercise.sets - 1),
    reps: planExercise.reps ? Math.max(6, Math.round(planExercise.reps * 0.8)) : planExercise.reps,
    why: planExercise.exercise.regression
      ? `Made easier: ${planExercise.exercise.regression}`
      : `${planExercise.why} (reduced volume)`,
  };
}

/** "Make shorter" — drop the lowest-priority main exercise (last in the list), keep warm-up/cooldown. */
export function makeShorter(plan: GeneratedSession): GeneratedSession {
  if (plan.exercises.length <= 1) return plan;
  const exercises = plan.exercises.slice(0, -1);
  const estimatedDurationMinutes =
    (plan.warmup?.durationMinutes ?? 0) +
    exercises.reduce((sum, e) => sum + e.durationMinutes, 0) +
    (plan.cooldown?.durationMinutes ?? 0);
  return { ...plan, exercises, estimatedDurationMinutes };
}

export function youtubeSearchUrl(query: string): string {
  return `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
}
